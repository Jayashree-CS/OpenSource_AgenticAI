"""
services/intent_classifier.py

Hybrid intent classification:
1. Deterministic keyword/regex layer (fast, no LLM cost).
2. Gemini 1.5 Flash fallback for ambiguous messages.

The classifier returns a structured ``IntentResult`` with a confidence score
and a downstream agent recommendation.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from llm import get_llm
from services.normalization import NormalizedQuery, normalize_message

logger = logging.getLogger(__name__)


# Canonical intents understood by the orchestrator.
INTENTS = (
    "leave",
    "ticket",
    "asset",
    "approval",
    "inventory",
    "informational",  # RAG / policy / company facts
    "conversational",  # greetings, smalltalk
)

# Agent routing per intent.
INTENT_TO_AGENT = {
    "leave": "hr",
    "ticket": "it",
    "asset": "it",
    "approval": "approvals",
    "inventory": "it",
    "informational": "rag",
    "conversational": "general",
}


@dataclass
class IntentResult:
    intent: str
    agent: str
    confidence: float
    source: str  # "rule" | "llm" | "fallback"
    normalized: NormalizedQuery
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "agent": self.agent,
            "confidence": self.confidence,
            "source": self.source,
            "reason": self.reason,
            "normalized": self.normalized.as_dict(),
        }


# ---------------------------------------------------------------------------
# Deterministic rules
# ---------------------------------------------------------------------------

_LEAVE_RE = re.compile(
    r"\b(apply|need|request|book|take)\b.*\bleave\b|"
    r"\b(sick|casual|earned)\s+leave\b|"
    r"\bleave\s+(balance|history|policy|status)\b|"
    r"\bcancel\s+leave\s+#?\d+\b|"
    r"\btime\s+off\b|\bday\s+off\b",
    re.IGNORECASE,
)

_TICKET_RE = re.compile(
    r"\b(raise|create|open|file|new)\b.*\bticket\b|"
    r"\bticket\s+(status|history)\b|"
    r"\bvpn\b|\bwifi\b|\bnetwork\b|"
    r"\bpassword\s+reset\b|"
    r"\b(laptop|monitor|keyboard|mouse|printer|headset)\s+(issue|problem|broken|not\s+working|hardware)\b",
    re.IGNORECASE,
)

_ASSET_RE = re.compile(
    r"\bassets?\s+request(s)?\b|"
    r"\b(request|need|want)\b.*\b(laptop|monitor|keyboard|mouse|headset|phone)\b|"
    r"\bcancel\s+asset\s+#?\d+\b|"
    r"\bmy\s+assets\b",
    re.IGNORECASE,
)

_APPROVAL_RE = re.compile(
    r"\b(approve|reject)\s+(leave|asset)\s+#?\d+\b|"
    r"\bpending\s+(approvals|leaves|assets)\b|"
    r"\bteam\s+approvals\b",
    re.IGNORECASE,
)

_INVENTORY_RE = re.compile(
    r"\binventory\b|\bstock\s+level(s)?\b|\bavailable\s+(laptops|monitors|assets)\b|\blow\s+stock\b",
    re.IGNORECASE,
)

_INFO_RE = re.compile(
    r"^(what|how|why|when|where|who|tell me|explain)\b|"
    r"\bpolicy\b|\bguideline\b|\bsop\b|\bceo\b|\bcompany\s+name\b",
    re.IGNORECASE,
)

_CHAT_RE = re.compile(
    r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|thanks|thank\s+you|bye|goodbye)\b",
    re.IGNORECASE,
)


_ACTION_VERBS_RE = re.compile(
    r"\b(apply|request|raise|create|open|file|cancel|approve|reject|book|need|want|update|resolve)\b",
    re.IGNORECASE,
)


def _rule_classify(nq: NormalizedQuery) -> Optional[IntentResult]:
    text = nq.normalized

    if _APPROVAL_RE.search(text):
        return IntentResult("approval", INTENT_TO_AGENT["approval"], 0.95, "rule", nq, "approval keywords")
    if _INVENTORY_RE.search(text):
        return IntentResult("inventory", INTENT_TO_AGENT["inventory"], 0.9, "rule", nq, "inventory keywords")

    # Informational/policy questions take precedence over action intents when
    # there's no explicit action verb (e.g. "what is the leave policy?").
    is_question = nq.flags.get("is_question")
    has_action_verb = bool(_ACTION_VERBS_RE.search(text))
    if (is_question and not has_action_verb) or _INFO_RE.search(text) and not has_action_verb:
        return IntentResult("informational", INTENT_TO_AGENT["informational"], 0.85, "rule", nq, "informational question")

    if _LEAVE_RE.search(text) or nq.leave_type:
        return IntentResult("leave", INTENT_TO_AGENT["leave"], 0.9, "rule", nq, "leave keywords")
    if _ASSET_RE.search(text) or (nq.asset_type and "request" in text):
        return IntentResult("asset", INTENT_TO_AGENT["asset"], 0.85, "rule", nq, "asset keywords")
    if _TICKET_RE.search(text) or nq.ticket_category:
        return IntentResult("ticket", INTENT_TO_AGENT["ticket"], 0.85, "rule", nq, "ticket keywords")
    if _CHAT_RE.search(text):
        return IntentResult("conversational", INTENT_TO_AGENT["conversational"], 0.95, "rule", nq, "greeting")
    if is_question:
        return IntentResult("informational", INTENT_TO_AGENT["informational"], 0.8, "rule", nq, "question form")

    return None


# ---------------------------------------------------------------------------
# LLM fallback
# ---------------------------------------------------------------------------


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    return match.group(0) if match else raw


_LLM_PROMPT_TEMPLATE = """You are an enterprise AI intent classifier.

Classify the message into ONE of these intents:
- leave: applying/cancelling/asking-about leave or balances
- ticket: raising/checking IT support tickets
- asset: requesting/cancelling/listing company assets
- approval: a manager approving/rejecting team requests
- inventory: stock levels or hardware availability
- informational: factual questions, policies, company info
- conversational: greetings, smalltalk

Return ONLY JSON with this schema:
{{"intent": "<one of the above>", "confidence": <0..1 float>, "reason": "short reason"}}

Message: "{message}"
"""


def _llm_classify(nq: NormalizedQuery) -> Optional[IntentResult]:
    try:
        llm = get_llm("gemini_flash")
        prompt = _LLM_PROMPT_TEMPLATE.format(message=nq.normalized)
        response = llm.invoke(prompt)
        raw = getattr(response, "content", str(response))
        parsed = json.loads(_clean_json(raw))
        intent = (parsed.get("intent") or "conversational").strip().lower()
        if intent not in INTENTS:
            intent = "conversational"
        confidence = float(parsed.get("confidence") or 0.5)
        confidence = max(0.0, min(1.0, confidence))
        reason = (parsed.get("reason") or "llm classification").strip()
        return IntentResult(intent, INTENT_TO_AGENT[intent], confidence, "llm", nq, reason)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("LLM intent classification failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(message: str) -> IntentResult:
    """Classify ``message`` and return an ``IntentResult``."""
    nq = normalize_message(message)

    if not nq.normalized:
        return IntentResult("conversational", "general", 1.0, "rule", nq, "empty input")

    rule_result = _rule_classify(nq)
    if rule_result and rule_result.confidence >= 0.85:
        return rule_result

    llm_result = _llm_classify(nq)
    if llm_result and llm_result.confidence >= 0.6:
        return llm_result

    if rule_result:
        return rule_result

    return IntentResult("conversational", "general", 0.3, "fallback", nq, "no high-confidence signal")


__all__ = ["INTENTS", "INTENT_TO_AGENT", "IntentResult", "classify"]

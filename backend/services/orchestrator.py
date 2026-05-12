"""
services/orchestrator.py

Thin orchestration layer that combines normalization + intent classification
and produces a structured routing decision for downstream agents.

Existing chat handlers (``routes/chat.py``) can call ``orchestrate(message)``
to get a deterministic routing artifact while preserving their existing
LangGraph + agent flow. This module is purely additive and never mutates DB
state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from services.intent_classifier import IntentResult, classify
from services.normalization import NormalizedQuery

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationDecision:
    intent: str
    agent: str
    confidence: float
    source: str
    reason: str
    normalized: NormalizedQuery
    requires_confirmation: bool = False
    pending_workflow: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "intent": self.intent,
            "agent": self.agent,
            "confidence": self.confidence,
            "source": self.source,
            "reason": self.reason,
            "requires_confirmation": self.requires_confirmation,
            "pending_workflow": self.pending_workflow,
            "normalized": self.normalized.as_dict(),
        }


def _confirmation_required(intent: str, normalized: NormalizedQuery) -> bool:
    """Heuristic: actionable workflows that mutate state should confirm."""
    if intent in {"leave", "asset"} and not normalized.flags.get("is_status_query"):
        return True
    if intent == "approval":
        return True
    return False


def _pending_workflow_for(intent: str) -> Optional[str]:
    if intent == "leave":
        return "hr_leave"
    if intent in {"ticket", "asset", "inventory"}:
        return "it_action"
    if intent == "approval":
        return "approval"
    return None


def orchestrate(message: str, *, session_state: object | None = None) -> OrchestrationDecision:
    """
    Run normalization + intent classification and return an
    ``OrchestrationDecision``.

    If ``session_state`` exposes ``get_pending_step``/``get_pending`` it is
    inspected so that bare confirmations like ``yes`` carry the previous
    workflow forward.
    """
    intent_result: IntentResult = classify(message)
    nq = intent_result.normalized

    pending_workflow = _pending_workflow_for(intent_result.intent)

    # If session has pending workflow, prefer it on bare confirmations.
    if session_state is not None and nq.flags.get("is_confirmation"):
        get_pending = getattr(session_state, "get_pending_step", None)
        pending = get_pending() if callable(get_pending) else None
        if isinstance(pending, dict) and pending.get("type"):
            pending_workflow = pending["type"]
            agent = "hr" if pending_workflow.startswith("hr_") else "it"
            return OrchestrationDecision(
                intent=intent_result.intent,
                agent=agent,
                confidence=max(intent_result.confidence, 0.9),
                source="session",
                reason="bare confirmation routed to active workflow",
                normalized=nq,
                requires_confirmation=False,
                pending_workflow=pending_workflow,
            )

    return OrchestrationDecision(
        intent=intent_result.intent,
        agent=intent_result.agent,
        confidence=intent_result.confidence,
        source=intent_result.source,
        reason=intent_result.reason,
        normalized=nq,
        requires_confirmation=_confirmation_required(intent_result.intent, nq),
        pending_workflow=pending_workflow,
    )


__all__ = ["OrchestrationDecision", "orchestrate"]

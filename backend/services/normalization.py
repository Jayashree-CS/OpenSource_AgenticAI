"""
services/normalization.py

Lexical and semantic normalization for inbound user messages. The output is a
``NormalizedQuery`` dataclass with the original text, a normalized form, and any
detected entities (dates, leave type, ticket category, asset type). The
intent classifier and orchestrator consume this artifact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from actions.enhanced_date_action import (
    enhanced_date_action,
    parse_relative_date_safe,
)


# ---------------------------------------------------------------------------
# Synonym maps
# ---------------------------------------------------------------------------

# Phrase-level rewrites (applied first, longest match wins).
PHRASE_REWRITES: Dict[str, str] = {
    "not feeling good": "sick leave",
    "not feeling well": "sick leave",
    "feeling sick": "sick leave",
    "fell ill": "sick leave",
    "i am ill": "sick leave",
    "vacation leave": "casual leave",
    "vacation": "casual leave",
    "annual leave": "earned leave",
    "privilege leave": "earned leave",
    "personal leave": "casual leave",
    "vpn issue": "vpn not working ticket",
    "vpn problem": "vpn not working ticket",
    "vpn down": "vpn not working ticket",
    "wifi issue": "wifi not working ticket",
    "wi-fi issue": "wifi not working ticket",
    "internet down": "wifi not working ticket",
    "laptop issue": "laptop hardware ticket",
    "laptop slow": "laptop hardware ticket",
    "system slow": "laptop hardware ticket",
    "password reset": "password reset ticket",
    "forgot password": "password reset ticket",
    "need a laptop": "laptop asset request",
    "need new laptop": "laptop asset request",
    "request laptop": "laptop asset request",
    "request a laptop": "laptop asset request",
    "want a laptop": "laptop asset request",
    "monitor request": "monitor asset request",
    "headset request": "headset asset request",
}

# Single-word synonyms applied after phrase rewrites.
WORD_SYNONYMS: Dict[str, str] = {
    "vac": "casual",
    "vacay": "casual",
    "holiday": "casual",
    "ill": "sick",
    "unwell": "sick",
    "wifi": "wifi",
    "wi-fi": "wifi",
    "internet": "wifi",
    "vpn": "vpn",
    "lappy": "laptop",
    "pc": "laptop",
    "machine": "laptop",
    "screen": "monitor",
    "display": "monitor",
}

# Common typos -> canonical word.
TYPO_FIXES: Dict[str, str] = {
    "leav": "leave",
    "leve": "leave",
    "leavs": "leaves",
    "tickt": "ticket",
    "tikket": "ticket",
    "tikit": "ticket",
    "asest": "asset",
    "aset": "asset",
    "appove": "approve",
    "approveit": "approve it",
    "rejct": "reject",
    "cancl": "cancel",
    "cancle": "cancel",
    "tomorow": "tomorrow",
    "tommrow": "tomorrow",
    "tomoro": "tomorrow",
    "tdy": "today",
    "yest": "yesterday",
    "passwrd": "password",
    "vpns": "vpn",
}

LEAVE_TYPE_KEYWORDS = {
    "casual": "casual",
    "sick": "sick",
    "earned": "earned",
}

TICKET_CATEGORY_KEYWORDS = {
    "vpn": "vpn",
    "wifi": "network",
    "network": "network",
    "laptop": "hardware",
    "monitor": "hardware",
    "keyboard": "hardware",
    "mouse": "hardware",
    "printer": "hardware",
    "headset": "hardware",
    "password": "access",
    "access": "access",
    "software": "software",
    "license": "software",
    "install": "software",
}

ASSET_TYPE_KEYWORDS = {
    "laptop": "laptop",
    "monitor": "monitor",
    "keyboard": "keyboard",
    "mouse": "mouse",
    "headset": "headset",
    "phone": "phone",
}


# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


@dataclass
class NormalizedQuery:
    raw: str
    normalized: str
    cleaned: str
    detected_dates: List[date] = field(default_factory=list)
    relative_keywords: List[str] = field(default_factory=list)
    leave_type: Optional[str] = None
    ticket_category: Optional[str] = None
    asset_type: Optional[str] = None
    flags: Dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "raw": self.raw,
            "normalized": self.normalized,
            "cleaned": self.cleaned,
            "detected_dates": [d.isoformat() for d in self.detected_dates],
            "relative_keywords": self.relative_keywords,
            "leave_type": self.leave_type,
            "ticket_category": self.ticket_category,
            "asset_type": self.asset_type,
            "flags": dict(self.flags),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PUNCT_RE = re.compile(r"[\t\r\n]+")
_MULTISPACE_RE = re.compile(r"\s+")


def _basic_clean(text: str) -> str:
    if not text:
        return ""
    cleaned = _PUNCT_RE.sub(" ", text)
    cleaned = _MULTISPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _apply_typo_fixes(tokens: List[str]) -> List[str]:
    return [TYPO_FIXES.get(tok, tok) for tok in tokens]


def _apply_word_synonyms(tokens: List[str]) -> List[str]:
    return [WORD_SYNONYMS.get(tok, tok) for tok in tokens]


def _apply_phrase_rewrites(text: str) -> str:
    lowered = text.lower()
    # Sort by length descending so longer phrases match first.
    for phrase in sorted(PHRASE_REWRITES, key=len, reverse=True):
        if phrase in lowered:
            lowered = lowered.replace(phrase, PHRASE_REWRITES[phrase])
    return lowered


def _detect_leave_type(text: str) -> Optional[str]:
    for keyword, value in LEAVE_TYPE_KEYWORDS.items():
        if re.search(rf"\b{keyword}\b", text):
            return value
    return None


def _detect_ticket_category(text: str) -> Optional[str]:
    for keyword, value in TICKET_CATEGORY_KEYWORDS.items():
        if re.search(rf"\b{keyword}\b", text):
            return value
    return None


def _detect_asset_type(text: str) -> Optional[str]:
    for keyword, value in ASSET_TYPE_KEYWORDS.items():
        if re.search(rf"\b{keyword}\b", text):
            return value
    return None


def _detect_dates(text: str) -> tuple[List[date], List[str]]:
    """Detect ISO dates and relative keywords (today/tomorrow/next monday)."""
    dates: List[date] = []
    keywords: List[str] = []

    # ISO yyyy-mm-dd
    for match in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        try:
            dates.append(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
        except ValueError:
            continue

    # Relative date via enhanced_date_action.
    parsed, keyword = parse_relative_date_safe(text)
    if parsed and keyword:
        dates.append(parsed)
        keywords.append(keyword)

    # Sweep for additional weekday/relative tokens (e.g., "next friday and monday").
    for weekday_name in (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ):
        if re.search(rf"\bnext\s+{weekday_name}\b", text):
            keyword = f"next_{weekday_name}"
            if keyword not in keywords:
                weekday_idx = (
                    "monday tuesday wednesday thursday friday saturday sunday"
                ).split().index(weekday_name)
                dates.append(enhanced_date_action.get_next_weekday(weekday_idx))
                keywords.append(keyword)

    # Deduplicate while preserving order.
    seen: set[date] = set()
    deduped_dates: List[date] = []
    for d in dates:
        if d in seen:
            continue
        seen.add(d)
        deduped_dates.append(d)

    return deduped_dates, keywords


def _flag_intents(text: str) -> Dict[str, bool]:
    return {
        "is_question": text.endswith("?") or text.startswith(("what", "how", "why", "when", "who", "where")),
        "is_confirmation": text in {"yes", "y", "yeah", "yep", "no", "n", "nope", "confirm", "ok", "okay"},
        "is_cancellation": "cancel" in text,
        "is_status_query": any(p in text for p in ("status", "history", "show me", "list")),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_message(message: str) -> NormalizedQuery:
    """
    Run lexical + semantic normalization over ``message`` and return a
    ``NormalizedQuery`` dataclass.
    """
    raw = message or ""
    cleaned = _basic_clean(raw)

    rewritten = _apply_phrase_rewrites(cleaned)
    tokens = rewritten.split()
    tokens = _apply_typo_fixes(tokens)
    tokens = _apply_word_synonyms(tokens)
    normalized = " ".join(tokens).strip()

    detected_dates, relative_keywords = _detect_dates(normalized)

    return NormalizedQuery(
        raw=raw,
        normalized=normalized,
        cleaned=cleaned,
        detected_dates=detected_dates,
        relative_keywords=relative_keywords,
        leave_type=_detect_leave_type(normalized),
        ticket_category=_detect_ticket_category(normalized),
        asset_type=_detect_asset_type(normalized),
        flags=_flag_intents(normalized.lower()),
    )


__all__ = ["NormalizedQuery", "normalize_message"]

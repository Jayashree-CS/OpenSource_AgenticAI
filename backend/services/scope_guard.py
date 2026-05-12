"""
services/scope_guard.py

Deterministic out-of-scope detector for the enterprise copilot.

The agent is restricted to HR (leave / policy / employee handbook), IT
(tickets / VPN / hardware / software / network), Asset (laptop / monitor
requests), Approvals, Inventory, and Company-policy questions answered
from the ingested document corpus. Everything else — recipes, weather,
sports, jokes, current events, free-form coding help, personal opinions,
political / religious takes — must be politely declined with a friendly
redirect that lists what the bot CAN help with.

This module is intentionally LLM-free: the decision is made with regex /
keyword lists so it is fast, deterministic, and easy to reason about
during a demo. The orchestrator's full LLM intent classifier still runs
afterwards for the in-scope traffic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# In-scope vocabulary
# ---------------------------------------------------------------------------
# Any one of these substrings appearing in the user message is enough to
# treat the question as plausibly enterprise-related; in that case we let
# the regular pipeline (router → HR/IT agent → RAG) handle it.

_IN_SCOPE_KEYWORDS: tuple[str, ...] = (
    # HR / leave
    "leave", "leaves", "vacation", "holiday", "pto", "time off", "day off",
    "sick", "casual", "earned", "maternity", "paternity", "bereavement",
    "wfh", "work from home", "remote work",
    "salary", "payroll", "payslip", "appraisal", "increment", "bonus",
    "reimbursement", "expense", "allowance", "benefits", "insurance",
    "medical", "pf", "provident fund", "gratuity",
    "notice period", "resignation", "probation", "termination",
    "policy", "handbook", "guideline", "code of conduct", "ethics",
    "csr", "dress code", "company", "organisation", "organization",
    "hr", "manager", "employee", "team", "department",
    "approve", "approval", "reject",
    # IT / tickets / asset
    "ticket", "tickets", "issue", "problem", "broken", "not working",
    "vpn", "wifi", "wi-fi", "network", "internet", "connection",
    "outlook", "email", "mailbox", "calendar", "teams",
    "laptop", "desktop", "monitor", "keyboard", "mouse", "headset",
    "printer", "scanner", "phone",
    "password", "login", "credential", "access", "account",
    "software", "license", "install", "upgrade", "vpn token",
    "asset", "request", "inventory", "stock",
    "it support", "it team", "helpdesk", "service desk",
    # Conversational openers that should still be served
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "thanks", "thank you", "bye", "goodbye",
    # Self-service follow-ups
    "my status", "my requests", "my history", "my balance", "my ticket",
    "my asset", "my leave", "show status", "track",
    # Date helpers (already wired up in chat.py)
    "today", "tomorrow", "yesterday", "what day", "current date",
)


# Words that almost always indicate the user is asking about the company
# / org / policies even if they don't explicitly mention HR/IT.
_INFO_QUESTION_PATTERNS = (
    re.compile(r"\bwho is\b.*\b(ceo|cto|cfo|founder|head|director|manager|hr|it)\b", re.I),
    re.compile(r"\bwhat is\b.*\b(policy|process|procedure|company|organisation|organization)\b", re.I),
    re.compile(r"\bhow (many|much|do i|can i|to)\b", re.I),
    re.compile(r"\bam i (allowed|entitled|eligible)\b", re.I),
    re.compile(r"\b(when|where) (is|will|does|can)\b", re.I),
)


# ---------------------------------------------------------------------------
# Out-of-scope vocabulary
# ---------------------------------------------------------------------------
# Strong signals that the question has nothing to do with internal
# enterprise operations. We use these as a positive-evidence list; they
# only matter when there is NO in-scope keyword in the same message.

_OUT_OF_SCOPE_TOPICS: dict[str, tuple[str, ...]] = {
    "cooking / recipes": (
        "recipe", "recipes", "cook", "cooking", "bake", "baking", "fry",
        "biryani", "biriyani", "pasta", "pizza", "curry", "dish", "ingredient",
        "kitchen", "chef",
    ),
    "weather": (
        "weather", "temperature", "forecast", "rain", "raining", "snow",
        "humidity", "climate today", "is it hot", "is it cold",
    ),
    "sports": (
        "cricket", "football", "soccer", "basketball", "tennis", "ipl",
        "world cup", "fifa", "match score", "live score",
    ),
    "entertainment": (
        "movie", "film", "song", "music", "lyrics", "album", "netflix",
        "spotify", "youtube video", "celebrity", "actor", "actress",
    ),
    "current events / news": (
        "news", "headline", "election", "stock price", "share price",
        "crypto", "bitcoin", "ethereum",
    ),
    "personal advice": (
        "should i date", "girlfriend", "boyfriend", "horoscope", "zodiac",
        "tarot", "fortune", "lucky number",
    ),
    "general knowledge / trivia": (
        "capital of", "president of", "prime minister of", "tallest mountain",
        "longest river", "what year did", "who invented", "who won",
    ),
    "free-form coding": (
        "write a python", "write code", "give me a program", "leetcode",
        "algorithm for", "write a sql", "write a function",
    ),
    "math homework": (
        "solve for x", "integrate", "differentiate", "factorize", "binomial",
        "quadratic equation",
    ),
    "religion / politics": (
        "who is god", "religion", "bible", "quran", "gita",
        "political party", "vote for", "election result",
    ),
    "jokes / chitchat with no enterprise hook": (
        "tell me a joke", "make me laugh", "are you human", "are you single",
        "do you love me", "what's your favourite", "what is your favorite",
    ),
}


@dataclass
class ScopeDecision:
    in_scope: bool
    reason: str
    matched_topic: str | None = None  # populated when out of scope
    redirect_message: str | None = None


SUPPORTED_CAPABILITIES = (
    "Apply / cancel leave and check leave balance",
    "Raise IT support tickets (laptop, VPN, network, software, etc.)",
    "Request company assets (laptop, monitor, keyboard, mouse…)",
    "Ask about HR policies, the employee handbook, leave rules, CSR, "
    "code of conduct, and other company documents",
    "Track the status of your existing leaves, tickets, or asset requests",
)


def _build_redirect(topic: str | None) -> str:
    """Build a friendly, brand-safe redirect message."""
    intro = (
        f"I'm sorry — I can't help with {topic} questions."
        if topic
        else "I'm sorry — that's outside what I'm built to help with."
    )
    bullets = "\n".join(f"  • {cap}" for cap in SUPPORTED_CAPABILITIES)
    return (
        f"{intro} I'm CopilotAI, your internal HR & IT assistant. "
        "Here's what I can help you with:\n\n"
        f"{bullets}\n\n"
        "Just ask me about any of those — for example, \"apply 2 days of "
        "casual leave next Monday\" or \"my VPN keeps disconnecting\"."
    )


def _tokenize(text_lower: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z'-]*", text_lower))


def _matches_keyword(kw: str, text_lower: str, tokens: set[str]) -> bool:
    """Whole-word match for single tokens, substring match for phrases.

    Substring matching for short tokens like ``hi`` would otherwise hit
    inside ``chicken`` and let cooking questions through.
    """
    if " " in kw or "-" in kw:
        return kw in text_lower
    return kw in tokens


def _has_in_scope_signal(text_lower: str) -> bool:
    tokens = _tokenize(text_lower)
    if any(_matches_keyword(kw, text_lower, tokens) for kw in _IN_SCOPE_KEYWORDS):
        return True
    return any(p.search(text_lower) for p in _INFO_QUESTION_PATTERNS)


def _matched_out_of_scope_topic(text_lower: str) -> str | None:
    tokens = _tokenize(text_lower)
    for topic, words in _OUT_OF_SCOPE_TOPICS.items():
        if any(_matches_keyword(w, text_lower, tokens) for w in words):
            return topic
    return None


def evaluate(message: str) -> ScopeDecision:
    """Decide whether ``message`` is in or out of scope for the copilot.

    Rules (deterministic, in order):

    1. Empty / whitespace-only → in_scope (let the chat layer handle it).
    2. If there is ANY in-scope keyword OR a known info-question pattern,
       the message is in scope — even if it also mentions a recipe by
       coincidence (e.g. "the canteen serves biryani — what's the food
       allowance policy?").
    3. Otherwise, if any out-of-scope topic word matches → out of scope
       with a friendly redirect tagged with the topic.
    4. Otherwise, in scope with reason ``unclassified`` so the regular
       RAG / general fallback decides.
    """
    if not message or not message.strip():
        return ScopeDecision(in_scope=True, reason="empty")

    text = message.strip().lower()

    if _has_in_scope_signal(text):
        return ScopeDecision(in_scope=True, reason="in_scope_keyword")

    topic = _matched_out_of_scope_topic(text)
    if topic is not None:
        return ScopeDecision(
            in_scope=False,
            reason="off_topic_keyword",
            matched_topic=topic,
            redirect_message=_build_redirect(topic),
        )

    return ScopeDecision(in_scope=True, reason="unclassified")


def is_out_of_scope(message: str) -> bool:
    """Convenience wrapper returning a plain bool."""
    return not evaluate(message).in_scope


__all__ = [
    "ScopeDecision",
    "SUPPORTED_CAPABILITIES",
    "evaluate",
    "is_out_of_scope",
]

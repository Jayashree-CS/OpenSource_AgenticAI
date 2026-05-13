from datetime import date, timedelta, datetime
import re
import os
import dateparser
from dateparser.search import search_dates

from actions.hr_ai_action import extract_hr_action
from actions.leave_action import (
    apply_leave,
    get_leave_history,
    get_leave_balance,
    get_pending_leaves_for_manager,
    approve_leave_by_manager,
)
from actions.calendar_action import get_non_working_days_between, get_working_days
from actions.enhanced_date_action import (
    enhanced_date_action,
    parse_relative_date_safe,
    validate_leave_date_safe,
    get_date_info_safe,
    get_today,
    get_today_text,
)
from rag.retriever import retrieve_docs, retrieve_docs_with_sources
from llm import get_llm
from graph_structure.state import AgentSessionState, normalize_history
from db.models import Employee, LeaveRequest


# ---------------------------------------------------------------------------
# Deterministic HR routing helpers (used by chat router + tests)
# ---------------------------------------------------------------------------

_LEAVE_ID_RE = re.compile(r"#?(\d+)")


def _deterministic_hr_route(message: str) -> dict:
    """
    Deterministic regex-based router for HR intents. Returns a dict like
    ``{"action": "...", ...}``. Never invokes an LLM. Used for confidence
    routing in tests and as a fast pre-check before LLM extraction.
    """
    text = (message or "").strip().lower()

    confirmed = bool(re.search(r"\bconfirm(ed)?\b", text))

    # Approve / reject leave with id.
    if "approve" in text and "leave" in text:
        m = _LEAVE_ID_RE.search(text)
        return {
            "action": "approve_leave",
            "leave_id": int(m.group(1)) if m else None,
            "confirmed": confirmed,
        }
    if "reject" in text and "leave" in text and re.search(r"\b\d+\b", text):
        m = _LEAVE_ID_RE.search(text)
        return {
            "action": "reject_leave",
            "leave_id": int(m.group(1)) if m else None,
            "confirmed": confirmed,
        }
    if "cancel" in text and "leave" in text and re.search(r"\b\d+\b", text):
        m = _LEAVE_ID_RE.search(text)
        return {
            "action": "cancel_leave",
            "leave_id": int(m.group(1)) if m else None,
            "confirmed": confirmed,
        }

    # Status / informational
    if "leave balance" in text or "my balance" in text:
        return {"action": "leave_balance"}
    if "leave history" in text or "my leave history" in text:
        return {"action": "leave_history"}
    if "pending leave" in text or "my pending" in text or "pending approvals" in text:
        return {"action": "pending_leaves"}

    # Company / date facts
    if "ceo" in text or "company name" in text or "organization" in text or "organisation" in text:
        return {"action": "company_info"}
    if "what day is today" in text or "today's date" in text or "todays date" in text or "what is today" in text:
        return {"action": "date_question"}

    # Policy questions
    if "leave policy" in text or "policy" in text and "leave" in text:
        return {"action": "leave_policy_question"}

    # Application
    if "apply" in text and "leave" in text:
        return {"action": "apply_leave"}

    return {"action": "unknown"}


def parse_flexible_dates(message: str) -> dict:
    """
    Best-effort flexible date parser. Returns a dict with ISO date strings
    (or ``None``) and a relative keyword when applicable.

    Recognised forms:
      - ``apply leave tomorrow``
      - ``apply leave 2026-05-15``
      - ``apply leave from 2026-05-15 to 2026-05-17``
    """
    text = (message or "").strip()
    result: dict = {
        "start_date": None,
        "end_date": None,
        "date_error": None,
        "relative_keyword": None,
    }

    # Range form first: "from <iso> to <iso>".
    range_match = re.search(
        r"(\d{4}-\d{2}-\d{2})\s+(?:to|-|until|through)\s+(\d{4}-\d{2}-\d{2})",
        text,
    )
    if range_match:
        result["start_date"] = range_match.group(1)
        result["end_date"] = range_match.group(2)
        return result

    # Single ISO date.
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        result["start_date"] = iso.group(1)
        result["end_date"] = iso.group(1)
        return result

    # Relative keyword via the enhanced date service.
    parsed_date, keyword = parse_relative_date_safe(text)
    if parsed_date and keyword:
        iso_value = parsed_date.isoformat()
        result["start_date"] = iso_value
        result["end_date"] = iso_value
        result["relative_keyword"] = keyword
        return result

    # Free-form fallback via dateparser (best-effort, never raise).
    # IMPORTANT: only run this when the message actually contains a
    # date-shaped token. dateparser's ``search_dates`` is eager and will
    # happily invent a date for messages like "I want to apply for leave"
    # — which previously caused the bot to confirm with a hallucinated
    # date like "2026-05-14" even though the user never mentioned one.
    _date_evidence_re = re.compile(
        r"\b("
        r"\d{1,4}[-/]\d{1,2}([-/]\d{1,4})?"            # 2026-05-14, 14/5, 14-05-2026
        r"|\d{1,2}(st|nd|rd|th)?\s+(of\s+)?"           # 14th May
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)"
        r"|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}"  # May 14
        r"|next\s+\w+|this\s+\w+"                       # next monday
        r"|tomorrow|today|day\s+after\s+tomorrow"
        r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
        r")\b",
        re.IGNORECASE,
    )
    if _date_evidence_re.search(text):
        try:
            hits = search_dates(text, settings={"PREFER_DATES_FROM": "future"})
            if hits:
                first = hits[0][1]
                result["start_date"] = first.date().isoformat()
                result["end_date"] = first.date().isoformat()
                return result
        except Exception:
            pass

    if any(token in text.lower() for token in ("tomorrow", "today", "monday", "tuesday")):
        # We could not resolve even with hints; signal the error.
        result["date_error"] = "ambiguous_relative_date"
    return result

# ---------------------------------------------------------------------------
# Session-state shims (resilient to mock objects in tests)
# ---------------------------------------------------------------------------


def _session_get_pending(session_state):
    """Return the active pending workflow dict (``{"type", "data"}``) or
    ``None``. Supports both ``get_pending_step`` (canonical) and
    ``get_pending(key)`` (legacy / test mocks).
    """
    if session_state is None:
        return None
    fn = getattr(session_state, "get_pending_step", None)
    if callable(fn):
        try:
            return fn() or None
        except Exception:
            return None
    fn = getattr(session_state, "get_pending", None)
    if callable(fn):
        for key in ("hr_leave", "leave_application", "leave_approval"):
            try:
                data = fn(key)
            except Exception:
                continue
            if isinstance(data, dict) and data:
                return {"type": data.get("type", "leave_application"), "data": data}
    return None


def _session_clear_pending(session_state):
    if session_state is None:
        return
    fn = getattr(session_state, "clear_pending_step", None)
    if callable(fn):
        try:
            fn()
            return
        except Exception:
            pass
    fn = getattr(session_state, "clear_pending", None)
    if callable(fn):
        try:
            fn("hr_leave")
        except Exception:
            pass


def _session_set_pending(session_state, workflow_type: str, data: dict):
    if session_state is None:
        return
    fn = getattr(session_state, "set_pending_step", None)
    if callable(fn):
        try:
            fn(workflow_type, data)
            return
        except Exception:
            pass
    fn = getattr(session_state, "set_pending", None)
    if callable(fn):
        try:
            fn(workflow_type, data)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Slot-filling helpers — used for multi-turn leave workflow memory
# ---------------------------------------------------------------------------

_LEAVE_TYPE_PATTERNS = {
    "sick": re.compile(r"\bsick\b", re.IGNORECASE),
    "casual": re.compile(r"\bcasual\b", re.IGNORECASE),
    "earned": re.compile(r"\b(earned|annual|vacation|privilege)\b", re.IGNORECASE),
}

_REASON_HINT_RE = re.compile(
    r"\b(?:"
    r"because of|because|due to|for|reason[:\s]+"
    r"|as i (?:have|am|'m|feel|am feeling|'m feeling)"
    r"|since i (?:have|am|'m|feel)"
    r"|i (?:have|'m having|am having|'m suffering from|am suffering from)"
    r"|having (?:a |an )?"
    r"|suffering from"
    r"|diagnosed with"
    r")\s+(.+?)(?:[\.\,]|$)",
    re.IGNORECASE,
)

# Symptoms / situations that, when mentioned directly, are unambiguous
# reasons even without a "because"/"due to" connector. Keeps the bot from
# re-asking "reason?" when the user already said "I have fever".
_DIRECT_REASON_TOKENS = (
    "fever", "cold", "flu", "cough", "headache", "migraine", "stomach ache",
    "stomach pain", "food poisoning", "viral", "infection", "covid",
    "surgery", "hospital", "doctor", "medical", "dentist", "appointment",
    "wedding", "marriage", "funeral", "bereavement", "emergency",
    "family function", "personal work", "travel",
)


def _direct_reason(text: str) -> str | None:
    """Return a direct symptom/event reason if the message mentions one
    without any explicit ``because``/``due to`` connector.

    Example: ``"apply sick leave as I have fever"`` returns ``"fever"``
    even though ``as`` isn't in the legacy connector list.
    """
    if not text:
        return None
    lowered = text.lower()
    for token in _DIRECT_REASON_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", lowered):
            return token
    return None


def _coerce_date(value):
    """Accept date, datetime, or ISO string and return a ``datetime.date``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
        except Exception:
            try:
                return datetime.strptime(value.strip(), "%Y-%m-%d").date()
            except Exception:
                return None
    return None


def _detect_leave_type(text: str) -> str | None:
    if not text:
        return None
    for label, pattern in _LEAVE_TYPE_PATTERNS.items():
        if pattern.search(text):
            return label
    return None


_REASON_STOPWORDS = {
    # Functional words that show up when the user merely says
    # "I want to apply for leave" / "apply for a leave" — none of these
    # are real reasons and they used to leak in as reason="leave".
    "leave", "leaves", "a leave", "the leave", "my leave",
    "leave application", "leave request",
    "sick", "casual", "earned", "vacation", "annual", "privilege",
    "approval", "today", "tomorrow",
    "it", "hr",
}


def _detect_reason(text: str) -> str | None:
    if not text:
        return None
    m = _REASON_HINT_RE.search(text)
    if not m:
        return None
    reason = m.group(1).strip().rstrip(".,")
    if not reason:
        return None
    # Filter out functional words and leave-type names that the regex
    # often catches via "for leave" / "for sick" — these are not real
    # reasons and should not satisfy the mandatory reason slot.
    lowered = reason.lower()
    if lowered in _REASON_STOPWORDS:
        return None
    # Anything shorter than three characters is almost certainly noise.
    if len(lowered) < 3:
        return None
    return reason


def _merge_leave_slots(wf_data: dict, message: str, history, user) -> dict:
    """
    Merge any new entities mentioned in ``message`` into the existing
    workflow data dict. Existing non-empty slots are preserved (we never
    overwrite a previously confirmed value with a less-specific one).
    """
    merged = dict(wf_data or {})

    # Leave type
    if not merged.get("leave_type"):
        lt = _detect_leave_type(message)
        if lt:
            merged["leave_type"] = lt

    # Dates — first try the in-process flexible parser, then fall back to LLM.
    if not merged.get("start_date") or not merged.get("end_date"):
        flex = parse_flexible_dates(message)
        if flex.get("start_date") and not merged.get("start_date"):
            merged["start_date"] = flex["start_date"]
        if flex.get("end_date") and not merged.get("end_date"):
            merged["end_date"] = flex["end_date"]

    # Reason — try connector-based regex first, then direct symptom/event
    # tokens (so "apply sick leave as I have fever" yields reason="fever"
    # without needing a "because"/"due to" connector).
    if not merged.get("reason"):
        r = _detect_reason(message) or _direct_reason(message)
        if r:
            merged["reason"] = r

    # If we still don't have everything, try the LLM extractor with full
    # history — this covers natural-language follow-ups like
    # "22nd May 2026 because of fever". To prevent hallucinated defaults
    # (e.g. the LLM filling in "fever" / today's date when the user just
    # typed "apply leave"), we ONLY accept a slot from the LLM when the
    # underlying message actually contains evidence for it: a date-shaped
    # token for date slots, the word "reason"/"because"/"due to" for
    # reason, or a leave-type word for leave_type.
    if (not merged.get("leave_type")
            or not merged.get("start_date")
            or not merged.get("end_date")
            or not merged.get("reason")):
        msg_lower = (message or "").lower()
        msg_has_date_token = bool(
            re.search(r"\b\d{4}-\d{2}-\d{2}\b", message or "")
            or re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", message or "")
            or re.search(
                r"\b(today|tomorrow|day after tomorrow|next\s+\w+|this\s+\w+|"
                r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
                r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                msg_lower,
            )
        )
        msg_has_reason_marker = bool(
            re.search(
                r"\b(because|due to|reason|for the reason"
                r"|as i (have|am|'m|feel)"
                r"|since i (have|am|'m|feel)"
                r"|i have|i'm having|i am having"
                r"|suffering from|diagnosed with|having a|having an)\b",
                msg_lower,
            )
        ) or bool(_direct_reason(message))
        msg_has_leave_type = bool(_detect_leave_type(message))

        try:
            extracted = extract_hr_action(message, history, user)
            if extracted.get("action") in {"apply_leave", "leave_advice", "general_hr_question"}:
                if not merged.get("leave_type") and extracted.get("leave_type") and msg_has_leave_type:
                    merged["leave_type"] = extracted["leave_type"]
                if msg_has_date_token:
                    if not merged.get("start_date") and extracted.get("start_date"):
                        merged["start_date"] = extracted["start_date"]
                    if not merged.get("end_date") and extracted.get("end_date"):
                        merged["end_date"] = extracted["end_date"]
                if not merged.get("reason") and extracted.get("reason") and msg_has_reason_marker:
                    candidate = (extracted["reason"] or "").strip().rstrip(".,")
                    if candidate and candidate.lower() not in _REASON_STOPWORDS and len(candidate) >= 3:
                        merged["reason"] = candidate
        except Exception:
            pass

    if not merged.get("employee_id") and getattr(user, "id", None):
        merged["employee_id"] = user.id

    return merged


def _missing_leave_slots(wf_data: dict) -> list[str]:
    missing = []
    if not wf_data.get("leave_type"):
        missing.append("leave_type")
    if not wf_data.get("start_date"):
        missing.append("start_date")
    if not wf_data.get("end_date"):
        missing.append("end_date")
    # Reason is required so the bot never silently submits "Applied via AI".
    reason = (wf_data.get("reason") or "").strip()
    if not reason:
        missing.append("reason")
    return missing


# ---------------------------------------------------------------------------
# Fresh-start detection — lets the user reset a stale leave workflow
# ---------------------------------------------------------------------------

_APPLY_LEAVE_INITIATOR_RE = re.compile(
    r"\b("
    r"i\s+(?:want|need|would like|'?d like)\s+to\s+apply.*\bleave\b"
    r"|please\s+apply.*\bleave\b"
    r"|can\s+i\s+apply.*\bleave\b"
    r"|apply\s+(?:for\s+)?(?:a\s+|the\s+)?leave"
    r"|new\s+leave\s+(?:request|application)"
    r")",
    re.IGNORECASE,
)


def _is_fresh_apply_leave(message: str) -> bool:
    """True when the user is starting a brand-new leave application and
    carries no concrete slot data in the same message.

    Used to reset stale ``pending_workflow`` slots so the bot doesn't
    silently reuse a previous turn's ``sick`` + ``fever`` when the user
    just types ``"I want to apply leave"``.
    """
    if not message:
        return False
    if not _APPLY_LEAVE_INITIATOR_RE.search(message):
        return False
    if _detect_leave_type(message):
        return False
    if _detect_reason(message) or _direct_reason(message):
        return False
    flex = parse_flexible_dates(message)
    if flex.get("start_date") or flex.get("end_date"):
        return False
    return True


_SLOT_LABEL = {
    "leave_type": "leave type (sick / casual / earned)",
    "start_date": "start date",
    "end_date": "end date",
    "reason": "reason",
}


def _prompt_for_missing_leave_slots(missing: list[str], wf_data: dict) -> str:
    have = []
    if wf_data.get("leave_type"):
        have.append(f"{wf_data['leave_type']} leave")
    if wf_data.get("start_date") and wf_data.get("end_date"):
        if wf_data["start_date"] == wf_data["end_date"]:
            have.append(f"on {wf_data['start_date']}")
        else:
            have.append(f"from {wf_data['start_date']} to {wf_data['end_date']}")
    if wf_data.get("reason"):
        have.append(f"reason \"{wf_data['reason']}\"")

    have_text = (" Got " + ", ".join(have) + ".") if have else ""
    needs = ", ".join(_SLOT_LABEL.get(slot, slot) for slot in missing)
    return f"Sure, I can help with that.{have_text} I still need the {needs}."


# ---------------------------------------------------------------------------
# Main HR Agent
# ---------------------------------------------------------------------------

def hr_agent(message, db, user, history=None, session_state: AgentSessionState = None):
    """
    Main HR Agent entry point with multi-turn support.
    """
    msg_lower = (message or "").lower().strip()
    user_role = (user.role or "employee").lower()

    # 1. Handle Pending Multi-turn Workflow (resilient to mock state objects)
    pending = _session_get_pending(session_state)

    # 1.0 Fresh-start guard — if the user is initiating a brand-new leave
    # application ("I want to apply leave") while a stale ``leave_application``
    # workflow still holds slots from a previous turn (e.g. sick + fever),
    # reset that pending state so we re-collect all fields from scratch.
    # Without this, the bot silently reuses the old slots and only asks for
    # whatever single slot was missing last time.
    if pending and pending.get("type") == "leave_application" \
            and _is_fresh_apply_leave(message):
        _session_clear_pending(session_state)
        pending = None

    # 1a. Cancellation always wins, even mid-workflow.
    if pending and re.search(r"\b(no|cancel|stop|nevermind|abort)\b", msg_lower) \
            and not re.search(r"\b(yes|confirm|proceed|ok|sure)\b", msg_lower):
        _session_clear_pending(session_state)
        return "No problem — I've cancelled that request. Let me know if there's anything else I can help with."

    if pending:
        wf_type = pending.get("type")
        wf_data = dict(pending.get("data") or {})

        # 1b. Slot-filling: merge any new info from the user's message into the
        # saved workflow data (leave_type, dates, reason). This is what gives
        # the chat its short-term memory across 3+ turns.
        if wf_type == "leave_application":
            wf_data = _merge_leave_slots(wf_data, message, history, user)

            confirmation_keywords = re.search(r"\b(yes|confirm|correct|sure|ok|okay|proceed|do it|go ahead)\b", msg_lower)
            still_missing = _missing_leave_slots(wf_data)

            if not still_missing and (confirmation_keywords or wf_data.get("_auto_confirm")):
                apply_kwargs = {
                    "employee_id": wf_data.get("employee_id") or getattr(user, "id", None),
                    "start_date": _coerce_date(wf_data.get("start_date")),
                    "end_date": _coerce_date(wf_data.get("end_date")),
                    "reason": wf_data.get("reason") or "Applied via AI",
                    "leave_type": wf_data.get("leave_type") or "casual",
                }
                result = apply_leave(db, **apply_kwargs)
                _session_clear_pending(session_state)
                if isinstance(result, dict):
                    status = result.get("status")
                    if status == "insufficient_balance":
                        return (
                            f"I'm sorry — you don't have enough {wf_data.get('leave_type')} leave balance "
                            f"for these dates. Only {result.get('remaining', 0)} day(s) remaining."
                        )
                    if status == "non_working_days":
                        return "Those dates fall on a weekend or holiday, so no leave is needed."
                    if status == "missing_data":
                        return "I'm missing some details — could you share the leave type and exact dates?"
                    if status == "overlap":
                        return (
                            f"You already have a leave request for overlapping dates — "
                            f"Leave #{result.get('conflict_leave_id')} ({result.get('conflict_start')} to "
                            f"{result.get('conflict_end')}, status: {result.get('conflict_status')}). "
                            "Please cancel or pick a different window before applying again."
                        )
                    if status in {"invalid_date", "invalid_range", "past_date"}:
                        return result.get("message") or "Those dates don't look valid — please try again."
                return (
                    f"All done! Your {apply_kwargs['leave_type']} leave from "
                    f"{apply_kwargs['start_date']} to {apply_kwargs['end_date']} has been submitted "
                    f"and is now pending manager approval. You'll receive an email once it's reviewed."
                )

            if not still_missing:
                # Have all info but no explicit yes yet → ask for confirmation.
                _session_set_pending(session_state, "leave_application", wf_data)
                return (
                    f"Just to confirm: {wf_data.get('leave_type')} leave from "
                    f"{wf_data.get('start_date')} to {wf_data.get('end_date')}"
                    + (f", reason \"{wf_data.get('reason')}\"" if wf_data.get("reason") else "")
                    + ". Shall I submit it? (yes / no)"
                )

            # Still missing fields → save progress and ask for the rest.
            _session_set_pending(session_state, "leave_application", wf_data)
            return _prompt_for_missing_leave_slots(still_missing, wf_data)

        if wf_type == "leave_approval" and re.search(r"\b(yes|confirm|correct|sure|ok|proceed|do it)\b", msg_lower):
            approve_leave_by_manager(db, wf_data.get("leave_id"), user.id)
            _session_clear_pending(session_state)
            return f"Leave request #{wf_data.get('leave_id')} has been approved."

    # 2. Deterministic Routing (Regex based)
    if "leave balance" in msg_lower or "my balance" in msg_lower:
        balance = get_leave_balance(db, user.id)
        reply = "📊 **Your Leave Balance:**\n"
        for l_type, b in balance.items():
            reply += f"• {l_type.capitalize()}: {b['remaining']} remaining (Used: {b['used']})\n"
        return reply

    if "leave history" in msg_lower or "my history" in msg_lower:
        history_list = get_leave_history(db, user.id)
        if not history_list: return "You have no leave history."
        reply = "📜 **Your Leave History:**\n"
        for l in history_list[-5:]:
            reply += f"• {l.start_date} to {l.end_date} | {l.leave_type} | {l.status}\n"
        return reply

    if "pending approvals" in msg_lower or "show pending" in msg_lower:
        if user_role not in ["manager", "admin"]: return "Only managers can view pending approvals."
        pending_list = get_pending_leaves_for_manager(db, user.id)
        if not pending_list: return "No pending approvals found."
        reply = "⏳ **Pending Approvals:**\n"
        for p in pending_list:
            reply += f"• Request #{p.id} from Employee ID {p.employee_id} | {p.leave_type} | {p.start_date}\n"
        return reply

    # 3. Leave Application Detection (kicks off a multi-turn workflow)
    if "apply" in msg_lower and "leave" in msg_lower or re.search(r"\b(want to|need to|would like to)\b.*\bleave\b", msg_lower):
        # Start with an EMPTY slot bag and let _merge_leave_slots fill it
        # using only evidence actually present in this turn's message.
        # The previous version seeded ``wf_data`` directly from
        # ``extract_hr_action(message, history, user)``, which let the LLM
        # extractor hallucinate ``leave_type=sick, reason=fever,
        # start_date=today`` by reading them out of stale conversation
        # history. _merge_leave_slots' internal LLM fallback already
        # applies msg_has_date_token / msg_has_reason_marker /
        # msg_has_leave_type evidence checks, so going through it gives
        # us the same coverage without the hallucinated defaults.
        wf_data = _merge_leave_slots({}, message, history, user)
        still_missing = _missing_leave_slots(wf_data)

        _session_set_pending(session_state, "leave_application", wf_data)

        if not still_missing:
            return (
                f"Just to confirm: {wf_data.get('leave_type')} leave from "
                f"{wf_data.get('start_date')} to {wf_data.get('end_date')}"
                + (f", reason \"{wf_data.get('reason')}\"" if wf_data.get("reason") else "")
                + ". Shall I submit it? (yes / no)"
            )
        return _prompt_for_missing_leave_slots(still_missing, wf_data)

    # 4. RAG-grounded informational fallback. Any question that looks like
    #    a policy / HR / company / procedure question MUST be answered from
    #    the ingested company document corpus — never free-form LLM. If the
    #    retriever returns nothing, we abstain with a fixed phrase.
    if _looks_like_policy_question(msg_lower):
        return _rag_grounded_answer(message, role=user_role)

    # For any other HR-ish question, still prefer RAG over speculating.
    return _rag_grounded_answer(message, role=user_role)


# ---------------------------------------------------------------------------
# Policy-question detection
# ---------------------------------------------------------------------------

_POLICY_KEYWORDS = (
    "policy", "rule", "guideline", "procedure", "handbook", "process",
    "notice period", "probation", "termination", "resignation",
    "leave", "casual leave", "sick leave", "earned leave", "maternity",
    "paternity", "bereavement", "holiday", "work from home", "wfh",
    "reimbursement", "expense", "allowance", "payroll", "salary",
    "advance", "bonus", "increment", "appraisal", "performance review",
    "benefits", "insurance", "medical", "pf", "provident fund", "gratuity",
    "ceo", "company", "organization", "organisation", "headquarter",
    "address", "location", "founded", "mission", "vision", "values",
    "code of conduct", "ethics", "csr", "dress code", "travel",
    "how many", "how much", "what is", "what are", "how do i",
    "how to", "can i", "am i allowed", "am i entitled",
)


def _looks_like_policy_question(msg_lower: str) -> bool:
    return any(kw in msg_lower for kw in _POLICY_KEYWORDS)


def _rag_grounded_answer(message: str, role: str | None = None) -> str:
    """
    Answer an informational question strictly from the ingested company
    document corpus. No hardcoded facts, no free-form speculation.

    The retriever is RBAC-filtered by ``role`` so employees never see
    manager/admin-only material. If retrieval returns nothing, we abstain
    with a fixed phrase rather than letting the LLM hallucinate.
    """
    hits = retrieve_docs_with_sources(message, k=5, role=role)
    if not hits:
        return (
            "I couldn't find this in our company documents. "
            "Please contact HR for clarification."
        )

    # Build a context block that preserves per-chunk source markers so the
    # LLM can cite them inline.
    context_parts = []
    sources = []
    for i, (text, src, page) in enumerate(hits, 1):
        tag = f"[{i}] {src}" + (f" (p.{page + 1})" if isinstance(page, int) else "")
        context_parts.append(f"{tag}\n{text}")
        sources.append(tag)
    context = "\n\n---\n\n".join(context_parts)

    llm = get_llm("groq_fast")
    prompt = (
        "You are CopilotAI, the internal company knowledge assistant for an "
        "enterprise. Answer the user's question using ONLY the provided "
        "context from official company documents. Follow these rules:\n"
        "1. Never invent or rely on outside knowledge. If the context does "
        "not contain the answer, reply exactly: "
        "\"I couldn't find this in our company documents. Please contact HR for clarification.\"\n"
        "2. Be concise, professional, and conversational. Avoid bullet-point "
        "dumps unless the user asked for a list.\n"
        "3. Cite the document after each fact in square brackets, e.g. [1] "
        "or [2], matching the numbered sources in the context.\n"
        "4. Never ask the user which company they mean — the context IS "
        "the company's own documentation.\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {message}\n\nAnswer:"
    )
    try:
        answer = llm.invoke(prompt).content.strip()
    except Exception:
        return (
            "I'm temporarily unable to read the policy documents. "
            "Please try again shortly."
        )

    # Append a compact sources footer so users see where facts came from.
    uniq_sources = []
    seen = set()
    for tag in sources:
        if tag not in seen:
            uniq_sources.append(tag)
            seen.add(tag)
    footer = "\n\nSources: " + "; ".join(uniq_sources)
    return answer + footer

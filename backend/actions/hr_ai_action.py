import json
import re

from llm import get_llm
from actions.enhanced_date_action import get_today


def _clean_json(raw: str) -> str:
    """Strip markdown fences and extract first JSON object from a string."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return match.group(0)
    return raw


def extract_hr_action(message: str, history: list = None, user=None):
    """
    Use the LLM to extract HR intent and entities from the user message.

    history is a list of {"role": "user"|"assistant", "content": "..."} dicts
    representing the current session.
    """
    llm = get_llm()
    today = get_today().isoformat()

    history_text = "(no prior turns)"
    if history:
        turns = []
        for turn in history[-10:]:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "")
            turns.append(f"{role}: {content}")
        history_text = "\n".join(turns)

    prompt = f"""
You are an HR operations intent and entity extraction agent.

Today's date is {today}.

--- CONVERSATION HISTORY (oldest first, most recent last) ---
{history_text}
--- END HISTORY ---

Current user message: {message}

Your job:
- Understand the user's HR request, resolving any follow-up answers using history.
  Example: if the assistant previously asked "What type of leave?" and the user now
  says "sick", the action is apply_leave with leave_type=sick.
- Convert all natural language dates to YYYY-MM-DD using today's date as {today}.
- Support flexible formats:
  tomorrow, today, day after tomorrow, next Monday, this Friday,
  2nd Jan 2026, Jan 2 2026, January 2nd 2026,
  02/01/2026, 2026-01-02, from 2 Jan to 5 Jan,
  for 3 days from tomorrow.
- If the user gives an impossible date like 2027-02-31, set:
  start_date = null,
  end_date = null,
  date_error = "Invalid date: 2027-02-31"
- Natural spelling mistakes are fine: "sik leave tomorow" = sick leave tomorrow.

Supported actions:
  apply_leave, leave_balance, leave_history, pending_leaves,
  pending_approvals, approve_leave, reject_leave, cancel_leave,
  leave_status, leave_policy_question, leave_advice,
  company_info, date_question, general_hr_question

Return ONLY a single valid JSON object - no markdown fences, no prose.

Schema:
{{
  "action": "...",
  "leave_type": "casual|sick|earned|other|null",
  "start_date": "YYYY-MM-DD|null",
  "end_date": "YYYY-MM-DD|null",
  "leave_id": number|null,
  "reason": string|null,
  "missing_info": [],
  "date_error": string|null
}}

Rules:
- Classify command and self-service intents before apply_leave.
- Explicit examples:
  * "confirm approve leave 24" = approve_leave, leave_id=24
  * "approve leave 24" = approve_leave, leave_id=24
  * "confirm reject leave 24" = reject_leave, leave_id=24
  * "reject leave 24" = reject_leave, leave_id=24
  * "cancel leave 24" = cancel_leave, leave_id=24
  * "status of leave 24" = leave_status, leave_id=24
  * "show my leave history" = leave_history
  * "show my pending leaves" = pending_leaves
  * "show pending approvals" = pending_approvals
  * "show my leave balance" = leave_balance
  * "what leave should I take if I am sick" = leave_advice
  * "can I apply leave tomorrow" = leave_advice
  * "what is sick leave policy" = leave_policy_question
  * "what day is today" = date_question
  * "who is the ceo" = company_info
  * "what is organization name" = company_info
  * "apply sick leave tomorrow for fever" = apply_leave
  * "apply leave tomorrow" = apply_leave
- Only return apply_leave when the user clearly wants to create, apply, or submit a leave request.
- apply_leave: extract leave_type, start_date, end_date, reason.
  * Set missing fields to null and list them in missing_info.
- Informational or permission questions are leave_policy_question, general_hr_question, or leave_advice, not apply_leave.
  Examples:
  * "what kind of leave should I apply if I am sick?" = leave_advice
  * "can I apply leave tomorrow?" = leave_advice
  * "can I take sick leave?" = leave_advice
  * "which leave can I apply?" = leave_advice
- Questions asking which leave type to use are leave_advice, not apply_leave.
  Example: "I am not feeling well, what leave should I put?" = leave_advice.
- approve_leave / reject_leave: set the action and extract leave_id.
- Single-day leave: start_date == end_date.
- Unclear HR question: action = "general_hr_question", missing_info = [], date_error = null.
- Output NOTHING outside the JSON object.
"""

    last_error = None
    for attempt in range(3):
        try:
            response = llm.invoke(prompt)
            raw = response.content
            cleaned = _clean_json(raw)
            data = json.loads(cleaned)

            return {
                "action": data.get("action", "general_hr_question"),
                "leave_type": data.get("leave_type"),
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
                "leave_id": data.get("leave_id"),
                "reason": data.get("reason"),
                "needs_confirmation": bool(data.get("needs_confirmation", False)),
                "confirmation_message": data.get("confirmation_message"),
                "missing_info": data.get("missing_info") or [],
                "date_error": data.get("date_error"),
            }

        except Exception as e:
            last_error = e
            print(f"[hr_ai_action] Extraction attempt {attempt + 1} failed: {e}")

    print(f"[hr_ai_action] All attempts failed. Defaulting. Last error: {last_error}")
    return {
        "action": "general_hr_question",
        "leave_type": None,
        "start_date": None,
        "end_date": None,
        "leave_id": None,
        "reason": None,
        "needs_confirmation": False,
        "confirmation_message": None,
        "missing_info": [],
        "date_error": None,
    }

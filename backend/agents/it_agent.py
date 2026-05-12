import json
import re
from typing import Any

from llm import get_llm
from graph_structure.state import AgentSessionState
from actions.it_action import (
    create_ticket,
    get_all_tickets,
    get_open_tickets,
    get_tickets_by_status,
    get_user_tickets,
    update_ticket_status,
    TicketTransitionError,
)
from db.models import Employee
from actions.email_action import send_email
from actions.asset_action import (
    create_asset_request,
    get_asset_requests,
    get_all_asset_requests,
    get_asset_requests_for_manager,
    get_pending_asset_requests_for_manager,
    approve_asset_by_manager,
    reject_asset_by_manager,
    get_pending_assets_for_it,
    approve_asset_by_it,
    reject_asset_by_it,
    cancel_asset_request,
)


IT_ROLES = {"it", "it_team", "admin"}
MANAGER_ROLES = {"manager", "admin"}
VALID_ASSET_TYPES = ("laptop", "monitor", "keyboard", "mouse", "vpn token", "software license")
CONFIRM_WORDS = {"confirm", "yes", "y", "ok", "okay", "sure", "proceed"}
CANCEL_WORDS = {"cancel", "no", "nope", "stop", "abort"}
PENDING_KEY = "it_action"


def extract_request_id(message: str):
    match = re.search(r"\d+", message)
    if match:
        return int(match.group())
    return None


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r"```$", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return match.group(0)
    return raw


def extract_it_details(message: str):
    llm = get_llm()

    prompt = f"""
You are an IT operations assistant.

Classify the user's message.

Return ONLY valid JSON:

{{
  "action_type": "ticket_status | all_ticket_status | open_tickets | ticket_update | create_ticket | asset_request | asset_status | cancel_asset_request | manager_pending_asset_approvals | manager_approve_asset | manager_reject_asset | it_pending_asset_approvals | it_approve_asset | it_reject_asset | general",
  "issue_type": "laptop | vpn | outlook | printer | network | software | general",
  "asset_type": "laptop | monitor | keyboard | mouse | vpn token | software license | null",
  "priority": "low | medium | high | critical",
  "target_status": "open | in_progress | resolved | closed | rejected | null"
}}

Rules:
- "show ticket status", "show all tickets" -> all_ticket_status for IT/Admin, ticket_status for Employee
- "what are the open tickets", "pending tickets", "open tickets" -> open_tickets
- "resolve ticket 5" -> ticket_update with target_status resolved
- "close ticket 5" -> ticket_update with target_status closed
- "reject ticket 5" -> ticket_update with target_status rejected
- Broken, slow, hanging, not working, unable to access, error, issue, problem -> create_ticket
- New hardware/software/access requests like need, request, want, provide, new -> asset_request
- "show asset status", "my asset requests" -> asset_status
- "cancel asset request 8" -> cancel_asset_request
- "show pending asset approvals" from manager -> manager_pending_asset_approvals
- "approve asset 8" -> manager_approve_asset
- "reject asset 8" -> manager_reject_asset
- "show pending it assets", "show IT asset approvals" -> it_pending_asset_approvals
- "it approve asset 8" -> it_approve_asset
- "it reject asset 8" -> it_reject_asset
- Normal IT tickets do not use manager approval. IT team manages assignment/status/resolution.

Message:
{message}
"""

    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()
        data = json.loads(_clean_json(raw))

        return {
            "action_type": data.get("action_type", "general"),
            "issue_type": data.get("issue_type", "general"),
            "asset_type": data.get("asset_type"),
            "priority": data.get("priority", "medium"),
            "target_status": data.get("target_status"),
        }

    except Exception as e:
        print(f"[it_agent] extract_it_details failed: {e}")
        return {
            "action_type": "general",
            "issue_type": "general",
            "asset_type": None,
            "priority": "medium",
            "target_status": None,
        }


def detect_issue_type(message: str) -> str:
    msg = message.lower()

    if "laptop" in msg or "system" in msg:
        return "laptop"
    if "vpn" in msg:
        return "vpn"
    if "outlook" in msg or "email" in msg:
        return "outlook"
    if "printer" in msg:
        return "printer"
    if "wifi" in msg or "network" in msg:
        return "network"
    if "software" in msg or "install" in msg:
        return "software"

    return "general"


def detect_priority(message: str) -> str:
    msg = message.lower()

    if "urgent" in msg or "critical" in msg or "blocked" in msg:
        return "critical"
    if "not working" in msg or "unable" in msg:
        return "high"

    return "medium"


def extract_asset_type(message: str) -> str | None:
    msg = message.lower()
    for asset_type in VALID_ASSET_TYPES:
        if asset_type in msg:
            return asset_type
    return None


def extract_ticket_update(message: str):
    msg = message.lower()
    ticket_id = extract_request_id(message)

    if "reject" in msg:
        status = "rejected"
    elif "close" in msg or "closed" in msg:
        status = "closed"
    elif "resolve" in msg or "resolved" in msg:
        status = "resolved"
    elif "progress" in msg:
        status = "in_progress"
    elif "open" in msg:
        status = "open"
    else:
        status = None

    return ticket_id, status


def _infer_it_details(message: str, user=None) -> dict[str, Any]:
    msg = message.lower().strip()
    ticket_id, target_status = extract_ticket_update(message)
    asset_type = extract_asset_type(message)

    details = {
        "action_type": "general",
        "issue_type": detect_issue_type(message),
        "asset_type": asset_type,
        "priority": detect_priority(message),
        "target_status": target_status,
        "ticket_id": ticket_id,
        "request_id": extract_request_id(message),
        "original_message": message,
    }

    if "ticket" in msg:
        if target_status and ticket_id:
            details["action_type"] = "ticket_update"
            return details
        if "open" in msg or "pending" in msg:
            details["action_type"] = "open_tickets"
            return details
        if "all" in msg:
            details["action_type"] = "all_ticket_status"
            return details
        if "status" in msg or "history" in msg or "my tickets" in msg or "tickets" in msg:
            details["action_type"] = "ticket_status"
            return details

    if "asset" in msg or asset_type:
        if "cancel" in msg:
            details["action_type"] = "cancel_asset_request"
            return details
        if "my" in msg and ("status" in msg or "requests" in msg or "request" in msg or "pending" in msg or "approval" in msg):
            details["action_type"] = "asset_status"
            return details
        if "it approve" in msg:
            details["action_type"] = "it_approve_asset"
            return details
        if "it reject" in msg:
            details["action_type"] = "it_reject_asset"
            return details
        if "pending" in msg and "approval" in msg:
            details["action_type"] = "manager_pending_asset_approvals"
            return details
        if "pending it" in msg or "it asset approval" in msg or "it assets" in msg:
            details["action_type"] = "it_pending_asset_approvals"
            return details
        if "approve" in msg:
            details["action_type"] = "manager_approve_asset"
            return details
        if "reject" in msg:
            details["action_type"] = "manager_reject_asset"
            return details
        if "all" in msg and ("status" in msg or "requests" in msg):
            details["action_type"] = "all_asset_status"
            return details
        if "team" in msg or "manager asset" in msg:
            details["action_type"] = "manager_asset_status"
            return details
        if "status" in msg or "requests" in msg:
            details["action_type"] = "asset_status"
            return details
        if any(word in msg for word in ("need", "request", "want", "provide", "new")):
            details["action_type"] = "asset_request"
            return details

    issue_words = ("not working", "broken", "slow", "hanging", "error", "issue", "problem", "unable")
    if any(word in msg for word in issue_words):
        details["action_type"] = "create_ticket"
        return details

    return details


def _merge_details(message: str, llm_details: dict[str, Any], user=None) -> dict[str, Any]:
    details = _infer_it_details(message, user=user)

    if details["action_type"] == "general":
        details["action_type"] = llm_details.get("action_type", "general")

    if details["issue_type"] == "general":
        details["issue_type"] = llm_details.get("issue_type", "general")

    if not details.get("asset_type"):
        asset_type = llm_details.get("asset_type")
        if asset_type and asset_type != "null":
            details["asset_type"] = asset_type

    if details["priority"] == "medium":
        details["priority"] = llm_details.get("priority", "medium")

    if not details.get("target_status"):
        details["target_status"] = llm_details.get("target_status")

    return details


def _get_pending(history: list | None = None, session_state: AgentSessionState | None = None):
    if session_state:
        return session_state.get_pending(PENDING_KEY)

    for turn in reversed(history or []):
        if turn.get("role") == "_system" and PENDING_KEY in turn:
            return turn[PENDING_KEY]

    return None


def _set_pending(
    ctx: dict[str, Any],
    history: list | None = None,
    session_state: AgentSessionState | None = None,
):
    if session_state:
        session_state.set_pending(PENDING_KEY, ctx)
        session_state.set_agent("it")
        return

    if history is not None:
        history[:] = [
            t for t in history
            if not (t.get("role") == "_system" and PENDING_KEY in t)
        ]
        history.append({"role": "_system", PENDING_KEY: ctx})


def _clear_pending(history: list | None = None, session_state: AgentSessionState | None = None):
    if session_state:
        session_state.clear_pending(PENDING_KEY)
        return

    if history is not None:
        history[:] = [
            t for t in history
            if not (t.get("role") == "_system" and PENDING_KEY in t)
        ]


def _is_confirm(message: str) -> bool:
    msg = message.lower().strip()
    return msg in CONFIRM_WORDS or msg.startswith("confirm ")


def _is_cancel(message: str) -> bool:
    return message.lower().strip() in CANCEL_WORDS


def _format_tickets(tickets) -> str:
    if not tickets:
        return "No IT tickets found."

    return "\n".join(
        f"Ticket #{t.id}: {t.issue_type} | User: {t.user_id} | Priority: {t.priority} | Status: {t.status}"
        for t in tickets
    )


def _format_asset_requests(requests) -> str:
    if not requests:
        return "No asset requests found."

    return "\n".join(
        f"Asset Request #{r.id}: {r.asset_type} | User: {r.user_id} | "
        f"Manager: {r.manager_status} | IT: {r.it_status} | Final: {r.final_status}"
        for r in requests
    )


def _set_last_action(
    session_state: AgentSessionState | None,
    action: str,
    status: str = "success",
    tool_used: str = "it_agent",
) -> None:
    if session_state:
        session_state.metadata["last_action"] = action
        session_state.metadata["last_status"] = status
        session_state.metadata["last_tool"] = tool_used


def _needs_confirmation(details: dict[str, Any]) -> bool:
    action_type = details["action_type"]
    if action_type in {
        "create_ticket",
        "asset_request",
        "cancel_asset_request",
        "manager_approve_asset",
        "manager_reject_asset",
        "it_approve_asset",
        "it_reject_asset",
    }:
        return True

    return action_type == "ticket_update" and details.get("target_status") in {
        "resolved",
        "closed",
        "rejected",
    }


def _precheck_action(details: dict[str, Any], user) -> str | None:
    action_type = details["action_type"]

    if action_type == "ticket_update" and user.role not in IT_ROLES:
        return "Access denied. Only IT team or admin can update tickets."

    if action_type in ("manager_approve_asset", "manager_reject_asset") and user.role not in MANAGER_ROLES:
        return "Access denied. Only managers or admin can approve or reject asset requests."

    if action_type in ("it_approve_asset", "it_reject_asset") and user.role not in IT_ROLES:
        return "Access denied. Only IT team or admin can approve or reject assets."

    return None


def _confirmation_prompt(details: dict[str, Any]) -> str:
    action_type = details["action_type"]

    if action_type == "create_ticket":
        return (
            f"Please confirm: create IT ticket for {details['issue_type']} issue? "
            "Reply: confirm create ticket"
        )

    if action_type == "asset_request":
        asset_type = details.get("asset_type")
        return (
            f"Please confirm: create asset request for {asset_type}? "
            f"Reply: confirm request {asset_type}"
        )

    if action_type == "cancel_asset_request":
        return (
            f"Please confirm: cancel asset request #{details.get('request_id')}? "
            f"Reply: confirm cancel asset request {details.get('request_id')}"
        )

    if action_type in ("manager_approve_asset", "manager_reject_asset", "it_approve_asset", "it_reject_asset"):
        action_word = "approve" if "approve" in action_type else "reject"
        return (
            f"Please confirm: {action_word} asset request #{details.get('request_id')}? "
            f"Reply: confirm {action_word} asset {details.get('request_id')}"
        )

    if action_type == "ticket_update":
        status = details.get("target_status")
        ticket_id = details.get("ticket_id")
        verb_by_status = {
            "closed": "close",
            "resolved": "resolve",
            "rejected": "reject",
            "in_progress": "mark in progress",
            "open": "open",
        }
        verb = verb_by_status.get(status, "update")
        return (
            f"Please confirm: {verb} ticket #{ticket_id}? "
            f"Reply: confirm {verb} ticket {ticket_id}"
        )

    return "Please confirm this action. Reply: confirm"


def _execute_ticket_update(details: dict[str, Any], db, user) -> str:
    if user.role not in IT_ROLES:
        return "Access denied. Only IT team or admin can update tickets."

    ticket_id = details.get("ticket_id")
    status = details.get("target_status")

    if not ticket_id or not status:
        return "Please specify ticket ID and target status clearly."

    try:
        ticket = update_ticket_status(db, ticket_id, status)
    except TicketTransitionError as exc:
        return str(exc)
    except ValueError as exc:
        return str(exc)

    if not ticket:
        return f"Ticket #{ticket_id} not found."

    return f"Ticket #{ticket.id} updated to {ticket.status}"


_HIGH_PRIORITY_KEYWORDS = (
    "production", "prod ", "critical", "blocked", "blocker",
    "cannot work", "can't work", "down", "outage", "nothing works",
    "completely broken", "urgent", "asap", "p1",
)
_MEDIUM_PRIORITY_KEYWORDS = (
    "slow", "laggy", "lagging", "degraded", "intermittent",
    "occasionally", "sometimes fails", "keeps disconnecting",
)


def _detect_priority(message: str, current: str | None) -> str:
    """Keyword-based priority detection with a safe medium default.

    The extractor already proposes a priority; we only escalate (low->med,
    low/med->high) when the message text clearly signals severity. We never
    downgrade a priority that the LLM already set.
    """
    msg = (message or "").lower()

    if any(kw in msg for kw in _HIGH_PRIORITY_KEYWORDS):
        return "high"

    if current in {"high", "critical"}:
        return current

    if any(kw in msg for kw in _MEDIUM_PRIORITY_KEYWORDS):
        return "medium"

    return current or "medium"


# Minimal known-outage / maintenance stub. In production this should be
# backed by a table / status feed. Keeping it in-process and lightweight so
# the chat can deflect duplicate noise without plumbing a new DB model.
KNOWN_ISSUES: dict[str, str] = {
    # "vpn": "The corporate VPN is undergoing maintenance until 9pm IST today.",
}


def _check_known_outage(issue_type: str) -> str | None:
    return KNOWN_ISSUES.get((issue_type or "").lower())


def _execute_create_ticket(details: dict[str, Any], db, user) -> str:
    if user.role not in {"employee", "manager", "it", "it_team", "admin"}:
        return "Access denied. You cannot create IT tickets."

    issue_type = details.get("issue_type") or "general"
    if issue_type == "general":
        return (
            "Sure, I can raise an IT ticket for you. Could you tell me which "
            "area the problem is in — laptop, VPN, Outlook, printer, network, "
            "or software?"
        )

    # Known-issue / maintenance deflection — avoid duplicate tickets for
    # problems IT is already aware of.
    outage_note = _check_known_outage(issue_type)
    if outage_note:
        return (
            f"Heads-up before I raise a ticket: {outage_note} "
            "You don't need to raise a new ticket for this. "
            "Reply \"raise it anyway\" if you still want me to create one."
        )

    # Auto-detect priority from the message text.
    description = details.get("original_message") or ""
    priority = _detect_priority(description, details.get("priority"))

    ticket, duplicate = create_ticket(
        db=db,
        user_id=user.email,
        issue_type=issue_type,
        description=description,
        priority=priority,
    )

    if duplicate:
        return (
            f"You already have an open {duplicate.issue_type} ticket — "
            f"Ticket #{duplicate.id} (status: {duplicate.status}). I've linked "
            "your message to that one so IT has the full context. "
            "Reply \"raise a new one\" if you need a separate ticket."
        )

    return (
        "Your IT ticket has been created and routed to the support team.\n"
        f"Ticket ID: #{ticket.id}\n"
        f"Issue type: {ticket.issue_type}\n"
        f"Priority: {ticket.priority}\n"
        f"Status: {ticket.status}\n"
        "You'll receive an email once an engineer picks it up."
    )


def _execute_asset_request(details: dict[str, Any], db, user) -> str:
    asset_type = details.get("asset_type")

    if not asset_type or asset_type == "null":
        return "Please specify asset type: laptop, monitor, keyboard, mouse, vpn token, or software license."

    request = create_asset_request(
        db=db,
        user_id=user.email,
        asset_type=asset_type,
        reason=details.get("original_message"),
    )

    manager = db.query(Employee).filter(Employee.id == user.manager_id).first()

    if manager:
        send_email(
            to=manager.email,
            subject="Asset Request Approval Required",
            body=(
                f"Hello {manager.name},\n\n"
                f"{user.name} has requested an asset.\n\n"
                f"Request ID: #{request.id}\n"
                f"Asset: {request.asset_type}\n"
                f"Reason: {details.get('original_message')}\n\n"
                f"Please login to CopilotAI and approve or reject.\n\n"
                f"Commands:\n"
                f"approve asset {request.id}\n"
                f"reject asset {request.id}"
            ),
            channel="asset",
        )

    return (
        "Asset request created successfully.\n"
        f"Request ID: #{request.id}\n"
        f"Asset: {request.asset_type}\n"
        f"Manager Approval: {request.manager_status}\n"
        f"IT Approval: {request.it_status}\n"
        f"Final Status: {request.final_status}"
    )


def _execute_asset_action(details: dict[str, Any], db, user) -> str:
    action_type = details["action_type"]
    request_id = details.get("request_id")

    if not request_id:
        return "Please provide request ID."

    if action_type == "cancel_asset_request":
        request = cancel_asset_request(db, request_id, user.email)
        if not request:
            return f"Asset request #{request_id} not found."
        if request == "not_allowed":
            return "Only pending asset requests can be cancelled."
        return f"Asset request #{request.id} cancelled successfully."

    if action_type == "manager_approve_asset":
        if user.role not in MANAGER_ROLES:
            return "Access denied. Only managers or admin can approve asset requests."
        request = approve_asset_by_manager(db, request_id, user.id)
        if not request:
            return "Asset request not found, already processed, or not assigned to you."
        return f"Asset request #{request.id} approved by manager. Sent to IT for approval."

    if action_type == "manager_reject_asset":
        if user.role not in MANAGER_ROLES:
            return "Access denied. Only managers or admin can reject asset requests."
        request = reject_asset_by_manager(db, request_id, user.id)
        if not request:
            return "Asset request not found, already processed, or not assigned to you."
        return f"Asset request #{request.id} rejected by manager."

    if action_type == "it_approve_asset":
        if user.role not in IT_ROLES:
            return "Access denied. Only IT team or admin can approve assets."
        request = approve_asset_by_it(db, request_id)
        if request == "inventory_not_found":
            return "Asset request rejected because this asset type does not exist in inventory."
        if request == "inventory_unavailable":
            return "Asset request approved by IT, but inventory is unavailable. Status set to waiting_for_stock."
        if not request:
            return "Asset request not found or manager approval is still pending."
        return (
            f"Asset request #{request.id} approved by IT.\n"
            f"Inventory Status: {request.inventory_status}\n"
            f"Final Status: {request.final_status}"
        )

    if action_type == "it_reject_asset":
        if user.role not in IT_ROLES:
            return "Access denied. Only IT team or admin can reject assets."
        request = reject_asset_by_it(db, request_id)
        if not request:
            return "Asset request not found or manager approval is still pending."
        return f"Asset request #{request.id} rejected by IT."

    return "Unsupported asset action."


def _log_action_name(details: dict[str, Any]) -> str:
    action_type = details["action_type"]
    target_status = details.get("target_status")

    if action_type == "create_ticket":
        return "ticket_created"
    if action_type == "asset_request":
        return "asset_requested"
    if action_type == "ticket_update":
        if target_status == "rejected":
            return "ticket_rejected"
        if target_status in ("resolved", "closed"):
            return "ticket_resolved"
        return "ticket_updated"
    if action_type == "cancel_asset_request":
        return "asset_cancelled"
    if action_type == "manager_approve_asset":
        return "asset_manager_approved"
    if action_type == "manager_reject_asset":
        return "asset_rejected"
    if action_type == "it_approve_asset":
        return "asset_it_approved"
    if action_type == "it_reject_asset":
        return "asset_rejected"

    return action_type


def _status_from_response(response: str) -> str:
    if response.startswith("Access denied"):
        return "access_denied"
    if "not found" in response.lower() or "unsupported" in response.lower():
        return "failed"
    return "success"


def _execute_confirmed(
    details: dict[str, Any],
    db,
    user,
    session_state: AgentSessionState | None = None,
) -> str:
    action_type = details["action_type"]

    if action_type == "create_ticket":
        response = _execute_create_ticket(details, db, user)
    elif action_type == "asset_request":
        response = _execute_asset_request(details, db, user)
    elif action_type == "ticket_update":
        response = _execute_ticket_update(details, db, user)
    elif action_type in {
        "cancel_asset_request",
        "manager_approve_asset",
        "manager_reject_asset",
        "it_approve_asset",
        "it_reject_asset",
    }:
        response = _execute_asset_action(details, db, user)
    else:
        response = "Unsupported confirmed action."

    _set_last_action(
        session_state,
        _log_action_name(details),
        _status_from_response(response),
    )
    return response


def _handle_read_action(details: dict[str, Any], db, user) -> str | None:
    action_type = details["action_type"]

    if action_type in ("ticket_status", "all_ticket_status"):
        if user.role in IT_ROLES:
            return _format_tickets(get_all_tickets(db))
        return _format_tickets(get_user_tickets(db, user.email))

    if action_type == "open_tickets":
        if user.role in IT_ROLES:
            return _format_tickets(get_open_tickets(db))
        tickets = [
            t for t in get_user_tickets(db, user.email)
            if t.status in ("open", "in_progress")
        ]
        return _format_tickets(tickets)

    if action_type == "asset_status":
        return _format_asset_requests(get_asset_requests(db, user.email))

    if action_type == "manager_pending_asset_approvals":
        if user.role not in MANAGER_ROLES:
            return "Access denied. Only managers or admin can view pending asset approvals."
        return _format_asset_requests(get_pending_asset_requests_for_manager(db, user.id))

    if action_type == "it_pending_asset_approvals":
        if user.role not in IT_ROLES:
            return "Access denied. Only IT team or admin can view IT asset approvals."
        return _format_asset_requests(get_pending_assets_for_it(db))

    if action_type == "all_asset_status":
        if user.role != "admin":
            return "Access denied. Only admin can view all asset requests."
        return _format_asset_requests(get_all_asset_requests(db))

    if action_type == "manager_asset_status":
        if user.role not in MANAGER_ROLES:
            return "Access denied. Only managers or admin can view team asset requests."
        return _format_asset_requests(get_asset_requests_for_manager(db, user.id))

    return None


def it_agent(
    message: str,
    db,
    user,
    history=None,
    session_state: AgentSessionState | None = None,
):
    if session_state:
        history = session_state.history
        session_state.set_agent("it")

    return _it_process(message, db, user, history or [], session_state=session_state)


def _it_process(
    message: str,
    db,
    user,
    history: list,
    session_state: AgentSessionState | None = None,
) -> str:
    pending = _get_pending(history, session_state=session_state)

    if pending:
        if _is_cancel(message):
            _clear_pending(history, session_state=session_state)
            return "IT action cancelled."

        if _is_confirm(message):
            _clear_pending(history, session_state=session_state)
            return _execute_confirmed(pending, db, user, session_state=session_state)

        # Slot-fill follow-up: the user's reply is meant to enrich the
        # pending action (e.g. they were asked "which area?" and replied
        # "laptop won't boot"). Re-extract from the new message, merge
        # missing fields, and re-evaluate whether we can ask for
        # confirmation now.
        new_inferred = _infer_it_details(message, user=user)
        updated = dict(pending)

        # Pull in concrete fields if the new message provided them.
        if new_inferred.get("issue_type") and new_inferred["issue_type"] != "general":
            updated["issue_type"] = new_inferred["issue_type"]
        if new_inferred.get("asset_type"):
            updated["asset_type"] = new_inferred["asset_type"]
        if new_inferred.get("priority") and new_inferred["priority"] != "medium":
            updated["priority"] = new_inferred["priority"]
        if new_inferred.get("target_status"):
            updated["target_status"] = new_inferred["target_status"]
        if new_inferred.get("ticket_id"):
            updated["ticket_id"] = new_inferred["ticket_id"]
        if new_inferred.get("request_id"):
            updated["request_id"] = new_inferred["request_id"]

        # Append the user's text to the description so the ticket carries
        # the actual problem statement, not just "I need to raise a ticket".
        prior_desc = (updated.get("original_message") or "").strip()
        if message and message.strip() and message.strip() != prior_desc:
            updated["original_message"] = (
                f"{prior_desc}\n{message.strip()}" if prior_desc else message.strip()
            )

        # If this is a create_ticket still missing the issue area, keep
        # prompting rather than confirming with ``general``.
        if updated.get("action_type") == "create_ticket" and (
            updated.get("issue_type") or "general"
        ) == "general":
            _set_pending(updated, history=history, session_state=session_state)
            return (
                "Thanks — I still need to know which area this is in: "
                "laptop, VPN, Outlook, printer, network, or software. "
                "Please reply with one of those words plus a short description."
            )

        # If this is an asset_request still missing the asset type, keep
        # prompting.
        if updated.get("action_type") == "asset_request" and not updated.get("asset_type"):
            _set_pending(updated, history=history, session_state=session_state)
            return (
                "Got it — which asset would you like? laptop, monitor, "
                "keyboard, mouse, vpn token, or software license."
            )

        _set_pending(updated, history=history, session_state=session_state)
        return _confirmation_prompt(updated)

    details = _infer_it_details(message, user=user)
    if details["action_type"] == "general":
        llm_details = extract_it_details(message)
        details = _merge_details(message, llm_details, user=user)

    read_response = _handle_read_action(details, db, user)
    if read_response is not None:
        return read_response

    if details["action_type"] == "asset_request" and not details.get("asset_type"):
        return "Please specify asset type: laptop, monitor, keyboard, mouse, vpn token, or software license."

    # Pre-confirmation slot-fill for create_ticket: never confirm a ticket
    # with ``issue_type == "general"`` — that's the symptom of the user
    # clicking "Raise IT ticket" from Quick Actions without typing any
    # specifics. Ask them which area + description first.
    if details["action_type"] == "create_ticket" and (details.get("issue_type") or "general") == "general":
        _set_pending(details, history=history, session_state=session_state)
        return (
            "Sure, I can raise an IT ticket for you. To make sure it goes to "
            "the right team, please tell me:\n\n"
            "  • Which area is the problem in? (laptop, VPN, Outlook, "
            "printer, network, or software)\n"
            "  • A short description of what's happening.\n\n"
            "Example: \"laptop won't boot — black screen since this morning\"."
        )

    precheck_error = _precheck_action(details, user)
    if precheck_error:
        _set_last_action(session_state, "access_denied", "access_denied")
        return precheck_error

    if _needs_confirmation(details):
        _set_pending(details, history=history, session_state=session_state)
        return _confirmation_prompt(details)

    if details["action_type"] == "ticket_update":
        response = _execute_ticket_update(details, db, user)
        _set_last_action(
            session_state,
            _log_action_name(details),
            _status_from_response(response),
        )
        return response

    if details["action_type"] in {
        "cancel_asset_request",
        "manager_approve_asset",
        "manager_reject_asset",
        "it_approve_asset",
        "it_reject_asset",
    }:
        response = _execute_asset_action(details, db, user)
        _set_last_action(
            session_state,
            _log_action_name(details),
            _status_from_response(response),
        )
        return response

    llm = get_llm()
    response = llm.invoke(f"Help with this IT support issue: {message}")
    return response.content
    return response.content

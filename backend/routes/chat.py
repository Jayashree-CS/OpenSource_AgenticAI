import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from db.database import SessionLocal
from db.models import (
    Employee,
    LeaveRequest,
    Ticket,
    AssetRequest,
    Inventory,
)
from actions.auth_action import verify_password, create_access_token, hash_password
from llm import get_llm
from actions.auth_dependency import get_current_user
from actions.log_action import create_log, get_logs

from rag.retriever import retrieve_docs
from actions.enhanced_date_action import get_today, get_today_text, get_day_name, get_tomorrow

from agents.hr_agent import hr_agent
from agents.it_agent import it_agent
from graph_structure.graph import build_graph
from graph_structure.state import agent_state_store
from services.orchestrator import orchestrate
from services.scope_guard import evaluate as evaluate_scope

router = APIRouter()
graph = build_graph()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: str | None = None
    name: str | None = None
    email: str | None = None
    role: str | None = None
    message: str | None = None


class RegisterRequest(BaseModel):
    # Frontend currently sends `username` (email address).
    email: str | None = None
    username: str | None = None
    password: str
    name: str | None = None
    role: str = "employee"


# Request schema
class ChatRequest(BaseModel):
    message: str
    token: str | None = None


# Response schema
class ChatResponse(BaseModel):
    reply: str


def _general_prompt(session_state, message: str) -> str:
    history = session_state.history_text(limit=8)
    today_text = get_today_text()
    return f"""
You are CopilotAI, an internal enterprise assistant. Your scope is strictly:
HR (leave, payroll, policies, employee handbook), IT (tickets, VPN,
hardware, software, network, asset requests), and answering questions about
the company from official internal documents.

You MUST refuse — politely and briefly — any request that is outside this
scope, including but not limited to: cooking / recipes, weather, sports,
movies, music, current events, news, jokes, free-form coding help, math
homework, religion, politics, personal advice, or trivia. When refusing,
suggest the kinds of HR / IT / company-policy questions you can help with.

You MUST NEVER reveal another employee's leave, ticket, or asset records.
Only summarise records belonging to the current user, unless the
conversation history clearly shows the user is a manager/admin acting on
their own team. {today_text}.

Never invent company facts. If the answer is not in retrieved company
documents, reply exactly: "I could not find this in company documents."
Company name, CEO, organization details, and policy facts MUST come from
retrieved documents, not from prior knowledge.

Conversation history:
{history}

Current message:
{message}
"""


_HR_PENDING_TYPES = {"leave_application", "leave_approval", "hr_leave"}
_IT_PENDING_TYPES = {"it_action", "it_ticket", "asset_request"}


def _has_pending_hr(session_state) -> bool:
    pw = getattr(session_state, "pending_workflow", None) or {}
    return isinstance(pw, dict) and pw.get("type") in _HR_PENDING_TYPES


def _has_pending_it(session_state) -> bool:
    pw = getattr(session_state, "pending_workflow", None) or {}
    return isinstance(pw, dict) and pw.get("type") in _IT_PENDING_TYPES


def _date_answer(message: str) -> str | None:
    """Pure date utilities. Company / CEO / organization answers go through
    the RAG pipeline (see ``_answer_general_question``) and are NEVER
    short-circuited from constants here.
    """
    msg = message.lower()
    if (
        "what day is today" in msg
        or "what is today" in msg
        or "today's date" in msg
        or "todays date" in msg
    ):
        return get_today_text()
    return None


def _answer_general_question(session_state, message: str, role: str | None = None) -> str:
    if answer := _date_answer(message):
        return answer

    docs = retrieve_docs(message, k=5, role=role)
    if not docs:
        return "I could not find this in company documents."

    context = "\n\n---\n\n".join(docs)
    history = session_state.history_text(limit=8)
    tomorrow = get_tomorrow()
    llm = get_llm("groq_fast")
    prompt = f"""
You are CopilotAI, an internal enterprise assistant. Your scope is strictly
HR / IT / company-policy questions answered from internal documents.

Today is {get_day_name(get_today())}, {get_today().isoformat()}.
Tomorrow is {get_day_name(tomorrow)}, {tomorrow.isoformat()}.

Hard rules:
1. Answer using ONLY the company document context below. Do NOT use prior
   knowledge about the company, its CEO, its organization, or any external
   facts. If the document context does not answer the question, reply
   exactly: "I could not find this in company documents."
2. Refuse — politely and briefly — anything outside HR / IT / policy /
   asset / company info (e.g. cooking, weather, sports, jokes, coding
   help, news, politics). When refusing, redirect the user to ask about
   leave, IT tickets, asset requests, or company policies.
3. Never reveal another employee's leave, ticket, or asset records.
4. Never quote, list, or reference confidential or admin-only material
   unless the retrieved context explicitly contains it for this user.

Conversation history:
{history}

Company document context:
{context}

User question:
{message}
"""
    return llm.invoke(prompt).content.strip()


def _is_contextual_follow_up(message: str) -> bool:
    return message.strip().lower() in {
        "show status",
        "status",
        "track status",
        "show history",
        "history",
        "my requests",
        "my status",
    }


def _rows_or_empty(rows: list[str], empty: str) -> str:
    return "\n".join(rows) if rows else empty


def _format_employees(db: Session) -> str:
    employees = db.query(Employee).order_by(Employee.id).all()
    return _rows_or_empty(
        [
            f"Employee #{e.id}: {e.name} | {e.email} | Role: {e.role} | Dept: {e.department or '-'} | Manager: {e.manager_id or '-'}"
            for e in employees
        ],
        "No employees found.",
    )


def _format_leaves(db: Session, pending_only: bool = False) -> str:
    query = db.query(LeaveRequest)
    if pending_only:
        query = query.filter(LeaveRequest.status.in_(["pending_manager", "pending_hr"]))
    leaves = query.order_by(LeaveRequest.id).all()
    return _rows_or_empty(
        [
            f"Leave #{l.id}: Employee {l.employee_id} | {l.leave_type} | {l.start_date} to {l.end_date} | Days: {l.total_days} | Status: {l.status}"
            for l in leaves
        ],
        "No leave requests found.",
    )


def _format_tickets(db: Session, open_only: bool = False) -> str:
    query = db.query(Ticket)
    if open_only:
        query = query.filter(Ticket.status.in_(["open", "in_progress"]))
    tickets = query.order_by(Ticket.id).all()
    return _rows_or_empty(
        [
            f"Ticket #{t.id}: {t.issue_type} | User: {t.user_id} | Priority: {t.priority} | Status: {t.status}"
            for t in tickets
        ],
        "No IT tickets found.",
    )


def _format_assets(db: Session, pending_manager: bool = False, pending_it: bool = False) -> str:
    query = db.query(AssetRequest)
    if pending_manager:
        query = query.filter(AssetRequest.manager_status == "pending")
    if pending_it:
        query = query.filter(
            AssetRequest.manager_status == "approved",
            AssetRequest.it_status == "pending",
        )
    assets = query.order_by(AssetRequest.id.desc()).all()
    return _rows_or_empty(
        [
            f"Asset #{a.id}: {a.asset_type} | User: {a.user_id} | Manager: {a.manager_status} | IT: {a.it_status} | Final: {a.final_status}"
            for a in assets
        ],
        "No asset requests found.",
    )


def _format_inventory(db: Session, low_stock: bool = False) -> str:
    query = db.query(Inventory)
    if low_stock:
        query = query.filter(Inventory.available_quantity <= 2)
    items = query.order_by(Inventory.id).all()
    return _rows_or_empty(
        [
            f"Inventory #{i.id}: {i.asset_type} | Total: {i.total_quantity} | Available: {i.available_quantity} | Reserved: {i.total_quantity - i.available_quantity}"
            for i in items
        ],
        "No inventory items found.",
    )


def _format_logs(db: Session, agent_only: bool = False) -> str:
    logs = get_logs(db)[:25]
    if agent_only:
        logs = [log for log in logs if log.agent]
    return _rows_or_empty(
        [
            f"Log #{log.id}: {log.created_at} | {log.user_email} | Agent: {log.agent} | Action: {log.action} | Status: {log.status}"
            for log in logs
        ],
        "No logs found.",
    )


def _format_summary(db: Session) -> str:
    return (
        "Dashboard Summary:\n"
        f"Employees: {db.query(Employee).count()}\n"
        f"Leave requests: {db.query(LeaveRequest).count()}\n"
        f"Pending leaves: {db.query(LeaveRequest).filter(LeaveRequest.status.in_(['pending_manager', 'pending_hr'])).count()}\n"
        f"Tickets: {db.query(Ticket).count()}\n"
        f"Open tickets: {db.query(Ticket).filter(Ticket.status.in_(['open', 'in_progress'])).count()}\n"
        f"Asset requests: {db.query(AssetRequest).count()}\n"
        f"Pending assets: {db.query(AssetRequest).filter(AssetRequest.final_status.in_(['pending', 'pending_it_approval'])).count()}\n"
        f"Inventory items: {db.query(Inventory).count()}\n"
        f"System logs: {len(get_logs(db))}"
    )


_PENDING_LEAVE_STATUSES = ("pending_manager", "pending_hr", "pending")
_APPROVED_LEAVE_STATUSES = ("approved",)
_PENDING_TICKET_STATUSES = ("open", "in_progress")
_RESOLVED_TICKET_STATUSES = ("resolved", "closed")


def _format_user_leaves(rows) -> list[str]:
    return [
        f"  • Leave #{l.id}: {l.leave_type} | {l.start_date} → {l.end_date} | {l.status}"
        for l in rows
    ]


def _format_user_tickets(rows) -> list[str]:
    return [
        f"  • Ticket #{t.id}: {t.issue_type} | priority: {t.priority} | {t.status}"
        for t in rows
    ]


def _format_user_assets(rows) -> list[str]:
    return [
        f"  • Asset #{a.id}: {a.asset_type} | manager: {a.manager_status} | IT: {a.it_status} | final: {a.final_status}"
        for a in rows
    ]


def _user_pending_summary(db: Session, user: Employee) -> str:
    """Show MY pending leaves + tickets + asset requests, newest first."""
    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == user.id,
            LeaveRequest.status.in_(_PENDING_LEAVE_STATUSES),
        )
        .order_by(LeaveRequest.id.desc())
        .all()
    )
    tickets = (
        db.query(Ticket)
        .filter(
            Ticket.user_id == user.email,
            Ticket.status.in_(_PENDING_TICKET_STATUSES),
        )
        .order_by(Ticket.id.desc())
        .all()
    )
    assets = (
        db.query(AssetRequest)
        .filter(
            AssetRequest.user_id == user.email,
            AssetRequest.final_status.in_(("pending", "pending_it_approval")),
        )
        .order_by(AssetRequest.id.desc())
        .all()
    )

    sections = []
    sections.append("Leave requests:")
    sections.extend(_format_user_leaves(leaves) or ["  • None pending"])
    sections.append("\nIT tickets:")
    sections.extend(_format_user_tickets(tickets) or ["  • None pending"])
    sections.append("\nAsset requests:")
    sections.extend(_format_user_assets(assets) or ["  • None pending"])
    if not (leaves or tickets or assets):
        return "You have no pending requests right now."
    return "Here's everything you have pending:\n\n" + "\n".join(sections)


def _user_approved_summary(db: Session, user: Employee) -> str:
    """Show MY approved leaves + resolved tickets + fulfilled assets."""
    leaves = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.employee_id == user.id,
            LeaveRequest.status.in_(_APPROVED_LEAVE_STATUSES),
        )
        .order_by(LeaveRequest.id.desc())
        .all()
    )
    tickets = (
        db.query(Ticket)
        .filter(
            Ticket.user_id == user.email,
            Ticket.status.in_(_RESOLVED_TICKET_STATUSES),
        )
        .order_by(Ticket.id.desc())
        .all()
    )
    assets = (
        db.query(AssetRequest)
        .filter(
            AssetRequest.user_id == user.email,
            AssetRequest.final_status.in_(("approved", "fulfilled")),
        )
        .order_by(AssetRequest.id.desc())
        .all()
    )

    sections = []
    sections.append("Approved leaves:")
    sections.extend(_format_user_leaves(leaves) or ["  • None"])
    sections.append("\nResolved/closed tickets:")
    sections.extend(_format_user_tickets(tickets) or ["  • None"])
    sections.append("\nApproved/fulfilled assets:")
    sections.extend(_format_user_assets(assets) or ["  • None"])
    if not (leaves or tickets or assets):
        return "You don't have any approved requests yet."
    return "Here's the status of your approved requests:\n\n" + "\n".join(sections)


def _manager_pending_queue(db: Session, manager: Employee) -> str:
    """For managers: leaves waiting on this manager + asset requests
    waiting on this manager. Admins see all rows via the helper.
    """
    from actions.leave_action import get_pending_leaves_for_manager
    from actions.asset_action import get_pending_asset_requests_for_manager

    leaves = get_pending_leaves_for_manager(db, manager.id) or []
    assets = get_pending_asset_requests_for_manager(db, manager.id) or []

    sections = ["Leave approvals waiting on you:"]
    sections.extend(_format_user_leaves(leaves) or ["  • None"])
    sections.append("\nAsset approvals waiting on you:")
    sections.extend(_format_user_assets(assets) or ["  • None"])
    if not (leaves or assets):
        return "You have no pending approvals right now."
    return "Here's your approvals queue:\n\n" + "\n".join(sections)


def _admin_pending_queue(db: Session) -> str:
    """For admins: every still-open approval in the system."""
    leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.status.in_(_PENDING_LEAVE_STATUSES))
        .order_by(LeaveRequest.id.desc())
        .all()
    )
    tickets = (
        db.query(Ticket)
        .filter(Ticket.status.in_(_PENDING_TICKET_STATUSES))
        .order_by(Ticket.id.desc())
        .all()
    )
    assets = (
        db.query(AssetRequest)
        .filter(
            (AssetRequest.manager_status == "pending")
            | (
                (AssetRequest.manager_status == "approved")
                & (AssetRequest.it_status == "pending")
            )
        )
        .order_by(AssetRequest.id.desc())
        .all()
    )

    sections = ["Pending leaves:"]
    sections.extend(_format_user_leaves(leaves) or ["  • None"])
    sections.append("\nOpen IT tickets:")
    sections.extend(_format_user_tickets(tickets) or ["  • None"])
    sections.append("\nPending asset approvals:")
    sections.extend(_format_user_assets(assets) or ["  • None"])
    if not (leaves or tickets or assets):
        return "There are no pending approvals in the system."
    return "System-wide pending approvals:\n\n" + "\n".join(sections)


def _it_team_pending_queue(db: Session) -> str:
    """For IT-team users: list every open ticket + every asset request
    that has been manager-approved and is now waiting on IT.
    """
    tickets = (
        db.query(Ticket)
        .filter(Ticket.status.in_(_PENDING_TICKET_STATUSES))
        .order_by(Ticket.id.desc())
        .all()
    )
    assets = (
        db.query(AssetRequest)
        .filter(
            AssetRequest.manager_status == "approved",
            AssetRequest.it_status == "pending",
        )
        .order_by(AssetRequest.id.desc())
        .all()
    )

    sections = ["Pending IT tickets:"]
    sections.extend(_format_user_tickets(tickets) or ["  • None"])
    sections.append("\nPending asset approvals (manager-approved → waiting on IT):")
    sections.extend(_format_user_assets(assets) or ["  • None"])
    if not (tickets or assets):
        return "IT queue is empty — no open tickets and no asset approvals waiting."
    return "Here's the IT team queue:\n\n" + "\n".join(sections)


def _user_full_history(db: Session, user: Employee) -> str:
    """Show ALL leaves the user has applied for, newest first."""
    leaves = (
        db.query(LeaveRequest)
        .filter(LeaveRequest.employee_id == user.id)
        .order_by(LeaveRequest.id.desc())
        .all()
    )
    if not leaves:
        return "You haven't applied for any leave yet."
    rows = "\n".join(
        f"  • Leave #{l.id}: {l.leave_type} | {l.start_date} → {l.end_date} | "
        f"{l.total_days} day(s) | {l.status}"
        for l in leaves
    )
    return f"All leaves you've applied for ({len(leaves)} total, newest first):\n\n{rows}"


_CANCEL_LEAVE_RE = re.compile(r"\bcancel\s+leave\b", re.IGNORECASE)
_LEAVE_ID_DIGIT_RE = re.compile(r"\b\d+\b")


def _capability_response(message: str, db: Session, user: Employee) -> str | None:
    """Top-level shortcuts for the documented employee capabilities.

    These run before the LangGraph router so the wording the team uses in
    the spec ("show pending requests", "show approval status",
    "view leave history") never gets misclassified into a free-form LLM
    answer.
    """
    msg = (message or "").strip().lower()
    if not msg:
        return None

    # Skip while a multi-turn workflow is open — the agents need to handle
    # follow-ups like "yes" / "no" themselves.
    if user is None:
        return None

    # 1. View leave history → ALL leaves applied (no truncation)
    if msg in {
        "view leave history",
        "leave history",
        "my leave history",
        "show my leave history",
        "show leave history",
        "all my leaves",
        "all leaves applied",
        "show all my leaves",
    }:
        return _user_full_history(db, user)

    # 2. Check pending requests → leaves + tickets + assets
    pending_phrases = (
        "show pending leave",
        "show pending leaves",
        "show pending ticket",
        "show pending tickets",
        "show pending asset",
        "show pending assets",
        "show pending approvals",
        "show all pending approvals",
        "show all pending",
        "all pending approvals",
        "all pending requests",
        "show my pending",
        "my pending requests",
        "pending requests",
        "check pending requests",
        "what is pending",
        "what's pending",
    )
    if any(p in msg for p in pending_phrases):
        # Role-specific routing:
        #   admin   -> system-wide pending approvals (leaves + assets + tickets)
        #   manager -> team's pending leaves + asset approvals waiting on manager
        #   it_team -> all open tickets + asset approvals waiting on IT
        #   employee -> personal pending summary (their own requests)
        if user.role == "admin":
            return _admin_pending_queue(db)
        if user.role == "manager":
            return _manager_pending_queue(db, user)
        if user.role in {"it", "it_team"}:
            return _it_team_pending_queue(db)
        if user.role == "employee":
            return _user_pending_summary(db, user)

    # 3. Check approval status → approved leaves + tickets + assets
    approved_phrases = (
        "show approved leave",
        "show approved leaves",
        "show approved ticket",
        "show approved tickets",
        "show approved asset",
        "show approved assets",
        "check approval status",
        "approval status",
        "show approval status",
        "show my approved",
        "my approved",
    )
    if any(p in msg for p in approved_phrases):
        if user.role in {"employee", "it", "it_team", "manager"}:
            return _user_approved_summary(db, user)

    # 4. Cancel leave request → ask user to provide id when missing.
    #    When an id IS provided, _action_command_response handles it.
    if _CANCEL_LEAVE_RE.search(msg) and not _LEAVE_ID_DIGIT_RE.search(msg):
        return (
            "Sure — which leave should I cancel? Please give me the leave ID, "
            "for example: `cancel leave 12`. You can run `view leave history` "
            "if you want to look up the ID."
        )

    return None


# ---------------------------------------------------------------------------
# Action command dispatcher
# ---------------------------------------------------------------------------
# Handles imperative commands the user can issue from chat:
#   • cancel leave <id>           — employee on own leave, or admin
#   • approve leave <id>          — manager / admin
#   • reject  leave <id>          — manager / admin
#   • approve ticket <id>         — IT / admin (marks resolved)
#   • reject  ticket <id>         — IT / admin (marks rejected)
#   • close   ticket <id>         — IT / admin (marks closed)
#   • approve asset <id>          — manager OR IT depending on current stage
#   • reject  asset <id>          — manager OR IT depending on current stage
#
# RBAC is enforced explicitly here so employees can never reach the
# approve/reject paths — they get an immediate refusal instead of falling
# through to RAG.
# ---------------------------------------------------------------------------

_APPROVE_LEAVE_RE = re.compile(r"\bapprove\s+leave\s+#?(\d+)\b", re.IGNORECASE)
_REJECT_LEAVE_RE = re.compile(r"\breject\s+leave\s+#?(\d+)\b", re.IGNORECASE)
_CANCEL_LEAVE_ID_RE = re.compile(r"\bcancel\s+leave\s+#?(\d+)\b", re.IGNORECASE)

_APPROVE_TICKET_RE = re.compile(
    r"\b(?:approve|resolve)\s+ticket\s+#?(\d+)\b", re.IGNORECASE
)
_REJECT_TICKET_RE = re.compile(r"\breject\s+ticket\s+#?(\d+)\b", re.IGNORECASE)
_CLOSE_TICKET_RE = re.compile(r"\bclose\s+ticket\s+#?(\d+)\b", re.IGNORECASE)

_APPROVE_ASSET_RE = re.compile(r"\bapprove\s+asset\s+#?(\d+)\b", re.IGNORECASE)
_REJECT_ASSET_RE = re.compile(r"\breject\s+asset\s+#?(\d+)\b", re.IGNORECASE)

_MANAGER_ROLES = {"manager", "admin"}
_IT_ROLES = {"it", "it_team", "admin"}


def _action_command_response(
    message: str, db: Session, user: Employee, session_state
) -> str | None:
    """Run before the LangGraph router so deterministic action commands
    never get misclassified into RAG or generic LLM answers.
    """
    if not message or user is None:
        return None
    msg = message.strip()

    # Hard RBAC gate: employees can never run approve/reject on
    # anything — refuse before we even look up the record so they don't
    # learn its existence or state.
    looks_like_approve_reject = bool(
        re.search(r"\b(approve|reject|resolve|close)\s+(leave|ticket|asset)\b", msg, re.IGNORECASE)
    )
    if looks_like_approve_reject and user.role == "employee":
        return (
            "Access denied. Employees cannot approve or reject requests. "
            "Please contact your manager or the IT team."
        )

    # ----- LEAVE ------------------------------------------------------
    m = _APPROVE_LEAVE_RE.search(msg)
    if m:
        leave_id = int(m.group(1))
        if user.role not in _MANAGER_ROLES:
            return "Access denied. Only managers or admin can approve leave requests."
        from actions.leave_action import approve_leave_by_manager
        result = approve_leave_by_manager(db, leave_id, user.id)
        if result is None:
            return f"Leave #{leave_id} not found, already processed, or outside your team."
        return f"Leave request #{leave_id} approved."

    m = _REJECT_LEAVE_RE.search(msg)
    if m:
        leave_id = int(m.group(1))
        if user.role not in _MANAGER_ROLES:
            return "Access denied. Only managers or admin can reject leave requests."
        from actions.leave_action import reject_leave_by_manager
        result = reject_leave_by_manager(db, leave_id, user.id)
        if result is None:
            return f"Leave #{leave_id} not found, already processed, or outside your team."
        return f"Leave request #{leave_id} rejected."

    m = _CANCEL_LEAVE_ID_RE.search(msg)
    if m:
        leave_id = int(m.group(1))
        # Employees can cancel their own pending leaves; admins can cancel any.
        from actions.leave_action import cancel_leave
        if user.role == "admin":
            owner = (
                db.query(LeaveRequest)
                .filter(LeaveRequest.id == leave_id)
                .first()
            )
            if not owner:
                return f"Leave #{leave_id} not found."
            target_employee_id = owner.employee_id
        else:
            target_employee_id = user.id
        result = cancel_leave(db, target_employee_id, leave_id)
        if result is None:
            return f"Leave #{leave_id} not found, or it doesn't belong to you."
        if result == "not_allowed":
            return (
                f"Leave #{leave_id} can't be cancelled — it's already been "
                "approved, rejected, or cancelled."
            )
        return f"Leave request #{leave_id} cancelled."

    # ----- TICKETS ----------------------------------------------------
    def _update_ticket(ticket_id: int, target_status: str, verb_past: str) -> str:
        if user.role not in _IT_ROLES:
            return "Access denied. Only IT team or admin can update tickets."
        from actions.it_action import update_ticket_status, TicketTransitionError
        try:
            ticket = update_ticket_status(
                db, ticket_id, target_status,
                user_role=user.role, user_id=str(user.id),
            )
        except TicketTransitionError as exc:
            return str(exc)
        except ValueError as exc:
            return str(exc)
        if ticket is None:
            return f"Ticket #{ticket_id} not found, or you don't have permission to update it."
        return f"Ticket #{ticket.id} {verb_past} (status: {ticket.status})."

    m = _APPROVE_TICKET_RE.search(msg)
    if m:
        return _update_ticket(int(m.group(1)), "resolved", "resolved")

    m = _CLOSE_TICKET_RE.search(msg)
    if m:
        return _update_ticket(int(m.group(1)), "closed", "closed")

    m = _REJECT_TICKET_RE.search(msg)
    if m:
        return _update_ticket(int(m.group(1)), "rejected", "rejected")

    # ----- ASSETS -----------------------------------------------------
    # An asset can be approved/rejected by either the manager (first
    # stage) or IT (second stage). We pick the right handler based on
    # the request's current state — that way the user doesn't have to
    # remember which stage it's in.
    def _resolve_asset_stage(request_id: int) -> tuple[AssetRequest | None, str | None]:
        req = (
            db.query(AssetRequest)
            .filter(AssetRequest.id == request_id)
            .first()
        )
        if req is None:
            return None, None
        if req.manager_status == "pending":
            return req, "manager"
        if req.manager_status == "approved" and req.it_status == "pending":
            return req, "it"
        return req, "done"

    m = _APPROVE_ASSET_RE.search(msg)
    if m:
        request_id = int(m.group(1))
        req, stage = _resolve_asset_stage(request_id)
        if req is None:
            return f"Asset request #{request_id} not found."
        if stage == "done":
            return (
                f"Asset request #{request_id} has already been processed "
                f"(manager: {req.manager_status}, IT: {req.it_status})."
            )
        if stage == "manager":
            if user.role not in _MANAGER_ROLES:
                return "Access denied. This asset needs manager approval first."
            from actions.asset_action import approve_asset_by_manager
            result = approve_asset_by_manager(db, request_id, user.id)
            if result is None:
                return f"Asset request #{request_id} is outside your team or not pending manager approval."
            return f"Asset request #{request_id} approved by you. Now waiting on IT."
        # stage == "it"
        if user.role not in _IT_ROLES:
            return "Access denied. This asset is now awaiting IT approval."
        from actions.asset_action import approve_asset_by_it
        result = approve_asset_by_it(db, request_id, it_user_id=user.email)
        if result is None:
            return f"Asset request #{request_id} could not be approved (inventory or permission issue)."
        return f"Asset request #{request_id} approved by IT and fulfilled."

    m = _REJECT_ASSET_RE.search(msg)
    if m:
        request_id = int(m.group(1))
        req, stage = _resolve_asset_stage(request_id)
        if req is None:
            return f"Asset request #{request_id} not found."
        if stage == "done":
            return (
                f"Asset request #{request_id} has already been processed "
                f"(manager: {req.manager_status}, IT: {req.it_status})."
            )
        if stage == "manager":
            if user.role not in _MANAGER_ROLES:
                return "Access denied. Only managers or admin can reject this asset."
            from actions.asset_action import reject_asset_by_manager
            result = reject_asset_by_manager(db, request_id, user.id)
            if result is None:
                return f"Asset request #{request_id} is outside your team or not pending manager approval."
            return f"Asset request #{request_id} rejected by manager."
        # stage == "it"
        if user.role not in _IT_ROLES:
            return "Access denied. Only IT team or admin can reject this asset."
        from actions.asset_action import reject_asset_by_it
        result = reject_asset_by_it(db, request_id, it_user_id=user.email)
        if result is None:
            return f"Asset request #{request_id} could not be rejected."
        return f"Asset request #{request_id} rejected by IT."

    return None


def _admin_command_response(message: str, db: Session, user: Employee, session_state) -> str | None:
    msg = message.lower().strip()
    self_action_leave_terms = (
        "my leave history",
        "my pending leave",
        "my pending leaves",
        "own leave history",
        "own pending leave",
        "own pending leaves",
    )

    if any(term in msg for term in self_action_leave_terms):
        return None

    self_action_ticket_terms = (
        "my ticket",
        "my tickets",
        "ticket status",
    )

    if user.role != "admin" and any(term in msg for term in self_action_ticket_terms):
        return None

    it_ticket_terms = (
        "all tickets",
        "ticket status",
        "open tickets",
        "pending tickets",
    )

    if user.role in ("it", "it_team") and any(term in msg for term in it_ticket_terms):
        return None

    admin_terms = (
        "all employees",
        "employee profiles",
        "employee details",
        "all leave",
        "leave history",
        "leave requests",
        "pending leave",
        "all tickets",
        "ticket status",
        "open tickets",
        "pending tickets",
        "all asset",
        "asset requests",
        "manager asset approvals",
        "it asset approvals",
        "inventory",
        "low stock",
        "system logs",
        "agent activity",
        "dashboard summary",
        "analytics",
    )

    if not any(term in msg for term in admin_terms):
        return None

    if user.role in ("it", "it_team") and ("inventory" in msg or "low stock" in msg):
        session_state.set_agent("it")
        session_state.metadata["last_tool"] = "inventory_view"
        session_state.metadata["last_status"] = "success"
        if "low stock" in msg:
            session_state.metadata["last_action"] = "it_view_low_stock"
            return _format_inventory(db, low_stock=True)
        session_state.metadata["last_action"] = "it_view_inventory"
        return _format_inventory(db)

    if user.role != "admin":
        session_state.metadata["last_action"] = "access_denied"
        session_state.metadata["last_status"] = "access_denied"
        session_state.metadata["last_tool"] = "admin_command"
        return "Access denied. Only admin can use this admin view."

    session_state.set_agent("admin")
    session_state.metadata["last_tool"] = "admin_command"
    session_state.metadata["last_status"] = "success"

    if "employee" in msg:
        session_state.metadata["last_action"] = "admin_view_employees"
        return _format_employees(db)
    if "pending leave" in msg or "pending approvals" in msg:
        session_state.metadata["last_action"] = "admin_view_pending_leaves"
        return _format_leaves(db, pending_only=True)
    if "leave" in msg:
        session_state.metadata["last_action"] = "admin_view_leave_requests"
        return _format_leaves(db)
    if "open tickets" in msg or "pending tickets" in msg or "in-progress" in msg or "in progress" in msg:
        session_state.metadata["last_action"] = "admin_view_open_tickets"
        return _format_tickets(db, open_only=True)
    if "ticket" in msg:
        session_state.metadata["last_action"] = "admin_view_tickets"
        return _format_tickets(db)
    if "low stock" in msg:
        session_state.metadata["last_action"] = "admin_view_low_stock"
        return _format_inventory(db, low_stock=True)
    if "inventory" in msg:
        session_state.metadata["last_action"] = "admin_view_inventory"
        return _format_inventory(db)
    if "it asset approvals" in msg or "pending it" in msg:
        session_state.metadata["last_action"] = "admin_view_it_asset_approvals"
        return _format_assets(db, pending_it=True)
    if "manager asset approvals" in msg or "pending manager" in msg:
        session_state.metadata["last_action"] = "admin_view_manager_asset_approvals"
        return _format_assets(db, pending_manager=True)
    if "asset" in msg:
        session_state.metadata["last_action"] = "admin_view_asset_requests"
        return _format_assets(db)
    if "agent activity" in msg:
        session_state.metadata["last_action"] = "admin_view_agent_logs"
        return _format_logs(db, agent_only=True)
    if "logs" in msg or "traces" in msg:
        session_state.metadata["last_action"] = "admin_view_logs"
        return _format_logs(db)
    if "summary" in msg or "analytics" in msg:
        session_state.metadata["last_action"] = "admin_view_dashboard_summary"
        return _format_summary(db)

    return None


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(Employee).filter(Employee.email == req.email).first()

    if not user:
        return {"success": False, "message": "User not found"}

    if not verify_password(req.password, user.password_hash):
        return {"success": False, "message": "Invalid password"}

    role = _normalize_role_for_backend(user.role)
    token = create_access_token({
        "user_id": user.id,
        "email": user.email,
        "role": role
    })

    return {
        "success": True,
        "token": token,
        "name": user.name,
        "email": user.email,
        "role": role,
    }


def _normalize_role_for_backend(role: str) -> str:
    r = (role or "").strip().lower()
    if r in {"it", "itteam", "it-team", "it team", "it_team"}:
        return "it_team"
    if r in {"hr", "hrteam", "hr-team", "hr team", "hr_team"}:
        return "employee"
    if r in {"employee", "manager", "admin"}:
        return r
    return "employee"


@router.post("/register", response_model=LoginResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    email = (req.email or req.username or "").strip().lower()
    if not email:
        return {
            "success": False,
            "token": None,
            "name": None,
            "email": None,
            "role": None,
            "message": "Email/username is required.",
        }

    existing = db.query(Employee).filter(Employee.email == email).first()
    if existing:
        return {
            "success": False,
            "token": None,
            "name": None,
            "email": None,
            "role": None,
            "message": "User already exists.",
        }

    role = _normalize_role_for_backend(req.role)
    name = (req.name or email.split("@")[0] or "User").strip()
    employee = Employee(
        name=name,
        email=email,
        role=role,
        department=None,
        manager_id=None,
        password_hash=hash_password(req.password),
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    token = create_access_token(
        {
            "user_id": employee.id,
            "email": employee.email,
            "role": employee.role,
        }
    )

    return {
        "success": True,
        "token": token,
        "name": employee.name,
        "email": employee.email,
        "role": employee.role,
    }


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):

    user_key = str(user.id)
    session_state = agent_state_store.get(user_key)
    history = session_state.history

    # Orchestration preprocessing: normalize + classify intent (additive metadata
    # only; downstream agents continue to handle the heavy lifting).
    try:
        decision = orchestrate(req.message, session_state=session_state)
        session_state.metadata["intent"] = decision.intent
        session_state.metadata["intent_confidence"] = decision.confidence
        session_state.metadata["intent_source"] = decision.source
        session_state.metadata["normalized_message"] = decision.normalized.normalized
    except Exception as exc:  # pragma: no cover - defensive
        session_state.metadata["intent_error"] = str(exc)

    direct_reply = _date_answer(req.message)
    msg_lower = (req.message or "").strip().lower()

    # Out-of-scope guardrail. If the user is mid-workflow (pending HR/IT
    # action) we let the agents respond — they may need a "no" or "yes"
    # answer that is also a generic word — but for fresh messages with no
    # pending state, decline anything clearly off-topic (recipes, weather,
    # sports, jokes, etc.) with a friendly redirect.
    has_pending = _has_pending_hr(session_state) or _has_pending_it(session_state)
    if not has_pending:
        scope_decision = evaluate_scope(req.message)
        if not scope_decision.in_scope and scope_decision.redirect_message:
            session_state.set_agent("general")
            session_state.metadata["last_tool"] = "scope_guard"
            session_state.metadata["last_action"] = "out_of_scope"
            session_state.metadata["last_status"] = "declined"
            session_state.metadata["scope_topic"] = scope_decision.matched_topic
            reply = scope_decision.redirect_message
            session_state.record_exchange(req.message, reply)
            create_log(
                db=db,
                user=user,
                agent="general",
                action="out_of_scope",
                tool_used="scope_guard",
                status="declined",
                message=req.message,
                response=reply,
            )
            return {"reply": reply}

    if direct_reply:
        reply = direct_reply
        session_state.set_agent("general")
        session_state.metadata["last_tool"] = "company_date_facts"

    elif _has_pending_hr(session_state):
        # Any pending HR workflow (leave_application, leave_approval, hr_leave)
        # should keep routing follow-up messages to the HR agent so the
        # multi-turn slot-filling memory works.
        reply = hr_agent(req.message, db, user, history, session_state=session_state)

    elif _has_pending_it(session_state):
        reply = it_agent(req.message, db, user, history, session_state=session_state)

    elif msg_lower in {"yes", "y", "yeah", "yep", "no", "n", "nope", "confirm"}:
        # Guardrail: don't accidentally route bare confirmations into unrelated agents
        # when there's no pending workflow.
        reply = "I don’t have anything pending to confirm right now. Tell me what you’d like to do (e.g., apply leave, cancel leave #123, create an IT ticket)."
        session_state.metadata["last_tool"] = "confirmation_guard"
        session_state.metadata["last_status"] = "success"

    elif (
        action_reply := _action_command_response(req.message, db, user, session_state)
    ) is not None:
        # Deterministic approve/reject/cancel commands (RBAC-enforced).
        # Runs before capability + admin + LangGraph so "cancel leave 7" /
        # "approve leave 12" / "reject ticket 5" / "approve asset 9" never
        # fall through to RAG or free-form LLM answers.
        reply = action_reply
        session_state.set_agent("general")
        session_state.metadata["last_tool"] = "action_command_dispatcher"
        session_state.metadata["last_status"] = "success"

    elif (cap_reply := _capability_response(req.message, db, user)) is not None:
        # Documented employee capabilities (view leave history, my pending
        # requests, approval status, cancel leave w/o id) — handled before
        # admin / agent routing so wording from the spec works verbatim.
        reply = cap_reply
        session_state.set_agent("general")
        session_state.metadata["last_tool"] = "capability_dispatcher"
        session_state.metadata["last_status"] = "success"

    elif (admin_reply := _admin_command_response(req.message, db, user, session_state)) is not None:
        reply = admin_reply

    elif _is_contextual_follow_up(req.message) and session_state.last_agent == "hr":
        reply = hr_agent(req.message, db, user, history, session_state=session_state)

    elif _is_contextual_follow_up(req.message) and session_state.last_agent == "it":
        reply = it_agent(req.message, db, user, history, session_state=session_state)

    else:
        # Let LangGraph route to HR, IT, or the general fallback.
        result = graph.invoke({
            "message": req.message,
            "db": db,
            "user": user,
            "history": history,
            "session_state": session_state,
        })

        if "response" in result and result["response"]:
            reply = result["response"]
            session_state.set_agent(result.get("agent"))
        else:
            reply = _answer_general_question(session_state, req.message, role=user.role)
            session_state.set_agent("general")

    session_state.record_exchange(req.message, reply)
    create_log(
        db=db,
        user=user,
        agent=session_state.last_agent,
        action=session_state.metadata.pop("last_action", "chat_response"),
        tool_used=session_state.metadata.pop("last_tool", session_state.last_agent),
        status=session_state.metadata.pop("last_status", "success"),
        message=req.message,
        response=reply,
    )

    return {"reply": reply}


@router.post("/orchestrate")
def orchestrate_debug(req: ChatRequest, user: Employee = Depends(get_current_user)):
    """
    Debug endpoint that exposes the orchestration decision for a message.
    Useful for validating intent classification + normalization without
    triggering any side effects.
    """
    user_key = str(user.id)
    session_state = agent_state_store.get(user_key)
    decision = orchestrate(req.message, session_state=session_state)
    return {
        "success": True,
        "data": decision.as_dict(),
        "error": None,
        "message": "OK",
    }


@router.get("/me")
def me(user: Employee = Depends(get_current_user)):
    return {
        "success": True,
        "message": "OK",
        "data": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": _normalize_role_for_backend(user.role),
        },
        "error": None,
    }

from datetime import datetime, timezone

from db.models import Ticket
from actions.power_automate_action import send_it_notification
from actions.email_action import send_email
from config.rbac import can_approve_ticket, is_admin, is_it_team, is_manager


OPEN_STATUSES = ["open", "in_progress"]
ALLOWED_TICKET_STATUSES = ["open", "in_progress", "resolved", "closed", "rejected"]

# Strict state machine for tickets. ``resolved`` is treated as a synonym for
# ``closed`` (both are terminal success states) because the API/UI have
# historically used them interchangeably; rejected is also terminal.
TERMINAL_TICKET_STATUSES = {"closed", "resolved", "rejected"}

# ``TICKET_TRANSITIONS[current]`` lists the statuses you are allowed to
# transition TO. Terminal statuses have an empty set → no further updates.
TICKET_TRANSITIONS: dict[str, set[str]] = {
    "open":        {"in_progress", "rejected"},
    "in_progress": {"closed", "resolved", "rejected"},
    "resolved":    set(),
    "closed":      set(),
    "rejected":    set(),
}


class TicketTransitionError(Exception):
    """Raised when the caller tries to apply an illegal ticket transition."""


def can_transition_ticket(current: str | None, target: str) -> bool:
    """Return True if ``current -> target`` is a legal state transition."""
    if target not in ALLOWED_TICKET_STATUSES:
        return False
    if current is None:
        # Freshly-created tickets start at 'open' implicitly.
        return target in TICKET_TRANSITIONS["open"] or target == "open"
    if current == target:
        # Re-asserting the current state is a no-op, allow it.
        return True
    return target in TICKET_TRANSITIONS.get(current, set())


def check_duplicate_ticket(db, user_id: str, issue_type: str):
    return db.query(Ticket).filter(
        Ticket.user_id == user_id,
        Ticket.issue_type == issue_type,
        Ticket.status.in_(OPEN_STATUSES)
    ).first()


def create_ticket(
    db,
    user_id: str,
    issue_type: str,
    description: str,
    priority: str = "medium"
):
    duplicate = check_duplicate_ticket(db, user_id, issue_type)

    if duplicate:
        return None, duplicate

    ticket = Ticket(
        user_id=user_id,
        issue_type=issue_type,
        description=description,
        priority=priority,
        status="open"
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Send Power Automate notification after successful DB commit
    from db.models import Employee
    employee = db.query(Employee).filter(Employee.email == user_id).first()
    if employee:
        try:
            send_it_notification(
                event_type="ticket_created",
                title=f"Ticket Created: {ticket.issue_type}",
                message=f"{employee.name} has created a {ticket.issue_type} ticket: {ticket.description}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "ticket_id": ticket.id,
                    "issue_type": ticket.issue_type,
                    "issue_description": ticket.description,
                    "status": ticket.status,
                    "created_at": ticket.created_at.isoformat()
                }
            )
        except Exception as e:
            # Log error but don't fail ticket creation
            print(f"[POWER_AUTOMATE] Failed to send ticket created notification: {e}")

        # Lightweight acknowledgement email so the employee has a paper
        # trail outside the chat. Routes through POWER_IT_URL.
        try:
            send_email(
                to=employee.email,
                subject=f"IT Ticket Created: #{ticket.id}",
                body=(
                    f"Hello {employee.name},\n\n"
                    f"Your IT support ticket has been created.\n\n"
                    f"Ticket ID: #{ticket.id}\n"
                    f"Issue: {ticket.issue_type}\n"
                    f"Description: {ticket.description}\n"
                    f"Status: {ticket.status}\n\n"
                    f"The IT team will follow up shortly."
                ),
                channel="it",
            )
        except Exception as e:
            print(f"[email] Failed to send ticket-created email: {e}")

    return ticket, None


def get_user_tickets(db, user_id: str):
    return db.query(Ticket).filter(
        Ticket.user_id == user_id
    ).order_by(Ticket.id.desc()).all()


def get_all_tickets(db):
    return db.query(Ticket).order_by(Ticket.id.desc()).all()


def get_open_tickets(db):
    return db.query(Ticket).filter(
        Ticket.status.in_(OPEN_STATUSES)
    ).order_by(Ticket.id.desc()).all()


def get_tickets_by_status(db, status: str):
    return db.query(Ticket).filter(
        Ticket.status == status
    ).order_by(Ticket.id.desc()).all()


def update_ticket_status(db, ticket_id: int, status: str, user_role: str = None, user_id: str = None):
    """Update ticket status with RBAC + strict state-machine validation.

    Raises ``TicketTransitionError`` when the requested transition is not
    allowed (terminal state, or not in the allowed next-state set).
    Returns ``None`` if the ticket does not exist or RBAC rejects the caller.
    """
    if status not in ALLOWED_TICKET_STATUSES:
        raise ValueError(f"Unsupported ticket status: {status}")

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if not ticket:
        return None

    # RBAC: only IT team and admin can change ticket status.
    if user_role and not can_approve_ticket(user_role):
        return None

    current = (ticket.status or "open").lower()
    target = status.lower()

    if current in TERMINAL_TICKET_STATUSES and current != target:
        raise TicketTransitionError(
            f"Ticket #{ticket.id} is already {current}; it cannot be reopened or modified."
        )

    if not can_transition_ticket(current, target):
        raise TicketTransitionError(
            f"Invalid transition: cannot move ticket #{ticket.id} from {current} to {target}."
        )

    ticket.status = target
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)

    # Send Power Automate notification after successful DB commit
    from db.models import Employee
    employee = db.query(Employee).filter(Employee.email == ticket.user_id).first()
    if employee:
        try:
            if status in ("resolved", "closed"):
                send_it_notification(
                    event_type="ticket_resolved",
                    title=f"Ticket Resolved: {ticket.issue_type}",
                    message=f"{employee.name}'s {ticket.issue_type} ticket has been resolved",
                    metadata={
                        "employee_id": employee.id,
                        "employee_name": employee.name,
                        "employee_email": employee.email,
                        "ticket_id": ticket.id,
                        "issue_type": ticket.issue_type,
                        "issue_description": ticket.description,
                        "status": status,
                        "updated_at": ticket.updated_at.isoformat()
                    }
                )
            else:
                send_it_notification(
                    event_type="ticket_updated",
                    title=f"Ticket Updated: {ticket.issue_type}",
                    message=f"{employee.name}'s {ticket.issue_type} ticket status updated to {status}",
                    metadata={
                        "employee_id": employee.id,
                        "employee_name": employee.name,
                        "employee_email": employee.email,
                        "ticket_id": ticket.id,
                        "issue_type": ticket.issue_type,
                        "issue_description": ticket.description,
                        "status": status,
                        "updated_at": ticket.updated_at.isoformat()
                    }
                )
        except Exception as e:
            # Log error but don't fail ticket update
            print(f"[POWER_AUTOMATE] Failed to send ticket updated notification: {e}")

        # Status-change email so the employee is kept informed outside the
        # chat / dashboard. Lightweight, never blocks the status change.
        try:
            if status in ("resolved", "closed"):
                subject = f"IT Ticket Resolved: #{ticket.id}"
                line = (
                    f"Your IT ticket has been marked as {status}. If the "
                    f"problem isn't fully fixed, please reply or open a new ticket."
                )
            else:
                subject = f"IT Ticket Updated: #{ticket.id}"
                line = f"Your IT ticket status is now '{status}'."
            send_email(
                to=employee.email,
                subject=subject,
                body=(
                    f"Hello {employee.name},\n\n"
                    f"{line}\n\n"
                    f"Ticket ID: #{ticket.id}\n"
                    f"Issue: {ticket.issue_type}\n"
                    f"Description: {ticket.description}\n"
                    f"Status: {status}\n"
                ),
                channel="it",
            )
        except Exception as e:
            print(f"[email] Failed to send ticket-updated email: {e}")

    return ticket

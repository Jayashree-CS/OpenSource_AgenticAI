import os
from datetime import date, datetime
from db.models import Employee, LeaveRequest, LeaveBalance
from actions.calendar_action import calculate_working_days
from actions.email_action import send_email
from actions.power_automate_action import send_hr_notification
from config.rbac import can_approve_leave, is_admin, is_manager


LEAVE_TYPES = ("sick", "casual", "earned")

# Enterprise workflow states - simplified without HR review
STATUS_PENDING_MANAGER = "pending_manager"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_CANCELLED = "cancelled"

# HR review is removed - manager approval is final
# Admin can also approve leaves as superuser


def calculate_working_leave_days(db, start_date: date, end_date: date):
    return calculate_working_days(db, start_date, end_date)


def _normalize_leave_type(leave_type: str | None) -> str:
    leave_type = (leave_type or "casual").lower()
    return leave_type if leave_type in LEAVE_TYPES else "casual"


def get_or_create_leave_balance(db, employee_id: int):
    balance = db.query(LeaveBalance).filter(
        LeaveBalance.employee_id == employee_id
    ).first()

    if balance:
        return balance

    balance = LeaveBalance(employee_id=employee_id)
    db.add(balance)
    db.commit()
    db.refresh(balance)
    return balance


_DEFAULT_TOTALS = {"sick": 6, "casual": 6, "earned": 12}


def _type_balance(balance, leave_type: str):
    total = getattr(balance, f"{leave_type}_total", None)
    used = getattr(balance, f"{leave_type}_used", None)
    if total is None:
        total = _DEFAULT_TOTALS.get(leave_type, 0)
    if used is None:
        used = 0
    return {
        "total": total,
        "used": used,
        "remaining": max(total - used, 0),
    }


def _insufficient_balance(leave_type: str, remaining: int):
    return {
        "status": "insufficient_balance",
        "leave_type": leave_type,
        "remaining": remaining,
    }


# ---------------------------------------------------------------------------
# Overlap + input validation
# ---------------------------------------------------------------------------

# Statuses that are still "live" and should block another overlapping request.
# Cancelled/rejected leaves do NOT block new requests for the same window.
BLOCKING_LEAVE_STATUSES = (
    STATUS_PENDING_MANAGER,
    STATUS_APPROVED,
)


def _coerce_to_date(value):
    """Accept ``date``, ``datetime``, or ISO string; return a ``date`` or None."""
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


def find_overlapping_leaves(db, employee_id: int, start_date, end_date,
                             exclude_leave_id: int | None = None):
    """Return every live leave that overlaps ``[start_date, end_date]``.

    Two ranges ``[a,b]`` and ``[c,d]`` overlap iff ``a <= d AND b >= c``.
    Cancelled/rejected leaves are ignored. When updating an existing leave,
    pass ``exclude_leave_id`` so it does not match itself.
    """
    start_d = _coerce_to_date(start_date)
    end_d = _coerce_to_date(end_date)
    if start_d is None or end_d is None:
        return []

    query = db.query(LeaveRequest).filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status.in_(BLOCKING_LEAVE_STATUSES),
        LeaveRequest.start_date <= end_d,
        LeaveRequest.end_date >= start_d,
    )
    if exclude_leave_id is not None:
        query = query.filter(LeaveRequest.id != exclude_leave_id)
    return query.all()


def apply_leave(
    db,
    employee_id,
    start_date,
    end_date,
    reason="Applied via AI",
    leave_type="casual",
    manager_email=None
):
    leave_type = _normalize_leave_type(leave_type)

    # Defensive: refuse to proceed if mandatory data is missing.
    if employee_id is None or start_date is None or end_date is None:
        return {
            "status": "missing_data",
            "message": "Cannot apply leave without employee, start_date, and end_date.",
        }

    start_d = _coerce_to_date(start_date)
    end_d = _coerce_to_date(end_date)
    if start_d is None or end_d is None:
        return {
            "status": "invalid_date",
            "message": "Start and end dates must be valid calendar dates.",
        }
    if end_d < start_d:
        return {
            "status": "invalid_range",
            "message": "End date cannot be earlier than start date.",
        }
    today = date.today()
    if end_d < today:
        return {
            "status": "past_date",
            "message": "Leave cannot be applied for dates that are already in the past.",
        }

    # Overlap check: block pending or approved leaves that already cover any
    # portion of the requested range. Same-day duplicates, fully overlapping
    # and partially overlapping ranges are all rejected here.
    overlaps = find_overlapping_leaves(db, employee_id, start_d, end_d)
    if overlaps:
        conflict = overlaps[0]
        return {
            "status": "overlap",
            "message": (
                "You already have a leave request overlapping these dates "
                f"(Leave #{conflict.id}: {conflict.start_date} to {conflict.end_date}, "
                f"status: {conflict.status})."
            ),
            "conflict_leave_id": conflict.id,
            "conflict_start": str(conflict.start_date),
            "conflict_end": str(conflict.end_date),
            "conflict_status": conflict.status,
        }

    total_days = calculate_working_leave_days(db, start_d, end_d)
    if total_days <= 0:
        return {
            "status": "non_working_days",
            "message": "Selected date(s) are weekend/holiday. Leave is not required.",
        }
    balance = get_or_create_leave_balance(db, employee_id)
    type_balance = _type_balance(balance, leave_type)

    if total_days > type_balance["remaining"]:
        return _insufficient_balance(leave_type, type_balance["remaining"])

    # Normalise stored dates to date objects for the DB column.
    start_date = start_d
    end_date = end_d

    leave = LeaveRequest(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        leave_type=leave_type,
        total_days=total_days,
        manager_email=manager_email,
        status=STATUS_PENDING_MANAGER
    )

    db.add(leave)
    db.commit()
    db.refresh(leave)

    # Send Power Automate notification after successful DB commit
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if employee:
        try:
            send_hr_notification(
                event_type="leave_applied",
                title=f"Leave Applied: {leave.leave_type}",
                message=f"{employee.name} has applied for {leave.leave_type} leave from {leave.start_date} to {leave.end_date}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "leave_id": leave.id,
                    "leave_type": leave.leave_type,
                    "start_date": leave.start_date.isoformat(),
                    "end_date": leave.end_date.isoformat(),
                    "reason": leave.reason
                }
            )
        except Exception as e:
            # Log error but don't fail the leave application
            print(f"[POWER_AUTOMATE] Failed to send leave applied notification: {e}")

    return leave


def get_leave_history(db, employee_id):
    # Newest first so chat replies + UI consistently lead with the most
    # recent activity.
    return db.query(LeaveRequest).filter(
        LeaveRequest.employee_id == employee_id
    ).order_by(LeaveRequest.id.desc()).all()


def get_pending_leaves(db, employee_id):
    return db.query(LeaveRequest).filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status == STATUS_PENDING_MANAGER
    ).all()


def get_leave_balance(db, employee_id):
    balance = get_or_create_leave_balance(db, employee_id)
    return {
        leave_type: _type_balance(balance, leave_type)
        for leave_type in LEAVE_TYPES
    }


def cancel_leave(db, employee_id, leave_id):
    leave = db.query(LeaveRequest).filter(
        LeaveRequest.id == leave_id,
        LeaveRequest.employee_id == employee_id
    ).first()

    if not leave:
        return None

    if leave.status not in (STATUS_PENDING_MANAGER,):
        return "not_allowed"

    leave.status = STATUS_CANCELLED
    db.commit()
    db.refresh(leave)

    return leave


def update_leave_status(db, leave_id, status):
    # Legacy helper; retained for compatibility with REST update route.
    allowed_status = [STATUS_PENDING_MANAGER, STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED]

    if status not in allowed_status:
        return "invalid_status"

    leave = db.query(LeaveRequest).filter(
        LeaveRequest.id == leave_id
    ).first()

    if not leave:
        return None

    # Only deduct leave balance on final approval.
    if status == STATUS_APPROVED and leave.status != STATUS_APPROVED:
        leave_type = _normalize_leave_type(leave.leave_type)
        balance = get_or_create_leave_balance(db, leave.employee_id)
        type_balance = _type_balance(balance, leave_type)

        if leave.total_days > type_balance["remaining"]:
            return _insufficient_balance(leave_type, type_balance["remaining"])

        setattr(
            balance,
            f"{leave_type}_used",
            getattr(balance, f"{leave_type}_used") + leave.total_days,
        )

    leave.status = status
    db.commit()
    db.refresh(leave)

    return leave

def get_leave_status(db, employee_id, leave_id):
    leave = db.query(LeaveRequest).filter(
        LeaveRequest.id == leave_id,
        LeaveRequest.employee_id == employee_id
    ).first()

    if not leave:
        return None

    return leave

def get_pending_leaves_for_manager(db, manager_id):
    """Pending leaves awaiting manager action.

    Managers see only their direct reports. Admin is superior to every
    manager, so admins see every pending leave in the system — mirrors
    the admin branch in ``get_pending_asset_requests_for_manager``.
    """
    manager = db.query(Employee).filter(Employee.id == manager_id).first()
    query = db.query(LeaveRequest).join(
        Employee,
        LeaveRequest.employee_id == Employee.id
    ).filter(LeaveRequest.status == STATUS_PENDING_MANAGER)

    if manager and (manager.role or "").lower() == "admin":
        return query.all()

    return query.filter(Employee.manager_id == manager_id).all()


def approve_leave_by_manager(db, leave_id, manager_id):
    """Approve leave request - manager or admin can approve."""
    manager = db.query(Employee).filter(Employee.id == manager_id).first()
    
    # Check if user has permission to approve leave
    if not manager or not can_approve_leave(manager.role):
        return None
    
    query = db.query(LeaveRequest).join(
        Employee,
        LeaveRequest.employee_id == Employee.id
    ).filter(
        LeaveRequest.id == leave_id,
        LeaveRequest.status == STATUS_PENDING_MANAGER
    )

    # Managers can only approve direct reports, admins can approve anyone
    if is_manager(manager.role):
        query = query.filter(Employee.manager_id == manager_id)
    # Admin can approve all pending leaves
    # No additional filter needed for admin

    leave = query.first()

    if not leave:
        return None

    # Manager/admin approval is final - no HR review needed
    leave_type = _normalize_leave_type(leave.leave_type)
    balance = get_or_create_leave_balance(db, leave.employee_id)
    type_balance = _type_balance(balance, leave_type)
    if leave.total_days > type_balance["remaining"]:
        return _insufficient_balance(leave_type, type_balance["remaining"])
    setattr(
        balance,
        f"{leave_type}_used",
        getattr(balance, f"{leave_type}_used") + leave.total_days,
    )
    leave.status = STATUS_APPROVED
    
    db.commit()
    db.refresh(leave)

    employee = db.query(Employee).filter(
        Employee.id == leave.employee_id
    ).first()

    if employee:
        approver_role = "Admin" if is_admin(manager.role) else "Manager"
        send_email(
            to=employee.email,
            subject="Leave Request Approved",
            body=(
                f"Hello {employee.name},\n\n"
                f"Your leave request has been approved by {approver_role.lower()}.\n\n"
                f"Leave ID: #{leave.id}\n"
                f"Type: {leave.leave_type}\n"
                f"Dates: {leave.start_date} to {leave.end_date}\n"
                f"Days: {leave.total_days}\n"
                f"Status: {leave.status}\n\n"
                f"Please check the portal for details."
            ),
            channel="hr",
        )
        
        # Send Power Automate notification after successful DB commit
        try:
            send_hr_notification(
                event_type="leave_approved",
                title=f"Leave Approved: {leave.leave_type}",
                message=f"{employee.name}'s {leave.leave_type} leave from {leave.start_date} to {leave.end_date} has been approved by {approver_role}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "leave_id": leave.id,
                    "leave_type": leave.leave_type,
                    "start_date": leave.start_date.isoformat(),
                    "end_date": leave.end_date.isoformat(),
                    "approver_role": approver_role,
                    "approver_id": manager_id
                }
            )
        except Exception as e:
            # Log error but don't fail the leave approval
            print(f"[POWER_AUTOMATE] Failed to send leave approved notification: {e}")

    return leave

def reject_leave_by_manager(db, leave_id, manager_id):
    """Reject leave request - manager or admin can reject."""
    manager = db.query(Employee).filter(Employee.id == manager_id).first()
    
    # Check if user has permission to reject leave
    if not manager or not can_approve_leave(manager.role):
        return None

    query = db.query(LeaveRequest).join(
        Employee,
        LeaveRequest.employee_id == Employee.id
    ).filter(
        LeaveRequest.id == leave_id,
        LeaveRequest.status == STATUS_PENDING_MANAGER
    )

    # Managers can only reject direct reports, admins can reject anyone
    if is_manager(manager.role):
        query = query.filter(Employee.manager_id == manager_id)
    # Admin can reject all pending leaves
    # No additional filter needed for admin

    leave = query.first()

    if not leave:
        return None

    leave.status = STATUS_REJECTED
    db.commit()
    db.refresh(leave)

    employee = db.query(Employee).filter(
        Employee.id == leave.employee_id
    ).first()

    if employee:
        approver_role = "Admin" if is_admin(manager.role) else "Manager"
        send_email(
            to=employee.email,
            subject="Leave Request Rejected",
            body=(
                f"Hello {employee.name},\n\n"
                f"Your leave request has been rejected by {approver_role.lower()}.\n\n"
                f"Leave ID: #{leave.id}\n"
                f"Type: {leave.leave_type}\n"
                f"Dates: {leave.start_date} to {leave.end_date}\n"
                f"Days: {leave.total_days}\n"
                f"Status: {leave.status}\n\n"
                f"Please contact your {approver_role.lower()} for more details."
            ),
            channel="hr",
        )
        
        # Send Power Automate notification after successful DB commit
        try:
            send_hr_notification(
                event_type="leave_rejected",
                title=f"Leave Rejected: {leave.leave_type}",
                message=f"{employee.name}'s {leave.leave_type} leave from {leave.start_date} to {leave.end_date} has been rejected by {approver_role}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "leave_id": leave.id,
                    "leave_type": leave.leave_type,
                    "start_date": leave.start_date.isoformat(),
                    "end_date": leave.end_date.isoformat(),
                    "approver_role": approver_role,
                    "approver_id": manager_id
                }
            )
        except Exception as e:
            # Log error but don't fail the leave rejection
            print(f"[POWER_AUTOMATE] Failed to send leave rejected notification: {e}")

    return leave



from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import LeaveCreate, LeaveResponse, Employee
from actions.auth_dependency import get_current_user
from actions.leave_action import (
    apply_leave as apply_leave_action,
    get_leave_history as get_leave_history_action,
    update_leave_status as update_leave_status_action,
    approve_leave_by_manager,
    reject_leave_by_manager,
    STATUS_APPROVED,
    STATUS_REJECTED,
)

router = APIRouter()

# DB dependency

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Apply Leave

@router.post("/apply-leave", response_model=LeaveResponse)
def apply_leave(
    leave: LeaveCreate,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    # Prevent spoofing employee_id in payload (unless admin).
    if str(leave.employee_id) != str(user.id) and (user.role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    new_leave = apply_leave_action(
        db=db,
        employee_id=leave.employee_id,
        start_date=leave.start_date,
        end_date=leave.end_date,
        reason=leave.reason,
        leave_type=leave.leave_type,
    )

    if isinstance(new_leave, dict) and new_leave.get("status") == "insufficient_balance":
        raise HTTPException(
            status_code=400,
            detail=(
                f"You only have {new_leave['remaining']} {new_leave['leave_type']} "
                "leaves remaining."
            ),
        )
    if isinstance(new_leave, dict) and new_leave.get("status") == "non_working_days":
        raise HTTPException(status_code=400, detail=new_leave["message"])

    return new_leave


# Get Leave History

@router.get("/leave-history/{employee_id}", response_model=list[LeaveResponse])
def get_leave_history(
    employee_id: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    if str(employee_id) != str(user.id) and (user.role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return get_leave_history_action(db, employee_id)


# Approve / Reject Leave

@router.put("/leave/{leave_id}", response_model=LeaveResponse)
def update_leave_status(
    leave_id: int,
    status: str,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = (user.role or "").lower()
    # Only manager/hr can approve/reject in enterprise workflow.
    if role not in {"manager", "hr"}:
        raise HTTPException(status_code=403, detail="Forbidden")
    if status not in [STATUS_APPROVED, STATUS_REJECTED]:
        raise HTTPException(status_code=400, detail="Invalid status")

    # Manager decision applies to pending_manager only; HR finalizes pending_hr only.
    if role == "manager":
        leave = approve_leave_by_manager(db, leave_id, user.id) if status == STATUS_APPROVED else reject_leave_by_manager(db, leave_id, user.id)
    

    if isinstance(leave, dict) and leave.get("status") == "insufficient_balance":
        raise HTTPException(
            status_code=400,
            detail=(
                f"You only have {leave['remaining']} {leave['leave_type']} "
                "leaves remaining."
            ),
        )
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    if leave in ("invalid_status", "invalid_transition"):
        raise HTTPException(status_code=400, detail="Invalid leave status transition")

    return leave


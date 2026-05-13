from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from actions.auth_dependency import get_current_user, require_roles
from db.database import SessionLocal
from db.models import Employee, LeaveRequest, Ticket, AssetRequest
from actions.leave_action import get_pending_leaves_for_manager, approve_leave_by_manager, reject_leave_by_manager
from actions.asset_action import (
    get_pending_asset_requests_for_manager,
    approve_asset_by_manager,
    reject_asset_by_manager,
)

router = APIRouter(
    prefix="/api/manager",
    tags=["API: Manager"],
    dependencies=[Depends(require_roles("manager", "admin"))],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ApprovalActionPayload(BaseModel):
    action: str  # approve | reject


@router.get("/approvals/summary")
def manager_approvals_summary(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    pending_leaves = get_pending_leaves_for_manager(db, user.id)
    pending_assets = get_pending_asset_requests_for_manager(db, user.id)
    return {
        "success": True,
        "data": {
            "pending_leaves": len(pending_leaves or []),
            "pending_assets": len(pending_assets or []),
        },
        "error": None,
        "message": "OK",
    }


@router.get("/leaves/pending")
def manager_pending_leaves(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    leaves = get_pending_leaves_for_manager(db, user.id)
    return {"success": True, "data": leaves, "error": None, "message": "OK"}


@router.post("/leaves/{leave_id}")
def manager_action_leave(
    leave_id: int,
    payload: ApprovalActionPayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    action = (payload.action or "").lower().strip()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    if action == "approve":
        leave = approve_leave_by_manager(db, leave_id, user.id)
    else:
        leave = reject_leave_by_manager(db, leave_id, user.id)

    if isinstance(leave, dict) and leave.get("status") == "insufficient_balance":
        raise HTTPException(status_code=400, detail="Insufficient leave balance")

    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found or not under your authority")

    return {"success": True, "data": leave, "error": None, "message": "OK"}


@router.get("/assets/pending")
def manager_pending_assets(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = get_pending_asset_requests_for_manager(db, user.id)
    return {"success": True, "data": rows, "error": None, "message": "OK"}


@router.post("/assets/{request_id}")
def manager_action_asset(
    request_id: int,
    payload: ApprovalActionPayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    action = (payload.action or "").lower().strip()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    if action == "approve":
        req = approve_asset_by_manager(db, request_id, user.id)
    else:
        req = reject_asset_by_manager(db, request_id, user.id)

    if not req:
        raise HTTPException(status_code=404, detail="Asset request not found or not under your authority")

    return {"success": True, "data": req, "error": None, "message": "OK"}


@router.get("/team/overview")
def manager_team_overview(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Approval history for the current reviewer.

    - Manager: strictly their direct reports (Employee.manager_id == user.id).
    - Admin: superior to every manager + IT lead, so returns the whole
      company's leaves / tickets / assets so the admin "Approvals" page
      is never blank.
    """
    is_admin = (user.role or "").lower() == "admin"

    if is_admin:
        team = db.query(Employee).order_by(Employee.id).all()
        leaves = db.query(LeaveRequest).order_by(LeaveRequest.id.desc()).all()
        tickets = db.query(Ticket).order_by(Ticket.id.desc()).all()
        assets = db.query(AssetRequest).order_by(AssetRequest.id.desc()).all()
    else:
        team = db.query(Employee).filter(Employee.manager_id == user.id).all()
        team_emails = [e.email for e in team]
        team_ids = [e.id for e in team]
        leaves = db.query(LeaveRequest).filter(LeaveRequest.employee_id.in_(team_ids)).all() if team_ids else []
        tickets = db.query(Ticket).filter(Ticket.user_id.in_(team_emails)).all() if team_emails else []
        assets = db.query(AssetRequest).filter(AssetRequest.user_id.in_(team_emails)).all() if team_emails else []

    return {
        "success": True,
        "data": {
            "team": team,
            "leaves": leaves,
            "tickets": tickets,
            "assets": assets,
        },
        "error": None,
        "message": "OK",
    }

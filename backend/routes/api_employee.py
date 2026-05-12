from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from actions.auth_dependency import get_current_user
from db.database import SessionLocal
from db.models import Employee
from actions.leave_action import apply_leave as apply_leave_action, get_leave_history, get_leave_balance
from actions.it_action import create_ticket, get_user_tickets
from actions.asset_action import create_asset_request, get_asset_requests
from actions.auth_dependency import require_roles

router = APIRouter(
    prefix="/api/employee",
    tags=["API: Employee"],
    dependencies=[Depends(require_roles("employee", "admin"))],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LeaveApplyPayload(BaseModel):
    start_date: date
    end_date: date
    reason: str | None = None
    leave_type: str | None = None


class TicketCreatePayload(BaseModel):
    issue_type: str
    description: str
    priority: str = "medium"


class AssetCreatePayload(BaseModel):
    asset_type: str
    reason: str | None = None


@router.get("/me")
def employee_me(user: Employee = Depends(get_current_user)):
    return {
        "success": True,
        "data": {"id": user.id, "name": user.name, "email": user.email, "role": (user.role or "").lower()},
        "error": None,
        "message": "OK",
    }


@router.get("/leave/balance")
def employee_leave_balance(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return {
        "success": True,
        "data": get_leave_balance(db, user.id),
        "error": None,
        "message": "OK",
    }


@router.get("/leave/history")
def employee_leave_history(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    leaves = get_leave_history(db, user.id)
    return {"success": True, "data": leaves, "error": None, "message": "OK"}


@router.post("/leave/apply")
def employee_apply_leave(
    payload: LeaveApplyPayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    result = apply_leave_action(
        db=db,
        employee_id=user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason or "Applied via portal",
        leave_type=payload.leave_type or "casual",
        manager_email=None,
    )

    # Surface every validation failure from the action layer as a 400.
    if isinstance(result, dict):
        status = result.get("status")
        if status == "insufficient_balance":
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient {result.get('leave_type') or 'leave'} balance (only {result.get('remaining', 0)} day(s) remaining).",
            )
        if status in {
            "non_working_days", "invalid_date", "invalid_range",
            "past_date", "missing_data", "overlap",
        }:
            raise HTTPException(
                status_code=400,
                detail=result.get("message") or "Invalid leave request",
            )

    return {"success": True, "data": result, "error": None, "message": "Leave applied"}


@router.post("/tickets")
def employee_create_ticket(
    payload: TicketCreatePayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    ticket, duplicate = create_ticket(
        db=db,
        user_id=user.email,
        issue_type=payload.issue_type,
        description=payload.description,
        priority=payload.priority,
    )

    if duplicate:
        return {
            "success": False,
            "data": {"duplicate_ticket": duplicate},
            "error": "duplicate",
            "message": "Duplicate open ticket already exists for this issue type.",
        }

    return {"success": True, "data": ticket, "error": None, "message": "Ticket created"}


@router.get("/tickets")
def employee_list_tickets(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = get_user_tickets(db, user.email)
    return {"success": True, "data": rows, "error": None, "message": "OK"}


@router.post("/assets")
def employee_create_asset_request(
    payload: AssetCreatePayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    req = create_asset_request(db, user.email, payload.asset_type, reason=payload.reason)
    return {"success": True, "data": req, "error": None, "message": "Asset request created"}


@router.get("/assets")
def employee_list_asset_requests(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = get_asset_requests(db, user.email)
    return {"success": True, "data": rows, "error": None, "message": "OK"}

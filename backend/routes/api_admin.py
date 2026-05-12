from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from actions.auth_action import hash_password
from actions.auth_dependency import get_current_user, require_roles
from actions.log_action import get_logs
from db.database import SessionLocal
from db.models import AssetRequest, Employee, Inventory, LeaveRequest, NotificationLog, Ticket

router = APIRouter(
    prefix="/api/admin",
    tags=["API: Admin"],
    dependencies=[Depends(require_roles("admin"))],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class UserCreatePayload(BaseModel):
    name: str
    email: str
    password: str
    role: str = "employee"
    manager_id: int | None = None
    # Department removed from the create flow — the column is kept on the
    # model for historical data but the UI no longer collects it.


class InventoryUpsertPayload(BaseModel):
    asset_type: str
    total_quantity: int
    available_quantity: int


@router.get("/logs")
def admin_logs(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = get_logs(db)
    return {
        "success": True,
        "data": [
            {
                "id": log.id,
                "time": str(log.created_at) if log.created_at else "",
                "agent": log.agent,
                "action": log.action,
                "tool_used": log.tool_used,
                "user": log.user_email,
                "role": log.user_role,
                "status": log.status,
            }
            for log in rows
        ],
        "error": None,
        "message": "OK",
    }


@router.get("/users")
def admin_list_users(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = db.query(Employee).order_by(Employee.id).all()
    return {"success": True, "data": rows, "error": None, "message": "OK"}


@router.post("/users")
def admin_create_user(
    payload: UserCreatePayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    email = payload.email.strip().lower()
    existing = db.query(Employee).filter(Employee.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    employee = Employee(
        name=payload.name.strip() or email.split("@")[0],
        email=email,
        role=(payload.role or "employee").strip().lower(),
        department=None,
        manager_id=payload.manager_id,
        password_hash=hash_password(payload.password),
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    return {"success": True, "data": employee, "error": None, "message": "User created"}


@router.delete("/users/{employee_id}")
def admin_delete_user(
    employee_id: int,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Delete an employee + cascade their owned transactional data so no
    dangling FK rows remain. Refuses to delete yourself (safety)."""
    if user and user.id == employee_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="User not found")

    # Clean up owned rows so the DB stays consistent even without FK ON DELETE.
    db.query(LeaveRequest).filter(LeaveRequest.employee_id == employee.id).delete(synchronize_session=False)
    db.query(AssetRequest).filter(AssetRequest.user_id == employee.email).delete(synchronize_session=False)
    db.query(Ticket).filter(Ticket.user_id == employee.email).delete(synchronize_session=False)
    # Anyone reporting to this user gets orphaned — null out the manager FK.
    for report in db.query(Employee).filter(Employee.manager_id == employee.id).all():
        report.manager_id = None

    db.delete(employee)
    db.commit()
    return {"success": True, "data": {"deleted": employee_id}, "error": None, "message": "User deleted"}


@router.get("/inventory")
def admin_inventory_list(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = db.query(Inventory).order_by(Inventory.asset_type).all()
    return {"success": True, "data": rows, "error": None, "message": "OK"}


@router.post("/inventory")
def admin_inventory_upsert(
    payload: InventoryUpsertPayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    asset_type = payload.asset_type.strip()
    item = db.query(Inventory).filter(Inventory.asset_type == asset_type).first()
    if not item:
        item = Inventory(asset_type=asset_type)
        db.add(item)

    item.total_quantity = int(payload.total_quantity)
    item.available_quantity = int(payload.available_quantity)

    db.commit()
    db.refresh(item)

    return {"success": True, "data": item, "error": None, "message": "OK"}


@router.get("/analytics")
def admin_analytics(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return {
        "success": True,
        "data": {
            "employees": db.query(Employee).count(),
            "leaves": db.query(LeaveRequest).count(),
            "tickets": db.query(Ticket).count(),
            "assets": db.query(AssetRequest).count(),
            "inventory_items": db.query(Inventory).count(),
            "logs": len(get_logs(db)),
            "notifications": db.query(NotificationLog).count(),
            "notifications_failed": db.query(NotificationLog)
            .filter(NotificationLog.status == "failed")
            .count(),
        },
        "error": None,
        "message": "OK",
    }


@router.get("/notifications")
def admin_notifications(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = (
        db.query(NotificationLog)
        .order_by(NotificationLog.id.desc())
        .limit(200)
        .all()
    )
    return {
        "success": True,
        "data": [
            {
                "id": row.id,
                "channel": row.channel,
                "event_type": row.event_type,
                "status": row.status,
                "attempts": row.attempts,
                "error": row.error,
                "created_at": str(row.created_at) if row.created_at else None,
            }
            for row in rows
        ],
        "error": None,
        "message": "OK",
    }


@router.get("/notifications/config")
def admin_notifications_config(user: Employee = Depends(get_current_user)):
    """Show which Power Automate channels are configured (URL masked)."""
    from actions.power_automate_action import test_webhook_connectivity
    cfg = test_webhook_connectivity()
    safe = {}
    for key, info in cfg.items():
        url = info.get("url") or ""
        safe[key] = {
            "configured": info.get("configured", False),
            "url_present": bool(url),
            "url_preview": (url[:60] + "...") if url else "",
        }
    return {"success": True, "data": safe, "error": None, "message": "OK"}


class NotificationTestPayload(BaseModel):
    channel: str  # "hr" | "it" | "asset"


@router.post("/notifications/test")
def admin_notifications_test(
    payload: NotificationTestPayload,
    user: Employee = Depends(get_current_user),
):
    """Fire a synchronous test webhook against a single Power Automate
    channel so the user can verify their flow setup end-to-end. Returns
    success/failure inline (does not rely on async executor)."""
    channel = (payload.channel or "").strip().lower()
    if channel not in {"hr", "it", "asset"}:
        raise HTTPException(status_code=400, detail="channel must be hr|it|asset")

    from actions.power_automate_action import (
        send_hr_notification,
        send_it_notification,
        send_asset_notification,
    )

    common = {
        "title": f"Test {channel.upper()} notification",
        "message": f"Manual test fired by {user.email}",
        "async_send": False,
        "metadata": {"triggered_by": user.email, "test": True},
    }
    if channel == "hr":
        ok = send_hr_notification(event_type="test_hr", **common)
    elif channel == "it":
        ok = send_it_notification(event_type="test_it", **common)
    else:
        ok = send_asset_notification(event_type="test_asset", **common)

    return {
        "success": bool(ok),
        "data": {"channel": channel, "delivered": bool(ok)},
        "error": None if ok else "webhook_failed",
        "message": "Webhook delivered" if ok else "Webhook failed — check NotificationLog",
    }


@router.post("/rag/reindex")
def admin_rag_reindex(user: Employee = Depends(get_current_user)):
    """Trigger a synchronous reindex of the RAG corpus."""
    try:
        from rag.cli import _reindex
        _reindex()
        return {"success": True, "data": {"reindexed": True}, "error": None, "message": "OK"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {exc}")

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db.database import SessionLocal
from db.models import (
    Employee,
    LeaveRequest,
    Ticket,
    AssetRequest,
    Inventory,
)
from actions.log_action import get_logs
from actions.leave_action import get_leave_balance
from actions.auth_dependency import get_current_user, require_roles

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
admin_router = APIRouter(prefix="/admin", tags=["Admin"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _leave_row(db: Session, leave: LeaveRequest):
    employee = db.query(Employee).filter(Employee.id == leave.employee_id).first()
    return {
        "id": leave.id,
        "emp": getattr(employee, "name", str(leave.employee_id)),
        "employee_id": leave.employee_id,
        "type": leave.leave_type,
        "from": str(leave.start_date),
        "to": str(leave.end_date),
        "days": leave.total_days,
        "reason": leave.reason,
        "status": leave.status,
    }


@router.get("/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = (user.role or "").lower()

    leave_query = db.query(LeaveRequest)
    ticket_query = db.query(Ticket)
    asset_query = db.query(AssetRequest)

    if role == "employee":
        leave_query = leave_query.filter(LeaveRequest.employee_id == user.id)
        ticket_query = ticket_query.filter(Ticket.user_id == user.email)
        asset_query = asset_query.filter(AssetRequest.user_id == user.email)
    elif role == "manager":
        team_emails = [e.email for e in db.query(Employee).filter(Employee.manager_id == user.id).all()]
        team_ids = [e.id for e in db.query(Employee).filter(Employee.manager_id == user.id).all()]
        leave_query = leave_query.filter(LeaveRequest.employee_id.in_(team_ids))
        ticket_query = ticket_query.filter(Ticket.user_id.in_(team_emails))
        asset_query = asset_query.filter(AssetRequest.user_id.in_(team_emails))
    elif role in {"hr", "hr_team"}:
        # HR can see all leaves, but not necessarily all IT/asset data.
        pass

    pending_leaves = leave_query.filter(LeaveRequest.status.in_(["pending_manager", "pending_hr"])).count()
    open_tickets = ticket_query.filter(Ticket.status.in_(["open", "in_progress"])).count()
    pending_assets = asset_query.filter(
        AssetRequest.final_status.in_(["pending", "pending_it_approval"])
    ).count()

    data = {
        "pending_leaves": pending_leaves,
        "open_tickets": open_tickets,
        "pending_assets": pending_assets,
        "inventory_items": db.query(Inventory).count() if role in ["it", "it_team", "admin"] else 0,
    }

    if role == "admin":
        data.update({
            "leaves": db.query(LeaveRequest).count(),
            "tickets": db.query(Ticket).count(),
            "assets": db.query(AssetRequest).count(),
            "logs": len(get_logs(db)),
        })

    return data

@router.get("/leaves")
def dashboard_leaves(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = (user.role or "").lower()
    query = db.query(LeaveRequest)

    if role == "employee":
        query = query.filter(LeaveRequest.employee_id == user.id)
    elif role == "manager":
        team_ids = [e.id for e in db.query(Employee).filter(Employee.manager_id == user.id).all()]
        query = query.filter(LeaveRequest.employee_id.in_(team_ids))

    leaves = query.all()

    return [_leave_row(db, l) for l in leaves]


@router.get("/leave-balance")
def dashboard_leave_balance(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return get_leave_balance(db, user.id)


@router.get("/leave-stats")
def dashboard_leave_stats(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """
    Compact leave stats for ChatPage header cards.
    """
    role = (user.role or "").lower()

    base = db.query(LeaveRequest).filter(LeaveRequest.employee_id == user.id)
    pending = base.filter(LeaveRequest.status.in_(["pending_manager", "pending_hr"])).count()
    approved = base.filter(LeaveRequest.status == "approved").count()
    rejected = base.filter(LeaveRequest.status == "rejected").count()
    cancelled = base.filter(LeaveRequest.status == "cancelled").count()

    balance = get_leave_balance(db, user.id)

    manager_pending = 0
    if role == "manager":
        team_ids = [e.id for e in db.query(Employee).filter(Employee.manager_id == user.id).all()]
        manager_pending = (
            db.query(LeaveRequest)
            .filter(LeaveRequest.employee_id.in_(team_ids), LeaveRequest.status == "pending_manager")
            .count()
        )

    hr_pending = 0
    if role == "hr":
        hr_pending = db.query(LeaveRequest).filter(LeaveRequest.status == "pending_hr").count()

    return {
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "cancelled": cancelled,
        "balance": balance,
        "manager_pending_approvals": manager_pending,
        "hr_pending_reviews": hr_pending,
    }


@router.get("/tickets")
def dashboard_tickets(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = (user.role or "").lower()
    query = db.query(Ticket)

    if role == "employee":
        query = query.filter(Ticket.user_id == user.email)
    elif role == "manager":
        team_emails = [e.email for e in db.query(Employee).filter(Employee.manager_id == user.id).all()]
        query = query.filter(Ticket.user_id.in_(team_emails))

    tickets = query.all()

    return [
        {
            "id": t.id,
            "emp": t.user_id,
            "title": t.description,
            "priority": t.priority,
            "status": t.status,
            "assignee": getattr(t, "assigned_to", None) or "—",
            "created": str(t.created_at) if getattr(t, "created_at", None) else ""
        }
        for t in tickets
    ]

@router.get("/pending-assets")
def get_pending_assets(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = (user.role or "").lower()
    query = db.query(AssetRequest)
    if role == "employee":
        query = query.filter(AssetRequest.user_id == user.email)
    elif role == "manager":
        team_emails = [e.email for e in db.query(Employee).filter(Employee.manager_id == user.id).all()]
        query = query.filter(AssetRequest.user_id.in_(team_emails))
    
    return {"success": True, "data": query.all()}

@router.put("/asset/{action}/{request_id}")
def dashboard_update_asset(
    action: str,
    request_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user)
):
    role = payload.get("role")
    # RBAC check: Only manager, IT team, or admin can update status
    user_role = (user.role or "").lower()
    if user_role not in {"manager", "it_team", "admin"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Forbidden")
    
    from actions.asset_action import update_asset_status
    updated = update_asset_status(db, request_id, role, action)
    if not updated:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Asset request not found")
    
    return {"success": True, "data": updated}


@router.get("/inventory")
def dashboard_inventory(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = (user.role or "").lower()
    if role not in ["it", "it_team", "admin"]:
        return []

    items = db.query(Inventory).all()

    return [
        {
            "id": i.id,
            "item": i.asset_type,
            "total": i.total_quantity,
            "available": i.available_quantity,
            "reserved": i.total_quantity - i.available_quantity
        }
        for i in items
    ]


def _log_rows(db: Session, user: Employee):
    role = (user.role or "").lower()
    if role != "admin":
        return {"detail": "Access denied. Only admin can view logs."}

    return [
        {
            "id": log.id,
            "time": str(log.created_at) if log.created_at else "",
            "agent": log.agent,
            "action": log.action,
            "user": log.user_email,
            "status": log.status,
        }
        for log in get_logs(db)
    ]


@router.get("/approvals")
def dashboard_approvals(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    role = (user.role or "").lower()

    # Manager sees pending_manager; HR sees pending_hr.
    leave_query = db.query(LeaveRequest).filter(LeaveRequest.status.in_(["pending_manager", "pending_hr"]))
    manager_asset_query = db.query(AssetRequest).filter(AssetRequest.manager_status == "pending")

    if role == "manager":
        team = db.query(Employee).filter(Employee.manager_id == user.id).all()
        team_ids = [e.id for e in team]
        team_emails = [e.email for e in team]
        leave_query = leave_query.filter(
            LeaveRequest.employee_id.in_(team_ids),
            LeaveRequest.status == "pending_manager",
        )
        manager_asset_query = manager_asset_query.filter(AssetRequest.user_id.in_(team_emails))
    elif role == "hr":
        leave_query = leave_query.filter(LeaveRequest.status == "pending_hr")
    elif role == "admin":
        # Oversight: admin can view pending queues but should not be the default approver.
        pass
    else:
        leave_query = leave_query.filter(False)
        manager_asset_query = manager_asset_query.filter(False)

    it_assets = db.query(AssetRequest).filter(
        AssetRequest.manager_status == "approved",
        AssetRequest.it_status == "pending",
    )
    open_tickets = db.query(Ticket).filter(Ticket.status.in_(["open", "in_progress"]))

    if role not in ["it", "it_team", "admin"]:
        it_assets = it_assets.filter(False)
        open_tickets = open_tickets.filter(False)

    return {
        "leave_approvals": [_leave_row(db, leave) for leave in leave_query.all()]
            if role in ["manager", "hr", "hr_team", "admin"] else [],
        "asset_manager_approvals": [
            {
                "id": a.id,
                "emp": a.user_id,
                "asset": a.asset_type,
                "reason": a.reason,
                "manager_status": a.manager_status,
                "it_status": a.it_status,
                "inventory_status": a.inventory_status,
                "final_status": a.final_status,
                "status": a.final_status,
                "created": str(a.created_at) if a.created_at else "",
            }
            for a in manager_asset_query.all()
        ],
        "asset_it_approvals": [
            {
                "id": a.id,
                "emp": a.user_id,
                "asset": a.asset_type,
                "reason": a.reason,
                "manager_status": a.manager_status,
                "it_status": a.it_status,
                "inventory_status": a.inventory_status,
                "final_status": a.final_status,
                "status": a.final_status,
                "created": str(a.created_at) if a.created_at else "",
            }
            for a in it_assets.all()
        ],
        "open_tickets": [
            {
                "id": t.id,
                "emp": t.user_id,
                "title": t.description,
                "priority": t.priority,
                "status": t.status,
                "assignee": getattr(t, "assigned_to", None) or "—",
                "created": str(t.created_at) if t.created_at else "",
            }
            for t in open_tickets.all()
        ],
    }


@router.get("/logs")
def dashboard_logs(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    return _log_rows(db, user)


@router.get("/employees")
def dashboard_employees(
    db: Session = Depends(get_db),
    user: Employee = Depends(require_roles("admin")),
):

    employees = db.query(Employee).all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "email": e.email,
            "role": e.role,
            "department": e.department,
            "manager_id": e.manager_id,
            "created_at": str(e.created_at) if e.created_at else "",
        }
        for e in employees
    ]


@admin_router.get("/logs")
def admin_logs(
    db: Session = Depends(get_db),
    user: Employee = Depends(require_roles("admin")),
):
    return _log_rows(db, user)



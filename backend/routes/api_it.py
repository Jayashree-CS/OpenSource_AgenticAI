from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from actions.auth_dependency import get_current_user, require_roles
from db.database import SessionLocal
from db.models import Employee, Inventory, Ticket, AssetRequest
from actions.it_action import update_ticket_status, get_all_tickets, TicketTransitionError
from actions.asset_action import get_pending_assets_for_it, approve_asset_by_it, reject_asset_by_it

router = APIRouter(
    prefix="/api/it",
    tags=["API: IT"],
    dependencies=[Depends(require_roles("it_team", "admin"))],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TicketStatusPayload(BaseModel):
    status: str


class InventoryUpsertPayload(BaseModel):
    asset_type: str
    total_quantity: int
    available_quantity: int


@router.get("/tickets")
def it_list_tickets(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    # IT can see all tickets
    rows = get_all_tickets(db)
    return {"success": True, "data": rows, "error": None, "message": "OK"}


@router.put("/tickets/{ticket_id}")
def it_update_ticket_status(
    ticket_id: int,
    payload: TicketStatusPayload,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    status = (payload.status or "").strip().lower()
    try:
        updated = update_ticket_status(db, ticket_id, status, user_role=user.role, user_id=user.email)
    except TicketTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not updated:
        raise HTTPException(status_code=404, detail="Ticket not found or forbidden")
    return {"success": True, "data": updated, "error": None, "message": "OK"}


@router.get("/assets/pending")
def it_pending_assets(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = get_pending_assets_for_it(db)
    return {"success": True, "data": rows, "error": None, "message": "OK"}


@router.post("/assets/{request_id}")
def it_action_asset(
    request_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    action = (payload.get("action") or "").strip().lower()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    # Pre-flight: differentiate "not found" vs "manager hasn't approved yet"
    # vs "already processed" so the IT user sees an accurate error instead
    # of a generic 404 (which previously fired in all three cases).
    existing = db.query(AssetRequest).filter(AssetRequest.id == request_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail=f"Asset request #{request_id} not found")
    if existing.manager_status != "approved":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Asset request #{request_id} is not ready for IT — "
                f"manager status is '{existing.manager_status}'. "
                "It must be approved by the manager first."
            ),
        )
    if existing.it_status != "pending":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Asset request #{request_id} has already been "
                f"{existing.it_status} by IT."
            ),
        )

    if action == "approve":
        res = approve_asset_by_it(db, request_id, it_user_id=user.email)
        if res in {"inventory_not_found", "inventory_unavailable"}:
            return {"success": True, "data": {"status": res}, "error": None, "message": "OK"}
        if not res:
            # Should only happen on a permission failure now that the
            # pre-flight check ruled out missing / wrong-state rows.
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to approve asset requests.",
            )
        return {"success": True, "data": res, "error": None, "message": "OK"}

    res = reject_asset_by_it(db, request_id, it_user_id=user.email)
    if not res:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to reject asset requests.",
        )
    return {"success": True, "data": res, "error": None, "message": "OK"}


@router.get("/inventory")
def it_inventory_list(
    db: Session = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    rows = db.query(Inventory).order_by(Inventory.asset_type).all()
    return {"success": True, "data": rows, "error": None, "message": "OK"}


@router.post("/inventory")
def it_inventory_upsert(
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

from datetime import datetime, timezone
from db.models import Inventory


def check_inventory(db, asset_type: str):
    return db.query(Inventory).filter(
        Inventory.asset_type == asset_type
    ).first()


def reserve_inventory(db, asset_type: str):
    item = check_inventory(db, asset_type)

    if not item:
        return None

    if item.available_quantity <= 0:
        return "unavailable"

    item.available_quantity -= 1
    item.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(item)

    return item
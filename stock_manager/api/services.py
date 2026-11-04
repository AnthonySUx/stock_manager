"""Business logic layer for the Stock Manager API."""

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from stock_manager.api.models import Item, RestockItem, Setting


# ─── Status Calculation ──────────────────────────────────────────


def _calculate_status(
    quantity_value: float,
    current_expiration_date: str,
    warning_days: int,
    today: date,
) -> str:
    """Calculate the current stock status from quantity and expiration date."""
    if quantity_value <= 0:
        return "consumed"

    if current_expiration_date == "infinite":
        return "active"

    try:
        expiration_date = date.fromisoformat(current_expiration_date)
    except ValueError:
        return "active"

    if expiration_date < today:
        return "expired"

    if expiration_date <= today + timedelta(days=warning_days):
        return "expiring soon"

    return "active"


def _get_expiration_warning_days(db: Session) -> int:
    """Return the configured global expiration warning window in days."""
    row = db.query(Setting).filter(Setting.key == "expiration_reminder_days").first()
    if row is None:
        return 2
    try:
        return max(int(row.value), 0)
    except (ValueError, TypeError):
        return 2


def refresh_item_statuses(db: Session) -> int:
    """Refresh all item statuses and return the number of changed rows."""
    today = date.today()
    warning_days = _get_expiration_warning_days(db)
    changed = 0

    items = db.query(Item).all()
    for item in items:
        new_status = _calculate_status(
            item.quantity_value,
            item.current_expiration_date,
            warning_days,
            today,
        )
        if new_status != item.status:
            item.status = new_status
            changed += 1

    db.commit()
    return changed


def calculate_item_status(
    quantity_value: float,
    current_expiration_date: str,
    db: Session,
) -> str:
    """Calculate a single item's status using current global settings."""
    warning_days = _get_expiration_warning_days(db)
    return _calculate_status(
        quantity_value,
        current_expiration_date,
        warning_days,
        date.today(),
    )


# ─── Stock Items ─────────────────────────────────────────────────


def get_items(
    db: Session,
    *,
    category: Optional[int] = None,
    owner: Optional[str] = None,
    location: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Item]:
    """Return stock items that match the optional filters."""
    refresh_item_statuses(db)

    query = db.query(Item)
    if category is not None:
        query = query.filter(Item.category_id == category)
    if owner is not None:
        query = query.filter(func.lower(Item.owner) == owner.lower())
    if location is not None:
        query = query.filter(func.lower(Item.location) == location.lower())
    if status is not None:
        query = query.filter(Item.status == status)

    return query.order_by(Item.id).all()


def search_items(
    db: Session,
    keyword: str,
    *,
    category: Optional[int] = None,
    owner: Optional[str] = None,
    location: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Item]:
    """Return stock items matching a keyword and optional filters."""
    refresh_item_statuses(db)

    from stock_manager.api.models import Category
    pattern = f"%{keyword}%"
    query = db.query(Item).outerjoin(Category, Item.category_id == Category.id).filter(
        func.lower(Item.name).like(pattern.lower())
        | func.lower(Category.name).like(pattern.lower())
        | func.lower(Item.owner).like(pattern.lower())
        | func.lower(Item.location).like(pattern.lower())
        | func.lower(func.coalesce(Item.notes, "")).like(pattern.lower())
    )

    if owner is not None:
        query = query.filter(func.lower(Item.owner) == owner.lower())
    if location is not None:
        query = query.filter(func.lower(Item.location) == location.lower())
    if category is not None:
        query = query.filter(Item.category_id == category)
    if status is not None:
        query = query.filter(Item.status == status)

    return query.order_by(Item.id).all()


def get_item(db: Session, item_id: int) -> Optional[Item]:
    """Return one stock item by id."""
    return db.query(Item).filter(Item.id == item_id).first()


def create_item(db: Session, item_data: dict) -> Item:
    """Create a new stock item."""
    item = Item(**item_data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item_id: int, item_data: dict) -> Optional[Item]:
    """Update an existing stock item."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        return None

    for key, value in item_data.items():
        setattr(item, key, value)

    db.commit()
    db.refresh(item)
    return item


def consume_item(
    db: Session,
    item_id: int,
    quantity: float,
    add_to_restock: bool = False,
) -> Optional[dict]:
    """Consume a portion of a stock item, updating quantity and status."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        return None

    original_quantity = item.quantity_value
    new_quantity = max(0.0, original_quantity - quantity)
    item.quantity_value = new_quantity

    today = date.today()
    warning_days = _get_expiration_warning_days(db)
    new_status = _calculate_status(
        new_quantity,
        item.current_expiration_date,
        warning_days,
        today,
    )
    item.status = new_status
    db.commit()
    db.refresh(item)

    result = {"item": item, "restock_item": None}

    if new_quantity <= 0 and add_to_restock:
        restock = RestockItem(
            name=item.name,
            category_id=item.category_id,
            quantity_value=original_quantity,
            quantity_unit=item.quantity_unit,
            source_item_id=item.id,
            status="pending",
            notes=item.notes,
        )
        db.add(restock)
        db.commit()
        db.refresh(restock)
        result["restock_item"] = restock

    return result


def delete_item(db: Session, item_id: int) -> bool:
    """Delete a stock item and clear restock references."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        return False

    # Clear foreign key references in restock_items
    db.query(RestockItem).filter(RestockItem.source_item_id == item_id).update(
        {RestockItem.source_item_id: None}
    )
    db.delete(item)
    db.commit()
    return True


def delete_items_by_statuses(db: Session, statuses: list[str]) -> int:
    """Delete items matching the given statuses."""
    if not statuses:
        return 0

    refresh_item_statuses(db)

    items = db.query(Item).filter(Item.status.in_(statuses)).all()
    item_ids = [item.id for item in items]

    if not item_ids:
        return 0

    # Clear foreign key references
    db.query(RestockItem).filter(
        RestockItem.source_item_id.in_(item_ids)
    ).update({RestockItem.source_item_id: None}, synchronize_session=False)

    deleted = db.query(Item).filter(Item.id.in_(item_ids)).delete(
        synchronize_session=False
    )
    db.commit()
    return deleted


# ─── Restock Items ───────────────────────────────────────────────


def get_restock_items(
    db: Session,
    *,
    status: Optional[str] = None,
) -> list[RestockItem]:
    """Return restock items that match the optional status filter."""
    query = db.query(RestockItem)
    if status is not None:
        query = query.filter(RestockItem.status == status)

    return query.order_by(
        RestockItem.status == "done", RestockItem.id
    ).all()


def get_restock_item(db: Session, item_id: int) -> Optional[RestockItem]:
    """Return one restock item by id."""
    return db.query(RestockItem).filter(RestockItem.id == item_id).first()


def create_restock_item(db: Session, item_data: dict) -> RestockItem:
    """Create a new restock item."""
    item = RestockItem(**item_data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_restock_item(
    db: Session, item_id: int, item_data: dict
) -> Optional[RestockItem]:
    """Update a restock item."""
    item = db.query(RestockItem).filter(RestockItem.id == item_id).first()
    if item is None:
        return None

    for key, value in item_data.items():
        setattr(item, key, value)

    # Handle done_at
    if item_data.get("status") == "done" and item.done_at is None:
        item.done_at = datetime.utcnow()
    elif item_data.get("status") == "pending":
        item.done_at = None

    db.commit()
    db.refresh(item)
    return item


def mark_restock_item_done(db: Session, item_id: int) -> bool:
    """Mark a restock item as done."""
    item = db.query(RestockItem).filter(RestockItem.id == item_id).first()
    if item is None or item.status == "done":
        return False

    item.status = "done"
    item.done_at = datetime.utcnow()
    db.commit()
    return True


def update_restock_item_quantity(db: Session, item_id: int, quantity: float) -> bool:
    """Update the remaining quantity for a pending restock item."""
    item = db.query(RestockItem).filter(
        RestockItem.id == item_id,
        RestockItem.status == "pending",
    ).first()
    if item is None:
        return False

    item.quantity_value = quantity
    db.commit()
    return True


def delete_restock_item(db: Session, item_id: int) -> bool:
    """Delete a restock item."""
    item = db.query(RestockItem).filter(RestockItem.id == item_id).first()
    if item is None:
        return False

    db.delete(item)
    db.commit()
    return True


def delete_restock_items_by_status(db: Session, status: str) -> int:
    """Delete restock items by status."""
    deleted = (
        db.query(RestockItem)
        .filter(RestockItem.status == status)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


# ─── Settings ────────────────────────────────────────────────────


def get_settings(db: Session) -> dict[str, str]:
    """Return current settings."""
    defaults = {
        "default_database": "stock.db",
        "expiration_reminder_days": "2",
    }

    rows = db.query(Setting).all()
    for row in rows:
        defaults[row.key] = row.value

    return defaults


def update_settings(db: Session, settings: dict[str, str]) -> dict[str, str]:
    """Update settings and return the current state."""
    now = datetime.utcnow()

    for key, value in settings.items():
        if value is None:
            continue
        existing = db.query(Setting).filter(Setting.key == key).first()
        if existing:
            existing.value = str(value)
            existing.updated_at = now
        else:
            db.add(Setting(key=key, value=str(value), updated_at=now))

    db.commit()
    return get_settings(db)

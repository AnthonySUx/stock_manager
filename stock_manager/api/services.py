"""Business logic layer for the Stock Manager API."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session, selectinload

from stock_manager.api.category_services import RECIPE_USAGE_NEVER
from stock_manager.api.errors import APIError
from stock_manager.api.localization import today as household_today
from stock_manager.api.models import Category, Item, RestockItem, Setting, utcnow
from stock_manager.api.quantity import quantize_stock_quantity


# ─── Status Calculation ──────────────────────────────────────────


def _calculate_status(
    quantity_value: Decimal | float,
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


def refresh_item_statuses(db: Session, *, commit: bool = True) -> int:
    """Refresh stale statuses in bulk and return the number of changed rows."""
    today = household_today(db)
    warning_days = _get_expiration_warning_days(db)
    first_day = today.isoformat()
    last_day = (today + timedelta(days=warning_days)).isoformat()
    expiration = Item.current_expiration_date
    has_expiration = expiration != "infinite"
    in_stock = Item.quantity_value > 0
    conditions = (
        ("consumed", Item.quantity_value <= 0),
        ("expired", in_stock & has_expiration & (expiration < first_day)),
        ("expiring soon", in_stock & has_expiration & expiration.between(first_day, last_day)),
        ("active", in_stock & ((expiration > last_day) | ~has_expiration)),
    )

    changed = 0
    for status, condition in conditions:
        changed += db.query(Item).filter(condition, Item.status != status).update(
            {Item.status: status}, synchronize_session=False,
        )

    if changed and commit:
        db.commit()
    return changed


def ensure_fresh_statuses(db: Session) -> None:
    """Refresh stored statuses before querying by status."""
    refresh_item_statuses(db)


def calculate_item_status(
    quantity_value: Decimal | float,
    current_expiration_date: str,
    db: Session,
) -> str:
    """Calculate a single item's status using current global settings."""
    warning_days = _get_expiration_warning_days(db)
    return _calculate_status(
        quantity_value,
        current_expiration_date,
        warning_days,
        household_today(db),
    )


# ─── Stock Items ─────────────────────────────────────────────────


def get_items(
    db: Session,
    *,
    category: Optional[int] = None,
    owner: Optional[str] = None,
    location: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[Item]:
    """Return stock items that match the optional filters."""
    ensure_fresh_statuses(db)

    query = db.query(Item).options(selectinload(Item.category))
    if category is not None:
        query = query.filter(Item.category_id == category)
    if owner is not None:
        query = query.filter(func.lower(Item.owner) == owner.lower())
    if location is not None:
        query = query.filter(func.lower(Item.location) == location.lower())
    if status is not None:
        query = query.filter(Item.status == status)

    query = query.order_by(Item.id)
    if limit is not None:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)
    return query.all()


# Reminders list "expiring soon" first, then "expired"; each by id.
REMINDER_STATUSES = ("expiring soon", "expired")


def get_reminder_items(db: Session) -> list[Item]:
    """Items that are expiring soon or expired: one refresh, one query (#48)."""
    ensure_fresh_statuses(db)
    return (
        db.query(Item)
        .filter(Item.status.in_(REMINDER_STATUSES))
        .order_by(case((Item.status == REMINDER_STATUSES[0], 0), else_=1), Item.id)
        .all()
    )


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
    ensure_fresh_statuses(db)

    from stock_manager.api.models import Category
    from stock_manager.api.text_search import contains_ci

    query = db.query(Item).outerjoin(Category, Item.category_id == Category.id).filter(
        contains_ci(Item.name, keyword)
        | contains_ci(Category.name, keyword)
        | contains_ci(Item.owner, keyword)
        | contains_ci(Item.location, keyword)
        | contains_ci(func.coalesce(Item.notes, ""), keyword)
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


def calculate_current_expiration_date(item_data: dict) -> str:
    """Determine the effective expiration date for new stock items."""
    opened_date = item_data.get("opened_date")
    opened_expiration = item_data.get("opened_expiration_date")
    unopened_expiration = item_data.get("unopened_expiration_date", "infinite")

    if opened_date and opened_expiration:
        return opened_expiration

    return unopened_expiration


def derive_item_dates_and_status(
    data: dict, db: Session, *, validate_purchase_date: bool = True,
) -> dict:
    """Validate the input dates and compute the effective date and stock status."""
    purchase_date = data.get("purchase_date")
    unopened_expiration = data.get("unopened_expiration_date", "infinite")
    if (
        validate_purchase_date and purchase_date and unopened_expiration != "infinite"
        and unopened_expiration < purchase_date
    ):
        raise APIError(
            422, "expiration_before_purchase", "Unopened expiration date precedes purchase date"
        )

    opened_date = data.get("opened_date")
    opened_expiration = data.get("opened_expiration_date")
    if (
        opened_date and opened_expiration and opened_expiration != "infinite"
        and opened_expiration < opened_date
    ):
        raise APIError(
            422, "opened_expiration_before_opened", "Opened expiration date precedes opening date"
        )

    expiration = calculate_current_expiration_date(data)
    return {
        "current_expiration_date": expiration,
        "status": calculate_item_status(data["quantity_value"], expiration, db),
    }


def prepare_item_data(db: Session, data: dict) -> dict:
    """Derive expiration and status, then fill in a missing purchase date."""
    item_data = {**data, **derive_item_dates_and_status(data, db)}
    if item_data.get("purchase_date") is None:
        item_data["purchase_date"] = household_today(db).isoformat()
    return item_data


def _with_stock_quantity(data: dict) -> dict:
    quantity = data.get("quantity_value")
    if quantity is None:
        return data
    return {**data, "quantity_value": quantize_stock_quantity(quantity)}


def create_item(db: Session, item_data: dict, *, commit: bool = True) -> Item:
    """Create a stock item, leaving the transaction open when requested."""
    item = Item(**_with_stock_quantity(item_data))
    db.add(item)
    if commit:
        db.commit()
        db.refresh(item)
    else:
        db.flush()
    return item


def update_item(db: Session, item_id: int, item_data: dict) -> Optional[Item]:
    """Update an existing stock item."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if item is None:
        return None

    for key, value in _with_stock_quantity(item_data).items():
        setattr(item, key, value)

    db.commit()
    db.refresh(item)
    return item


def deduct_item_quantity(
    db: Session, item_id: int, quantity: Decimal | float, *, recipe_only: bool = False,
) -> tuple[Item | None, bool]:
    """Attempt a guarded deduction and read the current row in the caller's transaction."""
    quantity = quantize_stock_quantity(quantity)
    if quantity <= 0:
        raise ValueError("Consumption quantity must be positive and finite")

    stock = db.query(Item).filter(
        Item.id == item_id,
        Item.quantity_value >= quantity,
        Item.status != "consumed",
    )
    if recipe_only:
        stock = stock.filter(Item.category.has(Category.recipe_usage != RECIPE_USAGE_NEVER))
    # SQLite evaluates Numeric arithmetic as floats. Keep stored results at scale.
    deducted = stock.update(
        {Item.quantity_value: func.round(Item.quantity_value - quantity, 3)},
        synchronize_session=False,
    ) == 1

    # Read the current row even if the session already held a stale snapshot.
    item = db.query(Item).filter(Item.id == item_id).populate_existing().with_for_update().first()
    if deducted:
        item.status = calculate_item_status(item.quantity_value, item.current_expiration_date, db)
    return item, deducted


def _add_stock_to_restock(
    db: Session, item: Item, quantity: Decimal | float, *, source_item_id: int | None,
) -> RestockItem:
    """Queue a restock row for the caller to commit."""
    restock = RestockItem(
        name=item.name,
        category_id=item.category_id,
        quantity_value=quantize_stock_quantity(quantity),
        quantity_unit=item.quantity_unit,
        source_item_id=source_item_id,
        status="pending",
        notes=item.notes,
    )
    db.add(restock)
    return restock


def consume_item(
    db: Session,
    item_id: int,
    quantity: Decimal | float,
    add_to_restock: bool = False,
) -> Optional[dict]:
    """Deduct stock and optionally queue the consumed amount for restock."""
    try:
        item, deducted = deduct_item_quantity(db, item_id, quantity)
        if item is None:
            db.rollback()
            return None
        if not deducted:
            if item.status == "consumed" or item.quantity_value <= 0:
                raise APIError(409, "item_already_consumed", "Item is already consumed")
            raise APIError(
                422, "consume_exceeds_stock", "Consumption quantity exceeds available stock",
                available=float(item.quantity_value),
            )

        restock = (
            _add_stock_to_restock(db, item, quantity, source_item_id=item.id)
            if add_to_restock else None
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"item": item, "restock_item": restock}


def delete_item(db: Session, item_id: int, *, add_to_restock: bool = False) -> bool:
    """Delete stock, clear references, and optionally queue restock atomically."""
    try:
        stock = db.query(Item).filter(Item.id == item_id)
        item = stock.populate_existing().with_for_update().first()
        if item is None:
            db.rollback()
            return False

        db.query(RestockItem).filter(RestockItem.source_item_id == item_id).update(
            {RestockItem.source_item_id: None}
        )
        if stock.delete(synchronize_session="fetch") != 1:
            db.rollback()
            return False
        if add_to_restock and item.quantity_value > 0:
            _add_stock_to_restock(db, item, item.quantity_value, source_item_id=None)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def delete_items_by_statuses(db: Session, statuses: list[str]) -> int:
    """Delete items matching the given statuses."""
    if not statuses:
        return 0

    ensure_fresh_statuses(db)

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
    shopping_checked: Optional[bool] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> list[RestockItem]:
    """Return restock items that match the optional status and shopping filters."""
    query = db.query(RestockItem).options(selectinload(RestockItem.category))
    if status is not None:
        query = query.filter(RestockItem.status == status)
    if shopping_checked is not None:
        checked_at = RestockItem.shopping_checked_at
        query = query.filter(checked_at.is_not(None) if shopping_checked else checked_at.is_(None))

    query = query.order_by(RestockItem.status == "done", RestockItem.id)
    if limit is not None:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)
    return query.all()


def find_restock_duplicates(db: Session, name: str) -> dict:
    """Return pending restock items with the same or a synonym name (#18).

    Matching uses the same rule as "missing ingredients to restock": two names
    match when their synonym-normalized, lower-cased forms are equal. There is
    no substring matching, so "egg" does not match "eggplant". Read-only.
    """
    # Imported here: recipe_services imports this module.
    from stock_manager.api.recipe_services import _normalize_name

    query = name.strip()
    key = _normalize_name(query).lower()
    pending = (
        db.query(RestockItem)
        .options(selectinload(RestockItem.category))
        .filter(RestockItem.status == "pending")
        .order_by(RestockItem.id)
    )
    candidates = []
    for item in pending:
        if _normalize_name(item.name).lower() != key:
            continue
        same_name = item.name.strip().lower() == query.lower()
        candidates.append({"item": item, "match_reason": "same_name" if same_name else "synonym"})
    return {"query": query, "normalized_name": _normalize_name(query), "candidates": candidates}


def get_restock_item(db: Session, item_id: int) -> Optional[RestockItem]:
    """Return one restock item by id."""
    return db.query(RestockItem).filter(RestockItem.id == item_id).first()


def create_restock_item(db: Session, item_data: dict) -> RestockItem:
    """Create a new restock item."""
    item = RestockItem(**_with_stock_quantity(item_data))
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

    for key, value in _with_stock_quantity(item_data).items():
        setattr(item, key, value)

    # Handle done_at
    if item_data.get("status") == "done" and item.done_at is None:
        item.done_at = utcnow()
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
    item.done_at = utcnow()
    db.commit()
    return True


def update_restock_item_quantity(db: Session, item_id: int, quantity: Decimal | float) -> bool:
    """Update the remaining quantity for a pending restock item."""
    item = db.query(RestockItem).filter(
        RestockItem.id == item_id,
        RestockItem.status == "pending",
    ).first()
    if item is None:
        return False

    item.quantity_value = quantize_stock_quantity(quantity)
    db.commit()
    return True


class RestockAlreadyDoneError(Exception):
    """Raised when a restock item is no longer pending (already done)."""


def apply_restock_purchase(
    db: Session,
    restock_item: RestockItem,
    purchased_quantity: Decimal | float,
    stock_data: dict,
) -> Item:
    """Add a purchase to stock and update restock in the caller's transaction.

    The restock row is updated with a guarded UPDATE (still pending, quantity
    unchanged since it was read), so a repeated or concurrent request cannot
    add the same purchase twice. The caller manages commit and rollback.

    Raises:
        RestockAlreadyDoneError: the item is done, or changed since it was read.
    """
    purchased_quantity = quantize_stock_quantity(purchased_quantity)
    observed_qty = restock_item.quantity_value
    original_qty = observed_qty or purchased_quantity
    remaining = original_qty - purchased_quantity

    guard = db.query(RestockItem).filter(
        RestockItem.id == restock_item.id,
        RestockItem.status == "pending",
    )
    if observed_qty is None:
        guard = guard.filter(RestockItem.quantity_value.is_(None))
    else:
        guard = guard.filter(RestockItem.quantity_value == observed_qty)

    if remaining > 0:
        # The rest still has to be bought, so it goes back on the shopping list.
        values = {RestockItem.quantity_value: remaining, RestockItem.shopping_checked_at: None}
    else:
        values = {RestockItem.status: "done", RestockItem.done_at: utcnow()}

    updated = guard.update(values, synchronize_session=False)
    if updated != 1:
        raise RestockAlreadyDoneError(restock_item.id)

    stock_item = create_item(db, stock_data, commit=False)
    db.expire(restock_item)
    return stock_item


def complete_restock_purchase(
    db: Session,
    restock_item: RestockItem,
    purchased_quantity: Decimal | float,
    stock_data: dict,
) -> Item:
    """Commit a standalone restock purchase or roll back both writes."""
    try:
        stock_item = apply_restock_purchase(db, restock_item, purchased_quantity, stock_data)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(stock_item)
    return stock_item


def set_restock_shopping_checked(db: Session, item_id: int, checked: bool) -> Optional[RestockItem]:
    """Check or uncheck a pending restock item while shopping (#22).

    Checking keeps the first check time; repeating either call changes nothing.
    It never touches stock or `status`.

    Raises:
        RestockAlreadyDoneError: the item is done.
    """
    item = get_restock_item(db, item_id)
    if item is None:
        return None
    if item.status == "done":
        raise RestockAlreadyDoneError(item_id)
    if checked and item.shopping_checked_at is None:
        item.shopping_checked_at = utcnow()
    elif not checked:
        item.shopping_checked_at = None
    if db.is_modified(item):
        db.commit()
        db.refresh(item)
    return item


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


DEFAULT_SETTINGS = {"expiration_reminder_days": "2"}


def get_settings(db: Session) -> dict[str, str]:
    """Return current settings. Old rows such as `default_database` may be
    included; SettingResponse returns only the known keys."""
    settings = dict(DEFAULT_SETTINGS)
    for row in db.query(Setting):
        settings[row.key] = row.value
    return settings


def update_settings(db: Session, settings: dict[str, str]) -> dict[str, str]:
    """Update settings and return the current state."""
    now = utcnow()

    for key, value in settings.items():
        if value is None:
            continue
        existing = db.query(Setting).filter(Setting.key == key).first()
        if value == "":
            # An empty value clears an optional setting (#65).
            if existing:
                db.delete(existing)
            continue
        if existing:
            existing.value = str(value)
            existing.updated_at = now
        else:
            db.add(Setting(key=key, value=str(value), updated_at=now))

    if {"expiration_reminder_days", "default_timezone"} & settings.keys():
        db.flush()
        refresh_item_statuses(db, commit=False)
    db.commit()
    return get_settings(db)

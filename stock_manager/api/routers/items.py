"""Stock items REST API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from stock_manager.api import schemas
from stock_manager.api.db import get_session
from stock_manager.api.services import (
    consume_item,
    create_item,
    delete_item,
    delete_items_by_statuses,
    derive_item_dates_and_status,
    get_item,
    get_items,
    get_reminder_items,
    prepare_item_data,
    search_items as search_items_service,
    update_item,
)

router = APIRouter()

# Statuses that POST /clean may delete in bulk (issue #40).
CLEANABLE_ITEM_STATUSES = {"consumed", "expired"}


@router.get("", response_model=list[schemas.ItemResponse])
def list_items(
    category: Optional[int] = Query(None),
    owner: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """List stock items with optional filters."""
    return get_items(
        db,
        category=category,
        owner=owner,
        location=location,
        status=status,
    )


@router.get("/search", response_model=list[schemas.ItemResponse])
def search_items(
    keyword: str = Query(..., min_length=1),
    category: Optional[int] = Query(None),
    owner: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """Search stock items by keyword and optional filters."""
    return search_items_service(
        db,
        keyword,
        category=category,
        owner=owner,
        location=location,
        status=status,
    )


@router.get("/reminders", response_model=list[schemas.ItemResponse])
def reminders(
    db: Session = Depends(get_session),
):
    """Return items that are expiring soon (first) or expired, each by id."""
    return get_reminder_items(db)


@router.get("/{item_id}", response_model=schemas.ItemResponse)
def get_item_endpoint(
    item_id: int,
    db: Session = Depends(get_session),
):
    """Get a single stock item by ID."""
    item = get_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("", response_model=schemas.ItemResponse, status_code=201)
def create_item_endpoint(
    payload: schemas.ItemCreate,
    db: Session = Depends(get_session),
):
    """Create a new stock item."""
    from stock_manager.api.category_services import validate_category_exists
    try:
        validate_category_exists(db, payload.category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    item_data = prepare_item_data(db, payload.model_dump())
    return create_item(db, item_data)


@router.patch("/{item_id}", response_model=schemas.ItemResponse)
def update_item_endpoint(
    item_id: int,
    payload: schemas.ItemUpdate,
    db: Session = Depends(get_session),
):
    """Update one or more fields of a stock item."""
    item_data = payload.model_dump(exclude_unset=True)

    if not item_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    from stock_manager.api.category_services import validate_category_exists
    if "category_id" in item_data:
        try:
            validate_category_exists(db, item_data["category_id"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    existing = get_item(db, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Item not found")

    if "opened_date" in item_data and item_data["opened_date"] is None:
        item_data["opened_expiration_date"] = None

    fields = (
        "purchase_date", "unopened_expiration_date", "opened_date",
        "opened_expiration_date", "quantity_value",
    )
    merged = {field: item_data.get(field, getattr(existing, field)) for field in fields}
    item_data.update(derive_item_dates_and_status(
        merged, db,
        validate_purchase_date=bool({"purchase_date", "unopened_expiration_date"} & item_data.keys()),
    ))

    result = update_item(db, item_id, item_data)
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return result


@router.post("/{item_id}/consume", response_model=schemas.ConsumeResponse)
def consume_item_endpoint(
    item_id: int,
    payload: schemas.ConsumeRequest,
    db: Session = Depends(get_session),
):
    """Consume a portion of a stock item."""
    result = consume_item(
        db,
        item_id,
        quantity=payload.quantity,
        add_to_restock=payload.add_to_restock,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found")
    data = schemas.ItemResponse.model_validate(result["item"]).model_dump()
    return schemas.ConsumeResponse(**data, restock_item=result["restock_item"])


@router.delete("/{item_id}", response_model=schemas.MessageResponse)
def delete_item_endpoint(
    item_id: int,
    add_to_restock: bool = Query(False),
    db: Session = Depends(get_session),
):
    """Delete a stock item and optionally queue its remaining amount for restock."""
    if not delete_item(db, item_id, add_to_restock=add_to_restock):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted"}


@router.post("/clean", response_model=schemas.MessageResponse)
def clean_items(
    statuses: list[str] = Query(default=["consumed"]),
    db: Session = Depends(get_session),
):
    """Batch delete items by statuses (default: consumed).

    Only finished items can be cleaned: `consumed` and `expired`. Active and
    expiring-soon stock must be deleted one by one.
    """
    disallowed = sorted(set(statuses) - CLEANABLE_ITEM_STATUSES)
    if disallowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot clean items with status {disallowed}. Allowed: {sorted(CLEANABLE_ITEM_STATUSES)}",
        )
    count = delete_items_by_statuses(db, statuses)
    return {"message": f"{count} item(s) deleted"}

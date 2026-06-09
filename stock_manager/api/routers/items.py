"""Stock items REST API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from stock_manager.api import schemas
from stock_manager.api.db import get_session
from stock_manager.api.services import (
    calculate_item_status,
    consume_item,
    create_item,
    delete_item,
    delete_items_by_statuses,
    get_item,
    get_items,
    search_items as search_items_service,
    update_item,
)

router = APIRouter()


def _calculate_current_expiration_date(item_data: dict) -> str:
    """Determine the effective expiration date for new stock items."""
    opened_date = item_data.get("opened_date")
    opened_expiration = item_data.get("opened_expiration_date")
    unopened_expiration = item_data.get("unopened_expiration_date", "infinite")

    if opened_date and opened_expiration:
        return opened_expiration

    return unopened_expiration


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
    """Return items that are expiring soon or expired."""
    items = get_items(db, status="expiring soon")
    expired = get_items(db, status="expired")
    return items + expired


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

    item_data = payload.model_dump()
    item_data["current_expiration_date"] = _calculate_current_expiration_date(
        item_data
    )

    # Calculate initial status
    item_data["status"] = calculate_item_status(
        item_data["quantity_value"],
        item_data["current_expiration_date"],
        db,
    )

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

    # Recalculate current_expiration_date if relevant fields changed
    if any(k in item_data for k in ("opened_date", "opened_expiration_date", "unopened_expiration_date")):
        existing = get_item(db, item_id)
        if existing:
            merged = {
                "opened_date": item_data.get("opened_date", existing.opened_date),
                "opened_expiration_date": item_data.get(
                    "opened_expiration_date", existing.opened_expiration_date
                ),
                "unopened_expiration_date": item_data.get(
                    "unopened_expiration_date", existing.unopened_expiration_date
                ),
            }
            item_data["current_expiration_date"] = (
                _calculate_current_expiration_date(merged)
            )

    # Refresh status from quantity or expiration changes
    if "quantity_value" in item_data or "current_expiration_date" in item_data:
        existing = get_item(db, item_id)
        if existing:
            qty = item_data.get("quantity_value", existing.quantity_value)
            exp = item_data.get(
                "current_expiration_date", existing.current_expiration_date
            )
            item_data["status"] = calculate_item_status(qty, exp, db)

    result = update_item(db, item_id, item_data)
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return result


@router.post("/{item_id}/consume", response_model=schemas.ItemResponse)
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
    return result["item"]


@router.delete("/{item_id}", response_model=schemas.MessageResponse)
def delete_item_endpoint(
    item_id: int,
    db: Session = Depends(get_session),
):
    """Delete a stock item."""
    if not delete_item(db, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted"}


@router.post("/clean", response_model=schemas.MessageResponse)
def clean_items(
    statuses: list[str] = Query(default=["consumed"]),
    db: Session = Depends(get_session),
):
    """Batch delete items by statuses (default: consumed)."""
    count = delete_items_by_statuses(db, statuses)
    return {"message": f"{count} item(s) deleted"}

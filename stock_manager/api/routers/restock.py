"""Restock items REST API router."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from stock_manager.api import schemas
from stock_manager.api.db import get_session
from stock_manager.api.services import (
    create_item,
    create_restock_item,
    delete_restock_item,
    delete_restock_items_by_status,
    get_item,
    get_restock_item,
    get_restock_items,
    mark_restock_item_done,
    update_restock_item,
    update_restock_item_quantity,
)

router = APIRouter()


@router.get("", response_model=list[schemas.RestockItemResponse])
def list_restock(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    """List restock items, optionally filtered by status."""
    return get_restock_items(db, status=status)


@router.get("/{item_id}", response_model=schemas.RestockItemResponse)
def get_restock_endpoint(
    item_id: int,
    db: Session = Depends(get_session),
):
    """Get a single restock item by ID."""
    item = get_restock_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Restock item not found")
    return item


@router.post("", response_model=schemas.RestockItemResponse, status_code=201)
def add_restock(
    payload: schemas.RestockItemCreate,
    db: Session = Depends(get_session),
):
    """Add a new item to the restock list."""
    item_data = payload.model_dump()
    item_data["status"] = "pending"
    return create_restock_item(db, item_data)


@router.patch("/{item_id}", response_model=schemas.RestockItemResponse)
def edit_restock(
    item_id: int,
    payload: schemas.RestockItemUpdate,
    db: Session = Depends(get_session),
):
    """Update one or more fields of a restock item."""
    item_data = {k: v for k, v in payload.model_dump().items() if v is not None}

    if not item_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = update_restock_item(db, item_id, item_data)
    if result is None:
        raise HTTPException(status_code=404, detail="Restock item not found")
    return result


@router.post("/{item_id}/done", response_model=schemas.MessageResponse)
def done_restock(
    item_id: int,
    payload: schemas.RestockDoneRequest,
    db: Session = Depends(get_session),
):
    """Mark a restock item as done, optionally adding purchased items to stock.

    If the purchased quantity is less than the restock quantity, the remaining
    quantity stays on the restock list as pending.
    """
    item = get_restock_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Restock item not found")

    purchased_qty = payload.purchased_quantity
    original_qty = item.quantity_value or purchased_qty

    # Add the purchased item(s) to stock
    final_category_id = payload.category_id or item.category_id
    if final_category_id is None:
        raise HTTPException(status_code=400, detail="Category is required when restocking into inventory")
    from stock_manager.api.category_services import validate_category_exists
    try:
        validate_category_exists(db, final_category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    stock_item = create_item(
        db,
        {
            "name": item.name,
            "category_id": final_category_id,
            "owner": payload.owner or "",
            "purchase_date": payload.purchase_date or date.today().isoformat(),
            "quantity_value": purchased_qty,
            "quantity_unit": item.quantity_unit or "pcs",
            "location": payload.location or "",
            "unopened_expiration_date": payload.unopened_expiration_date or "infinite",
            "opened_expiration_date": payload.opened_expiration_date,
            "opened_date": payload.opened_date,
            "current_expiration_date": payload.unopened_expiration_date or "infinite",
            "status": "active",
            "notes": item.notes,
        },
    )

    # If purchased less than asked, keep the rest as pending
    remaining = original_qty - purchased_qty
    if remaining > 0:
        update_restock_item_quantity(db, item_id, remaining)
    else:
        # Fully purchased: mark as done
        mark_restock_item_done(db, item_id)

    return {"message": f"Added {purchased_qty} {item.quantity_unit or 'pcs'} to stock"}


@router.delete("/{item_id}", response_model=schemas.MessageResponse)
def delete_restock_endpoint(
    item_id: int,
    db: Session = Depends(get_session),
):
    """Delete a restock item."""
    if not delete_restock_item(db, item_id):
        raise HTTPException(status_code=404, detail="Restock item not found")
    return {"message": "Restock item deleted"}


@router.post("/clean", response_model=schemas.MessageResponse)
def clean_restock(
    status: str = Query(default="done"),
    db: Session = Depends(get_session),
):
    """Batch delete restock items by status (default: done)."""
    count = delete_restock_items_by_status(db, status)
    return {"message": f"{count} restock item(s) deleted"}

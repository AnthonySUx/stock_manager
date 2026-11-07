"""Restock items REST API router."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from stock_manager.api import schemas
from stock_manager.api.db import get_session
from stock_manager.api.services import (
    RestockAlreadyDoneError,
    complete_restock_purchase,
    create_restock_item,
    delete_restock_item,
    delete_restock_items_by_status,
    get_item,
    get_restock_item,
    get_restock_items,
    update_restock_item,
)

router = APIRouter()

RESTOCK_ALREADY_DONE_DETAIL = "Restock item is already done"


def _validate_references(
    db: Session,
    category_id: Optional[int] = None,
    source_item_id: Optional[int] = None,
) -> None:
    """Return 400 for a category or source item that does not exist (issue #43)."""
    from stock_manager.api.category_services import validate_category_exists
    if category_id is not None:
        try:
            validate_category_exists(db, category_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if source_item_id is not None and get_item(db, source_item_id) is None:
        raise HTTPException(
            status_code=400, detail=f"Source item id={source_item_id} not found"
        )


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
    _validate_references(db, payload.category_id, payload.source_item_id)
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

    _validate_references(db, item_data.get("category_id"))
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
    """Add a purchase to stock and mark the restock item done.

    If the purchased quantity is less than the restock quantity, the remaining
    quantity stays on the restock list as pending.

    Returns 409 if the item is already done (or changed by another request);
    the stock item and restock update are written in a single transaction.
    """
    item = get_restock_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Restock item not found")
    if item.status == "done":
        raise HTTPException(status_code=409, detail=RESTOCK_ALREADY_DONE_DETAIL)

    purchased_qty = payload.purchased_quantity

    # Add the purchased item(s) to stock
    final_category_id = payload.category_id or item.category_id
    if final_category_id is None:
        raise HTTPException(status_code=400, detail="Category is required when restocking into inventory")
    from stock_manager.api.category_services import validate_category_exists
    try:
        validate_category_exists(db, final_category_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    stock_data = {
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
    }
    unit = item.quantity_unit or "pcs"

    try:
        complete_restock_purchase(db, item, purchased_qty, stock_data)
    except RestockAlreadyDoneError:
        raise HTTPException(status_code=409, detail=RESTOCK_ALREADY_DONE_DETAIL)

    return {"message": f"Added {purchased_qty} {unit} to stock"}


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
    """Batch delete restock items by status (default: done).

    Only `done` items can be cleaned; pending items must be deleted one by one.
    """
    if status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot clean restock items with status '{status}'. Allowed: ['done']",
        )
    count = delete_restock_items_by_status(db, status)
    return {"message": f"{count} restock item(s) deleted"}

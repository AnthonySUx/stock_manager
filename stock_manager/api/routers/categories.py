"""Categories REST API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from stock_manager.api import schemas
from stock_manager.api.db import get_session
from stock_manager.api.category_services import (
    create_category,
    delete_category,
    get_category,
    get_category_tree,
    get_categories_flat,
    update_category,
)

router = APIRouter()


@router.get('', response_model=list[schemas.CategoryTreeResponse])
def list_categories_tree(db: Session = Depends(get_session)):
    return get_category_tree(db)


@router.get('/flat', response_model=list[schemas.CategoryResponse])
def list_categories_flat(db: Session = Depends(get_session)):
    return get_categories_flat(db)


@router.get('/{category_id}', response_model=schemas.CategoryResponse)
def get_category_endpoint(category_id: int, db: Session = Depends(get_session)):
    cat = get_category(db, category_id)
    if cat is None:
        raise HTTPException(status_code=404, detail='Category not found')
    return cat


@router.post('', response_model=schemas.CategoryResponse, status_code=201)
def create_category_endpoint(
    payload: schemas.CategoryCreate,
    db: Session = Depends(get_session),
):
    try:
        return create_category(db, payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch('/{category_id}', response_model=schemas.CategoryResponse)
def update_category_endpoint(
    category_id: int,
    payload: schemas.CategoryUpdate,
    db: Session = Depends(get_session),
):
    try:
        result = update_category(db, category_id, payload.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail='Category not found')
    return result


@router.delete('/{category_id}', response_model=schemas.MessageResponse)
def delete_category_endpoint(
    category_id: int,
    db: Session = Depends(get_session),
):
    try:
        ok = delete_category(db, category_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail='Category not found')
    return {'message': 'Category deleted'}

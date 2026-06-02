"""Settings REST API router."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from stock_manager.api import schemas
from stock_manager.api.db import get_session
from stock_manager.api.services import get_settings, update_settings

router = APIRouter()


@router.get("", response_model=schemas.SettingResponse)
def read_settings(
    db: Session = Depends(get_session),
):
    """Get current global settings."""
    return get_settings(db)


@router.patch("", response_model=schemas.SettingResponse)
def patch_settings(
    payload: schemas.SettingUpdate,
    db: Session = Depends(get_session),
):
    """Update one or more settings."""
    settings_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    return update_settings(db, settings_data)

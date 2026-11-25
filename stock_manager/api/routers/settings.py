"""Settings REST API router."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from stock_manager.api import schemas
from stock_manager.api.db import get_session
from stock_manager.api.equipment import catalog_order
from stock_manager.api.equipment_services import EQUIPMENT_CONFIGURED_KEY
from stock_manager.api.models import HouseholdEquipment
from stock_manager.api.services import get_settings, update_settings

router = APIRouter()


def _settings_response(db: Session, values: dict[str, str]) -> schemas.SettingResponse:
    return schemas.SettingResponse(
        **{key: value for key, value in values.items() if key != EQUIPMENT_CONFIGURED_KEY},
        kitchen_equipment=catalog_order(code for code, in db.query(HouseholdEquipment.code)),
        kitchen_equipment_configured=values.get(EQUIPMENT_CONFIGURED_KEY) == "1",
    )


@router.get("", response_model=schemas.SettingResponse)
def read_settings(
    db: Session = Depends(get_session),
):
    """Get current global settings."""
    return _settings_response(db, get_settings(db))


@router.patch("", response_model=schemas.SettingResponse)
def patch_settings(
    payload: schemas.SettingUpdate,
    db: Session = Depends(get_session),
):
    """Update one or more settings."""
    settings_data = payload.model_dump(exclude={"kitchen_equipment"}, exclude_none=True)
    values = update_settings(db, settings_data, kitchen_equipment=payload.kitchen_equipment)
    return _settings_response(db, values)

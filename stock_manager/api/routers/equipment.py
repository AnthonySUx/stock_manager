"""Read the kitchen equipment catalog."""

from fastapi import APIRouter

from stock_manager.api.equipment import EQUIPMENT_CODES

router = APIRouter()


@router.get("")
def list_equipment() -> dict[str, list[str]]:
    return {"codes": list(EQUIPMENT_CODES)}

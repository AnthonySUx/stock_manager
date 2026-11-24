"""Read and write kitchen equipment within the caller's transaction."""

from collections import defaultdict

from sqlalchemy import delete, select, true
from sqlalchemy.orm import Session, aliased

from stock_manager.api.equipment import catalog_order
from stock_manager.api.models import HouseholdEquipment, Recipe, RecipeEquipment, Setting


EQUIPMENT_CONFIGURED_KEY = "kitchen_equipment_configured"


def _equipment_configured():
    return select(Setting.key).where(
        Setting.key == EQUIPMENT_CONFIGURED_KEY, Setting.value == "1",
    ).exists()


def get_household_equipment(db: Session) -> tuple[list[str], bool]:
    """Load both the owned codes and the explicit configuration flag in one query."""
    state = select(_equipment_configured().label("configured")).subquery()
    rows = db.execute(
        select(HouseholdEquipment.code, state.c.configured)
        .select_from(state).outerjoin(HouseholdEquipment, true())
    ).all()
    return catalog_order(code for code, _ in rows if code is not None), bool(rows[0].configured)


def load_recipe_equipment(db: Session, recipe_ids: list[int]) -> dict[int, list[list[str]]]:
    """Load the requirements for a page of recipes."""
    if not recipe_ids:
        return {}
    by_recipe = defaultdict(dict)
    rows = db.execute(
        select(RecipeEquipment.recipe_id, RecipeEquipment.group_index, RecipeEquipment.equipment_code)
        .where(RecipeEquipment.recipe_id.in_(recipe_ids))
        .order_by(RecipeEquipment.group_index)
    )
    for recipe_id, group_index, code in rows:
        by_recipe[recipe_id].setdefault(group_index, []).append(code)
    return {
        recipe_id: [catalog_order(codes) for codes in groups.values()]
        for recipe_id, groups in by_recipe.items()
    }


def missing_equipment(groups: list[list[str]], owned: set[str] | None) -> list[list[str]]:
    if owned is None:
        return []
    return [group for group in groups if owned.isdisjoint(group)]


def meets_equipment_requirements():
    """SQL filter for Recipe queries, bypassed until household settings are saved."""
    option = aliased(RecipeEquipment)
    owned_option = (
        select(option.id)
        .join(HouseholdEquipment, HouseholdEquipment.code == option.equipment_code)
        .where(
            option.recipe_id == RecipeEquipment.recipe_id,
            option.group_index == RecipeEquipment.group_index,
        )
        .correlate(RecipeEquipment)
        .exists()
    )
    missing_group = (
        select(RecipeEquipment.id)
        .where(RecipeEquipment.recipe_id == Recipe.id, ~owned_option)
        .correlate(Recipe)
        .exists()
    )
    return ~_equipment_configured() | ~missing_group


def delete_recipe_equipment(db: Session, recipe_ids: list[int]) -> None:
    db.execute(delete(RecipeEquipment).where(RecipeEquipment.recipe_id.in_(recipe_ids)))


def replace_recipe_equipment(db: Session, recipe_id: int, groups: list[list[str]]) -> None:
    delete_recipe_equipment(db, [recipe_id])
    db.add_all([
        RecipeEquipment(recipe_id=recipe_id, group_index=index, equipment_code=code)
        for index, group in enumerate(groups)
        for code in group
    ])

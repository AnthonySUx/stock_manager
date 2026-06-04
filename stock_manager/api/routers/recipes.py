"""FastAPI router for recipe features."""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from stock_manager.api.db import get_session
from stock_manager.api.recipe_schemas import (
    AIRecipeRecommendationResponse,
    ConsumePreviewResponse,
    CookRecipeRequest,
    CookRecipeResponse,
    RecipeCreate,
    RecipeRecommendation,
    RecipeRecommendationResponse,
    RecipeResponse,
    RecipeSummary,
    RecipeUpdate,
    SourceResponse,
)
from stock_manager.api.recipe_services import (
    add_favorite,
    cook_recipe_and_consume,
    create_recipe,
    delete_recipe,
    fork_recipe,
    get_consume_preview,
    get_recipe,
    get_recipes,
    get_recommendations,
    record_recommendations,
    has_been_cooked,
    is_favorite,
    remove_favorite,
    update_recipe,
)
from stock_manager.api.ai_recipe_service import get_ai_recommendations

router = APIRouter(tags=["Recipes"])


HOWTOCOOK_SOURCE = SourceResponse(
    name="HowToCook",
    url="https://github.com/Anduin2017/HowToCook",
    license="The Unlicense",
    notice=(
        "Some recipe data is imported from Anduin2017/HowToCook "
        "(https://github.com/Anduin2017/HowToCook), which is released "
        "under The Unlicense. See https://unlicense.org/ for details."
    ),
)


def _recipe_to_summary(recipe, db: Session) -> RecipeSummary:
    return RecipeSummary(
        id=recipe.id, source_type=recipe.source_type, source_name=recipe.source_name,
        title=recipe.title, category=recipe.category, difficulty=recipe.difficulty,
        cook_time_minutes=recipe.cook_time_minutes, is_user_created=recipe.is_user_created,
        base_recipe_id=recipe.base_recipe_id, is_favorite=is_favorite(db, recipe.id),
        has_been_cooked=has_been_cooked(db, recipe.id),
        created_at=recipe.created_at,
    )


def _recipe_to_response(recipe, db: Session) -> RecipeResponse:
    return RecipeResponse(
        id=recipe.id, source_type=recipe.source_type, source_name=recipe.source_name,
        source_url=recipe.source_url, source_path=recipe.source_path,
        license_name=recipe.license_name, title=recipe.title, category=recipe.category,
        description=recipe.description, difficulty=recipe.difficulty,
        servings=recipe.servings, cook_time_minutes=recipe.cook_time_minutes,
        raw_markdown=recipe.raw_markdown, is_user_created=recipe.is_user_created,
        base_recipe_id=recipe.base_recipe_id, is_favorite=is_favorite(db, recipe.id),
        has_been_cooked=has_been_cooked(db, recipe.id),
        ingredients=[
            {
                "ingredient_name": ing.ingredient_name,
                "normalized_name": ing.normalized_name,
                "quantity": ing.quantity,
                "unit": ing.unit,
                "is_optional": ing.is_optional,
                "is_seasoning": ing.is_seasoning,
                "sort_order": ing.sort_order,
            }
            for ing in recipe.ingredients
        ] if recipe.ingredients else [],
        steps=[
            {
                "step_number": step.step_number,
                "instruction": step.instruction,
            }
            for step in recipe.steps
        ] if recipe.steps else [],
        created_at=recipe.created_at, updated_at=recipe.updated_at,
    )


@router.get("/sources", response_model=list[SourceResponse])
def list_sources():
    return [HOWTOCOOK_SOURCE]


@router.get("", response_model=list[RecipeSummary])
def list_recipes(
    source_type: Optional[str] = Query(None, pattern="^(howtocook|user|ai_saved)$"),
    category: Optional[str] = None, query: Optional[str] = None,
    favorite_only: bool = False, limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0), db: Session = Depends(get_session),
):
    recipes = get_recipes(db, source_type=source_type, category=category,
        query=query, favorite_only=favorite_only, limit=limit, offset=offset)
    return [_recipe_to_summary(r, db) for r in recipes]


@router.get("/recommendations", response_model=RecipeRecommendationResponse)
def rule_recommendations(limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_session)):
    results = get_recommendations(db, limit=limit)
    record_recommendations(db, [r["recipe_id"] for r in results])
    return RecipeRecommendationResponse(source_notice=HOWTOCOOK_SOURCE.notice,
        recommendations=[RecipeRecommendation(**r) for r in results])


@router.post("/ai/today", response_model=AIRecipeRecommendationResponse)
def ai_today_recommendations(limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_session)):
    rule_results = get_recommendations(db, limit=limit)
    if not rule_results:
        return AIRecipeRecommendationResponse(mode="rule_based_fallback",
            summary="No matching recipes found.", source_notice=HOWTOCOOK_SOURCE.notice,
            recommendations=[])
    try:
        from stock_manager.api.models import Item
        inventory = db.query(Item).filter(Item.status.in_(["active", "expiring soon"])).all()
        inv_names = list(set(i.name.strip() for i in inventory))
        exp_names = list(set(i.name.strip() for i in inventory if i.status == "expiring soon"))
        ai_result = asyncio.run(get_ai_recommendations(
            candidates=[{"recipe_id": r["recipe_id"], "title": r["title"]} for r in rule_results],
            inventory_items=inv_names, expiring_soon_items=exp_names,
            favorite_ids=[r["recipe_id"] for r in rule_results if r.get("is_favorite")],
        ))
        if ai_result is not None:
            return AIRecipeRecommendationResponse(mode="ai",
                summary=ai_result.get("summary"), source_notice=HOWTOCOOK_SOURCE.notice,
                recommendations=[RecipeRecommendation(**r) for r in rule_results])
    except Exception:
        pass
    return AIRecipeRecommendationResponse(mode="rule_based_fallback",
        summary="AI not available.", source_notice=HOWTOCOOK_SOURCE.notice,
        recommendations=[RecipeRecommendation(**r) for r in rule_results])


@router.get("/{recipe_id}/consume-preview", response_model=ConsumePreviewResponse)
def consume_preview_endpoint(
    recipe_id: int,
    db: Session = Depends(get_session),
):
    """Preview which inventory items would be consumed for a recipe."""
    from stock_manager.api.recipe_services import get_consume_preview as _preview
    result = _preview(db, recipe_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return result


@router.post("/{recipe_id}/cook", response_model=CookRecipeResponse)
def cook_recipe_endpoint(
    recipe_id: int,
    data: CookRecipeRequest,
    db: Session = Depends(get_session),
):
    """Mark a recipe as cooked and optionally consume inventory items."""
    from stock_manager.api.recipe_services import cook_recipe_and_consume as _cook
    consume_dicts = [
        {"item_id": ci.item_id, "quantity": ci.quantity, "ingredient_name": ci.ingredient_name}
        for ci in data.consume_items
    ]
    result = _cook(db, recipe_id, consume_dicts, notes=data.notes)
    if result is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return CookRecipeResponse(
        message="Recipe marked as cooked" + (" and inventory consumed" if consume_dicts else ""),
        recipe_id=result["recipe_id"],
        title=result["title"],
        consumed_items=result.get("consumed_items", []),
        notes=result.get("notes"),
    )


@router.get("/{recipe_id}", response_model=RecipeResponse)
def get_recipe_endpoint(recipe_id: int, db: Session = Depends(get_session)):
    recipe = get_recipe(db, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _recipe_to_response(recipe, db)


@router.post("", response_model=RecipeResponse, status_code=201)
def create_recipe_endpoint(data: RecipeCreate, db: Session = Depends(get_session)):
    return _recipe_to_response(create_recipe(db, data, source_type="user"), db)


@router.patch("/{recipe_id}", response_model=RecipeResponse)
def update_recipe_endpoint(recipe_id: int, data: RecipeUpdate, db: Session = Depends(get_session)):
    recipe = update_recipe(db, recipe_id, data)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found or not editable")
    return _recipe_to_response(recipe, db)


@router.delete("/{recipe_id}")
def delete_recipe_endpoint(recipe_id: int, db: Session = Depends(get_session)):
    if not delete_recipe(db, recipe_id):
        raise HTTPException(status_code=404, detail="Recipe not found or not deletable")
    return {"message": "Recipe deleted"}


@router.post("/{recipe_id}/fork", response_model=RecipeResponse)
def fork_recipe_endpoint(recipe_id: int, db: Session = Depends(get_session)):
    recipe = fork_recipe(db, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _recipe_to_response(recipe, db)


@router.post("/{recipe_id}/favorite")
def add_favorite_endpoint(recipe_id: int, db: Session = Depends(get_session)):
    if not add_favorite(db, recipe_id):
        raise HTTPException(status_code=404, detail="Recipe not found")
    return {"message": "Recipe favorited"}


@router.delete("/{recipe_id}/favorite")
def remove_favorite_endpoint(recipe_id: int, db: Session = Depends(get_session)):
    if not remove_favorite(db, recipe_id):
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"message": "Favorite removed"}

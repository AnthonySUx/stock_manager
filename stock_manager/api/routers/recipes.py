"""FastAPI router for recipe features."""
import asyncio
import contextlib
import json
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from stock_manager.api import ai_client

from stock_manager.api.db import get_session
from stock_manager.api.recipe_schemas import (
    AIWarning,
    ConsumePreviewResponse,
    CookRecipeRequest,
    CookRecipeResponse,
    ExploreIdea,
    ExploreRequest,
    ExploreResponse,
    ExpandRequest,
    ExpandResponse,
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
    create_recipe,
    delete_recipe,
    fork_recipe,
    get_recipe,
    get_recipe_flags,
    get_recipes,
    get_recommendations,
    has_been_cooked,
    is_favorite,
    remove_favorite,
    update_recipe,
)

router = APIRouter(tags=["Recipes"])
logger = logging.getLogger(__name__)


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


def _recipe_to_summary(recipe, favorite_ids: set[int], cooked_ids: set[int]) -> RecipeSummary:
    return RecipeSummary(
        id=recipe.id, source_type=recipe.source_type, source_name=recipe.source_name,
        title=recipe.title, category=recipe.category, difficulty=recipe.difficulty,
        cook_time_minutes=recipe.cook_time_minutes, is_user_created=recipe.is_user_created,
        base_recipe_id=recipe.base_recipe_id, is_favorite=recipe.id in favorite_ids,
        has_been_cooked=recipe.id in cooked_ids,
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
    source_type: Optional[str] = Query(None, pattern="^(howtocook|user)$"),
    category: Optional[str] = None, query: Optional[str] = None,
    favorite_only: bool = False, limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0), db: Session = Depends(get_session),
):
    recipes = get_recipes(db, source_type=source_type, category=category,
        query=query, favorite_only=favorite_only, limit=limit, offset=offset)
    # Flags for the whole page in two queries, not two per recipe (#48).
    favorite_ids, cooked_ids = get_recipe_flags(db, [r.id for r in recipes])
    return [_recipe_to_summary(r, favorite_ids, cooked_ids) for r in recipes]


@router.get("/recommendations", response_model=RecipeRecommendationResponse)
def rule_recommendations(
    limit: int = Query(10, ge=1, le=50),
    scene: Literal["all", "breakfast", "meal", "dessert_drink"] = Query(
        "all", description="breakfast | meal (lunch/dinner) | dessert_drink | all"
    ),
    db: Session = Depends(get_session),
):
    """Refresh inventory status and score recipes using recent cooking history."""
    results = get_recommendations(db, limit=limit, scene=scene)
    return RecipeRecommendationResponse(source_notice=HOWTOCOOK_SOURCE.notice,
        recommendations=[RecipeRecommendation(**r) for r in results])


async def _prepare_explore(db: Session, data: ExploreRequest, accept_language: Optional[str]) -> dict:
    """Inventory, locale and prompt inputs for Explore; raises 400 for bad ids."""
    from starlette.concurrency import run_in_threadpool
    from stock_manager.api.localization import resolve_locale

    structured = data.structured.model_dump() if data.structured else None
    selected_ids = (structured or {}).get("inventory_item_ids") or []

    inv_dicts, bad_ids, setting_locale = await run_in_threadpool(
        _load_explore_inventory, db, selected_ids
    )
    recipes = await run_in_threadpool(_load_recipe_titles, db)
    if bad_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Inventory items not found or not usable for recipes: {bad_ids}",
        )
    locale, warnings = resolve_locale(data.locale, accept_language, setting_locale)
    # ExploreRequest guarantees exactly one of structured / natural_language is set.
    return {
        "inventory_items": inv_dicts, "structured": structured,
        "natural_language": data.natural_language, "locale": locale, "warnings": warnings,
        "recipes": recipes,
    }


def _load_recipe_titles(db: Session) -> list[tuple[int, str]]:
    """(id, title) of every local recipe, for linking Explore ideas to
    existing recipes (#66 part 6)."""
    from stock_manager.api.models import Recipe

    return [(row.id, row.title) for row in db.query(Recipe.id, Recipe.title)]


@router.post("/explore", response_model=ExploreResponse)
async def explore_recipes_endpoint(
    data: ExploreRequest,
    db: Session = Depends(get_session),
    accept_language: Optional[str] = Header(None),
):
    """Generate cooking ideas from inventory with structured or free-text input.

    `structured.inventory_item_ids` limits the inventory sent to the AI; unknown
    or ineligible ids return 400. DB work runs in a threadpool so the event
    loop is not blocked while the AI call is awaited.

    Output language: `locale`, else the household `default_locale`, else
    Accept-Language, else zh-CN (#65).

    The same validated ideas as `/explore/stream`, returned together.
    """
    from stock_manager.api.explore_services import explore_ideas

    return await explore_ideas(**await _prepare_explore(db, data, accept_language))


# Seconds between keep-alive comments on /explore/stream.
SSE_HEARTBEAT_SECONDS = 10.0


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _explore_events(events, path: str):
    """Server-sent events for /explore/stream, with a heartbeat while the AI
    is busy. Ideas are re-checked against ExploreIdea before they are sent."""
    queue: asyncio.Queue = asyncio.Queue()

    async def pump() -> None:
        try:
            async for item in events:
                await queue.put(item)
            await queue.put(None)
        except Exception as exc:  # sent as an `error` event below
            await queue.put(exc)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), SSE_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if item is None:
                return
            if isinstance(item, Exception):
                if isinstance(item, ai_client.AIError):
                    ai_client.log_ai_error("POST", path, item)
                    yield _sse("error", {"code": item.code})
                else:
                    logger.error("POST %s failed", path, exc_info=item)
                    yield _sse("error", {"code": "internal_error"})
                return
            kind, value = item
            if kind == "idea":
                value = ExploreIdea.model_validate(value).model_dump(mode="json")
            elif kind == "done":
                value = {**value, "warnings": [AIWarning.model_validate(w).model_dump() for w in value["warnings"]]}
            yield _sse(kind, value)
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await events.aclose()


@router.post(
    "/explore/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}},
                     "description": "Server-sent events: idea*, then done or error"}},
)
async def explore_stream_endpoint(
    request: Request,
    data: ExploreRequest,
    db: Session = Depends(get_session),
    accept_language: Optional[str] = Header(None),
):
    """Explore, streamed: each idea is sent as soon as it has passed validation.

    Events (`text/event-stream`):
    - `idea`: one ExploreIdea, already validated (nothing unvalidated is sent);
    - `done`: `{mode, input_mode, locale, warnings, count}`, last event on success;
    - `error`: `{code}` (`ai_upstream_error`) when no idea could be produced.
    A `: ping` comment is sent every 10 s while the AI is working.

    Problems known before the AI is called keep their status codes: 400 for
    bad inventory ids, 422 for a bad body, 503 when AI is not configured.
    """
    from stock_manager.api.explore_services import explore_stream

    if not ai_client.is_available():
        raise ai_client.AIUnavailableError("AI is not configured")
    arguments = await _prepare_explore(db, data, accept_language)
    return StreamingResponse(
        _explore_events(explore_stream(**arguments), request.url.path),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _load_explore_inventory(
    db: Session, selected_ids: list[int]
) -> tuple[list[dict], list[int], Optional[str]]:
    """Return recipe-eligible, usable inventory (optionally only `selected_ids`),
    the selected ids that are unknown or not eligible, and the household
    `default_locale` setting (None when not set)."""
    from stock_manager.api.category_services import query_recipe_candidate_items
    from stock_manager.api.localization import household_locale
    from stock_manager.api.models import Item

    query = query_recipe_candidate_items(db)
    wanted = list(dict.fromkeys(selected_ids))  # dedupe, keep order
    if wanted:
        query = query.filter(Item.id.in_(wanted))
    items = query.all()

    found = {i.id for i in items}
    bad_ids = [i for i in wanted if i not in found]
    inv_dicts = [
        {"name": i.name, "quantity": i.quantity_value, "unit": i.quantity_unit,
         "status": i.status, "recipe_usage": i.category.recipe_usage}
        for i in items
    ]
    return inv_dicts, bad_ids, household_locale(db)


@router.post("/explore/expand", response_model=ExpandResponse)
async def explore_expand_endpoint(
    data: ExpandRequest,
    db: Session = Depends(get_session),
    accept_language: Optional[str] = Header(None),
):
    """Expand an idea into a recipe draft (not saved).

    The prompt lists recipe-eligible inventory with units, so the draft can
    reuse stock names and units (#65, #66 part 5). Locale as for Explore.
    """
    from starlette.concurrency import run_in_threadpool
    from stock_manager.api.explore_services import expand_to_recipe_draft
    from stock_manager.api.localization import resolve_locale

    inv_dicts, _, setting_locale = await run_in_threadpool(_load_explore_inventory, db, [])
    locale, warnings = resolve_locale(data.locale, accept_language, setting_locale)
    return await expand_to_recipe_draft(
        data.idea.model_dump(), inventory_items=inv_dicts, locale=locale, warnings=warnings
    )


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

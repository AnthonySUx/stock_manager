"""Business logic for recipe features."""
import json
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from stock_manager.api.models import (
    Recipe,
    RecipeFavorite,
    RecipeIngredient,
    RecipeStep,
    RecipeUsageHistory,
    AIRecipeRecommendation,
    Item,
)
from stock_manager.api.recipe_schemas import RecipeCreate, RecipeUpdate


SYNONYM_MAP: dict[str, list[str]] = {}

def load_synonym_map(map_data: dict[str, list[str]]):
    """Load a synonym map for ingredient name normalization."""
    global SYNONYM_MAP
    SYNONYM_MAP = map_data


def _normalize_name(name: str) -> str:
    """Return normalized ingredient name using synonym map."""
    lower = name.strip().lower()
    for canonical, aliases in SYNONYM_MAP.items():
        if lower == canonical.lower():
            return canonical
        for alias in aliases:
            if lower == alias.lower():
                return canonical
    return name.strip()


def _build_normalized_set(names: list[str]) -> set[str]:
    """Build a set of normalized names."""
    return {_normalize_name(n) for n in names}


# ─── CRUD ────────────────────────────────────────────────────────


def get_recipes(
    db: Session,
    *,
    source_type: Optional[str] = None,
    category: Optional[str] = None,
    query: Optional[str] = None,
    favorite_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[Recipe]:
    """Return recipes matching filters."""
    q = db.query(Recipe)

    if source_type:
        q = q.filter(Recipe.source_type == source_type)
    if category:
        q = q.filter(func.lower(Recipe.category) == category.lower())
    if query:
        pattern = f"%{query}%"
        q = q.filter(
            func.lower(Recipe.title).like(pattern.lower())
            | func.lower(func.coalesce(Recipe.description, "")).like(pattern.lower())
        )
    if favorite_only:
        q = q.filter(Recipe.id.in_(
            db.query(RecipeFavorite.recipe_id).subquery()
        ))

    return q.order_by(Recipe.id).offset(offset).limit(limit).all()


def get_recipe(db: Session, recipe_id: int) -> Optional[Recipe]:
    """Return one recipe by id."""
    return db.query(Recipe).filter(Recipe.id == recipe_id).first()


def create_recipe(db: Session, data: RecipeCreate, source_type: str = "user") -> Recipe:
    """Create a new recipe (user-created or AI-saved)."""
    recipe = Recipe(
        source_type=source_type,
        source_name="User" if source_type == "user" else "AI",
        title=data.title,
        category=data.category,
        description=data.description,
        difficulty=data.difficulty,
        servings=data.servings,
        cook_time_minutes=data.cook_time_minutes,
        raw_markdown=data.raw_markdown,
        is_user_created=(source_type == "user"),
    )
    db.add(recipe)
    db.flush()

    for ing in data.ingredients:
        normalized = _normalize_name(ing.ingredient_name)
        db.add(RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_name=ing.ingredient_name,
            normalized_name=normalized or ing.ingredient_name,
            quantity=ing.quantity,
            unit=ing.unit,
            is_optional=ing.is_optional,
            is_seasoning=ing.is_seasoning,
            sort_order=ing.sort_order,
        ))

    for step in data.steps:
        db.add(RecipeStep(
            recipe_id=recipe.id,
            step_number=step.step_number,
            instruction=step.instruction,
        ))

    db.commit()
    db.refresh(recipe)
    return recipe


def update_recipe(db: Session, recipe_id: int, data: RecipeUpdate) -> Optional[Recipe]:
    """Update a user-created or AI-saved recipe."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return None
    if recipe.source_type not in ("user", "ai_saved"):
        return None  # cannot edit HowToCook recipes directly

    update_data = data.model_dump(exclude_unset=True, exclude={"ingredients", "steps"})
    for key, value in update_data.items():
        setattr(recipe, key, value)

    if data.ingredients is not None:
        db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe_id).delete()
        for ing in data.ingredients:
            normalized = _normalize_name(ing.ingredient_name)
            db.add(RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_name=ing.ingredient_name,
                normalized_name=normalized or ing.ingredient_name,
                quantity=ing.quantity,
                unit=ing.unit,
                is_optional=ing.is_optional,
                is_seasoning=ing.is_seasoning,
                sort_order=ing.sort_order,
            ))

    if data.steps is not None:
        db.query(RecipeStep).filter(RecipeStep.recipe_id == recipe_id).delete()
        for step in data.steps:
            db.add(RecipeStep(
                recipe_id=recipe.id,
                step_number=step.step_number,
                instruction=step.instruction,
            ))

    db.commit()
    db.refresh(recipe)
    return recipe


def delete_recipe(db: Session, recipe_id: int) -> bool:
    """Delete a user-created or AI-saved recipe."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return False
    if recipe.source_type not in ("user", "ai_saved"):
        return False
    db.delete(recipe)
    db.commit()
    return True


def fork_recipe(db: Session, recipe_id: int) -> Optional[Recipe]:
    """Fork a recipe into a user-editable copy."""
    original = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if original is None:
        return None
    if original.source_type == "user" and original.is_user_created:
        return original  # already user-owned

    recipe = Recipe(
        source_type="user",
        source_name="User",
        source_url=original.source_url,
        title=original.title,
        category=original.category,
        description=original.description,
        difficulty=original.difficulty,
        servings=original.servings,
        cook_time_minutes=original.cook_time_minutes,
        raw_markdown=original.raw_markdown,
        is_user_created=True,
        base_recipe_id=original.id,
    )
    db.add(recipe)
    db.flush()

    for ing in original.ingredients:
        db.add(RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_name=ing.ingredient_name,
            normalized_name=ing.normalized_name,
            quantity=ing.quantity,
            unit=ing.unit,
            is_optional=ing.is_optional,
            is_seasoning=ing.is_seasoning,
            sort_order=ing.sort_order,
        ))

    for step in original.steps:
        db.add(RecipeStep(
            recipe_id=recipe.id,
            step_number=step.step_number,
            instruction=step.instruction,
        ))

    db.commit()
    db.refresh(recipe)
    return recipe


# ─── Favorites ────────────────────────────────────────────────────


def add_favorite(db: Session, recipe_id: int) -> bool:
    """Add a recipe to favorites."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if recipe is None:
        return False
    existing = db.query(RecipeFavorite).filter(
        RecipeFavorite.recipe_id == recipe_id
    ).first()
    if existing:
        return True  # already favorited
    db.add(RecipeFavorite(recipe_id=recipe_id))
    db.add(RecipeUsageHistory(recipe_id=recipe_id, event_type="favorited"))
    db.commit()
    return True


def remove_favorite(db: Session, recipe_id: int) -> bool:
    """Remove a recipe from favorites."""
    fav = db.query(RecipeFavorite).filter(
        RecipeFavorite.recipe_id == recipe_id
    ).first()
    if fav is None:
        return False
    db.delete(fav)
    db.commit()
    return True


def is_favorite(db: Session, recipe_id: int) -> bool:
    """Check if a recipe is favorited."""
    return db.query(RecipeFavorite).filter(
        RecipeFavorite.recipe_id == recipe_id
    ).first() is not None


# ─── Usage history ──────────────────────────────────────────────


def record_recommendation(db: Session, recipe_id: int):
    """Record that a recipe was recommended."""
    db.add(RecipeUsageHistory(recipe_id=recipe_id, event_type="recommended"))
    db.commit()


# ─── Rule-based recommendations ─────────────────────────────────


def get_recommendations(
    db: Session,
    limit: int = 10,
    include_expired: bool = False,
) -> list[dict]:
    """Generate rule-based recipe recommendations from inventory.

    Scoring:
    - Matched ingredient: +10
    - Expiring ingredient: +40
    - Missing ingredient: -5
    - Favorite recipe: +15
    - Recently recommended: -10 (diversity boost)
    - Not recommended in history: +5 (novelty)
    """
    today = date.today()
    warning_days = 2

    # Gather active inventory
    items = db.query(Item).filter(
        Item.status.in_(["active", "expiring soon"])
    ).all()

    inventory_names = set()
    expiring_names = set()
    for item in items:
        item_lower = item.name.strip().lower()
        inventory_names.add(item_lower)
        if item.status == "expiring soon":
            expiring_names.add(item_lower)

    # Also add normalized names
    inv_norm = _build_normalized_set(list(inventory_names))
    exp_norm = _build_normalized_set(list(expiring_names))

    # Get all recipes with their ingredients
    recipes = db.query(Recipe).all()

    # Get recent recommendations (last 7 days)
    seven_days_ago = today - timedelta(days=7)
    recent_rec_ids = set(
        row[0] for row in db.query(RecipeUsageHistory.recipe_id).filter(
            RecipeUsageHistory.event_type == "recommended",
            RecipeUsageHistory.created_at >= seven_days_ago,
        ).all()
    )

    # Get favorite IDs
    fav_ids = set(
        row[0] for row in db.query(RecipeFavorite.recipe_id).all()
    )

    scored: list[dict] = []

    for recipe in recipes:
        ingredients = db.query(RecipeIngredient).filter(
            RecipeIngredient.recipe_id == recipe.id
        ).all()

        matched = []
        expiring_used = []
        missing = []
        missing_main = []

        for ing in ingredients:
            ing_norm = _normalize_name(ing.ingredient_name).lower()
            ing_raw = ing.ingredient_name.strip().lower()

            if ing_norm in inv_norm or ing_raw in inventory_names:
                matched.append(ing.ingredient_name)
                if ing_norm in exp_norm or ing_raw in expiring_names:
                    expiring_used.append(ing.ingredient_name)
            elif ing.is_seasoning:
                pass  # skip seasoning for missing detection
            elif ing.is_optional:
                pass  # optional ingredients can be omitted
            else:
                missing.append(ing.ingredient_name)

        score = len(matched) * 10 + len(expiring_used) * 40
        score -= len(missing) * 5
        if recipe.id in fav_ids:
            score += 15
        if recipe.id in recent_rec_ids:
            score -= 10
        else:
            score += 5  # novelty bonus

        if score < 0:
            continue

        scored.append({
            "recipe_id": recipe.id,
            "title": recipe.title,
            "score": round(score, 1),
            "matched_inventory_items": matched,
            "expiring_inventory_items": expiring_used,
            "missing_ingredients": missing,
            "is_favorite": recipe.id in fav_ids,
            "is_new_suggestion": recipe.id not in recent_rec_ids,
            "source_type": recipe.source_type,
        })


    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

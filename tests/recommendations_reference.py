"""Unoptimized get_recommendations from the P7 base revision."""

from datetime import timedelta

from sqlalchemy.orm import Session

from stock_manager.api.models import Recipe, RecipeFavorite, RecipeIngredient, RecipeUsageHistory, utcnow
from stock_manager.api.recipe_services import (
    RECENT_COOKED_DAYS,
    RECOMMENDATION_SCENES,
    _build_normalized_set,
    _match_recipe_ingredients,
    _normalize_name,
    is_recommendable,
    recipe_matches_scene,
)


def get_recommendations(
    db: Session,
    limit: int = 10,
    scene: str = "all",
) -> list[dict]:
    """Generate rule-based recipe recommendations from inventory.

    Refresh stored inventory statuses before scoring with the current
    inventory and cooking history.

    Scoring:
    - Matched ingredient: +10 (conditional category: +6)
    - Expiring ingredient: +40 (conditional category: +20)
    - Missing ingredient: -5
    - Favorite recipe: +15
    - Cooked in the last RECENT_COOKED_DAYS days: -10
    - Not cooked in the last RECENT_COOKED_DAYS days: +5
    """
    if scene not in RECOMMENDATION_SCENES:
        raise ValueError(f"Unknown scene '{scene}'")

    # Gather active inventory - only recipe eligible
    from stock_manager.api.category_services import RECIPE_USAGE_ALWAYS, query_recipe_candidate_items
    items = query_recipe_candidate_items(db).all()

    inventory_names = set()
    expiring_names = set()
    always_names = set()
    for item in items:
        item_lower = item.name.strip().lower()
        inventory_names.add(item_lower)
        if item.status == "expiring soon":
            expiring_names.add(item_lower)
        if item.category.recipe_usage == RECIPE_USAGE_ALWAYS:
            always_names.add(item_lower)

    # Also add normalized (synonym-resolved) names, lower-cased for comparison
    inv_norm = {n.lower() for n in _build_normalized_set(list(inventory_names))}
    exp_norm = {n.lower() for n in _build_normalized_set(list(expiring_names))}
    always_norm = {n.lower() for n in _build_normalized_set(list(always_names))}

    def _is_always(ingredient_name: str) -> bool:
        """True if the matched ingredient comes from an always-usage item.

        Checks both the raw name and its synonym-resolved form, so an
        always item named e.g. 西红柿 is not down-weighted when matched to
        a recipe ingredient named 番茄.
        """
        raw = ingredient_name.strip().lower()
        return raw in always_names or _normalize_name(ingredient_name).lower() in always_norm

    # Get all recipes in this scene
    recipes = [r for r in db.query(Recipe).order_by(Recipe.id).all() if is_recommendable(r) and recipe_matches_scene(r, scene)]

    # Recipes actually cooked recently (written by POST /recipes/{id}/cook)
    cooked_since = utcnow() - timedelta(days=RECENT_COOKED_DAYS)
    recent_cooked_ids = set(
        row[0] for row in db.query(RecipeUsageHistory.recipe_id).filter(
            RecipeUsageHistory.event_type == "cooked",
            RecipeUsageHistory.created_at >= cooked_since,
        ).all()
    )

    # Get favorite IDs
    fav_ids = set(
        row[0] for row in db.query(RecipeFavorite.recipe_id).all()
    )

    # All candidate ingredients in one query instead of one per recipe (#48).
    ingredients_by_recipe: dict[int, list[RecipeIngredient]] = {r.id: [] for r in recipes}
    if recipes:
        for ing in (
            db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id.in_(list(ingredients_by_recipe)))
            .order_by(RecipeIngredient.id)
        ):
            ingredients_by_recipe[ing.recipe_id].append(ing)

    scored: list[dict] = []

    for recipe in recipes:
        ingredients = ingredients_by_recipe[recipe.id]

        matched_rows, missing_rows = _match_recipe_ingredients(
            ingredients, inventory_names, inv_norm,
        )
        matched = [ingredient.ingredient_name for ingredient in matched_rows]
        missing = [ingredient.ingredient_name for ingredient in missing_rows]
        expiring_used = [
            name for name in matched
            if name.strip().lower() in expiring_names or _normalize_name(name).lower() in exp_norm
        ]

        score = len(matched) * 10 + len(expiring_used) * 40
        # Reduce score for conditional (non-always) matched items
        for m in matched:
            if not _is_always(m):
                score -= 4  # +10 becomes +6 for conditional
        for e in expiring_used:
            if not _is_always(e):
                score -= 20  # +40 becomes +20 for conditional
        score -= len(missing) * 5
        if recipe.id in fav_ids:
            score += 15
        if recipe.id in recent_cooked_ids:
            score -= 10  # cooked recently: give other dishes a turn
        else:
            score += 5  # not cooked recently

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
            "is_new_suggestion": recipe.id not in recent_cooked_ids,
            "source_type": recipe.source_type,
        })


    # Highest score first; ties keep recipe id order, so results are stable.
    scored.sort(key=lambda x: (-x["score"], x["recipe_id"]))
    return scored[:limit]

"""Candidate selection preserves the original recommendation scores and order (#102)."""

from datetime import date, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.models import Item, Recipe, RecipeFavorite, RecipeIngredient, RecipeUsageHistory
from stock_manager.api.recipe_services import get_recommendations
from tests.helpers import make_item_model_data
from tests.recommendations_reference import get_recommendations as reference_recommendations


def _recipe(db, title, *ingredients, category="soup"):
    recipe = Recipe(title=title, category=category, source_type="user", source_name="User")
    db.add(recipe)
    db.flush()
    for ingredient in ingredients:
        if isinstance(ingredient, str):
            ingredient = {"ingredient_name": ingredient}
        db.add(RecipeIngredient(recipe_id=recipe.id, **ingredient))
    return recipe.id


def _stock(db, name, *, slug="staples_grains", expiring=False):
    category_id = get_category_by_slug(db, slug).id
    expiration = (date.today() + timedelta(days=1)).isoformat() if expiring else "infinite"
    db.add(Item(**make_item_model_data(
        name=name, category_id=category_id, current_expiration_date=expiration,
    )))


@pytest.mark.parametrize(("stock", "favorite", "recent", "scene"), [
    ("empty", False, False, "all"),
    ("pantry", False, False, "all"),
    ("pantry", True, True, "all"),
    ("empty", True, True, "all"),
    ("mixed", True, True, "meal"),
    ("mixed", False, True, "dessert_drink"),
])
def test_recommendations_match_the_reference_scores_and_order(
    db_session, stock, favorite, recent, scene,
):
    db = db_session
    zero = _recipe(db, "No ingredients")
    optional_only = _recipe(
        db, "Garnishes", {"ingredient_name": "Parsley", "is_optional": True},
        {"ingredient_name": "Salt", "is_seasoning": True},
    )
    _recipe(db, "One requirement", "Carrot", {"ingredient_name": "Parsley", "is_optional": True})
    two_missing = _recipe(db, "Two missing", "Carrot", "Pepper")
    pantry_match = _recipe(
        db, "Rice bowl",
        {"ingredient_name": "  白米  ", "normalized_name": None}, "Carrot", "Pepper",
    )
    seasoning_match = _recipe(
        db, "Seasoning match", {"ingredient_name": "食盐", "is_seasoning": True}, "Carrot", "Pepper",
    )
    optional_match = _recipe(
        db, "Optional match", {"ingredient_name": "米", "is_optional": True}, "Carrot", "Pepper",
    )
    _recipe(db, "Dessert", "Crème", "Carrot", "Pepper", category="dessert")
    favorite_id = _recipe(db, "Favorite", "Carrot", "Pepper", "Spinach", "Chicken")
    recent_id = _recipe(db, "Recent", "Tomato")

    if stock != "empty":
        _stock(db, "Rice")
        _stock(db, "Salt", slug="seasonings_spices")
    if stock == "mixed":
        _stock(db, "番茄", slug="vegetables", expiring=True)
        _stock(db, "CRÈME", slug="snacks")
    if favorite:
        db.add(RecipeFavorite(recipe_id=favorite_id))
    if recent:
        db.add(RecipeUsageHistory(recipe_id=recent_id, event_type="cooked"))
    db.commit()

    for limit in (1, 3, 50):
        expected = reference_recommendations(db, limit=limit, scene=scene)
        actual = get_recommendations(db, limit=limit, scene=scene)
        assert actual == expected

    by_id = {row["recipe_id"]: row for row in actual}
    assert two_missing not in by_id
    if stock == "empty" and scene == "all":
        assert by_id[zero]["score"] == 5
        assert by_id[optional_only]["score"] == 5
    if stock != "empty" and scene == "all":
        for recipe_id in (pantry_match, seasoning_match, optional_match):
            assert by_id[recipe_id]["score"] == 5
    if favorite and scene in ("all", "meal"):
        assert by_id[favorite_id]["score"] == 0

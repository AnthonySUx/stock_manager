"""Behavior tests for issue #34: recipe features use only recipe-eligible inventory.

Each path gets three active inventory items whose names all match recipe
ingredients, so an empty result can never pass by accident:

- 番茄 (vegetables, recipe_usage=always)       -> kept, full weight
- 啤酒 (drinks, recipe_usage=conditional)      -> kept, reduced weight
- 牛肉 (pet, recipe_usage=never)               -> excluded everywhere
"""

from datetime import date, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from tests.helpers import make_item_create_payload

ALWAYS_NAME = "番茄"
CONDITIONAL_NAME = "啤酒"
NEVER_NAME = "牛肉"


def _cat_id(db_session, slug):
    cat = get_category_by_slug(db_session, slug)
    assert cat is not None, f"seed category '{slug}' missing"
    return cat.id


def _create_item(client, db_session, name, slug, quantity=5):
    """Create an active item far from expiry and assert the API accepted it."""
    far_future = (date.today() + timedelta(days=60)).isoformat()
    payload = make_item_create_payload(
        name=name,
        category_id=_cat_id(db_session, slug),
        quantity_value=quantity,
        quantity_unit="个",
        unopened_expiration_date=far_future,
        current_expiration_date=far_future,
    )
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["status"] == "active"
    return item


def _create_recipe(client, title, ingredient_names):
    payload = {
        "title": title,
        "ingredients": [
            {"ingredient_name": n, "quantity": "1", "unit": "个"} for n in ingredient_names
        ],
        "steps": [{"step_number": 1, "instruction": "cook"}],
    }
    response = client.post("/api/recipes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def inventory(client, db_session):
    """Seed one always / conditional / never item; return them keyed by usage."""
    return {
        "always": _create_item(client, db_session, ALWAYS_NAME, "vegetables"),
        "conditional": _create_item(client, db_session, CONDITIONAL_NAME, "drinks"),
        "never": _create_item(client, db_session, NEVER_NAME, "pet"),
    }


@pytest.fixture()
def mixed_recipe(client, inventory):
    """A recipe that needs all three inventory names."""
    return _create_recipe(client, "混合菜", [ALWAYS_NAME, CONDITIONAL_NAME, NEVER_NAME])


class TestRuleRecommendations:
    def test_never_item_excluded_eligible_items_kept(self, client, mixed_recipe):
        response = client.get("/api/recipes/recommendations")
        assert response.status_code == 200
        rec = next(
            r for r in response.json()["recommendations"]
            if r["recipe_id"] == mixed_recipe["id"]
        )
        assert ALWAYS_NAME in rec["matched_inventory_items"]
        assert CONDITIONAL_NAME in rec["matched_inventory_items"]
        assert NEVER_NAME not in rec["matched_inventory_items"]
        # The never item is treated as if the user does not have it.
        assert NEVER_NAME in rec["missing_ingredients"]

    def test_conditional_match_scores_lower_than_always(self, client, inventory):
        always_recipe = _create_recipe(client, "只用番茄", [ALWAYS_NAME])
        conditional_recipe = _create_recipe(client, "只用啤酒", [CONDITIONAL_NAME])

        response = client.get("/api/recipes/recommendations")
        assert response.status_code == 200
        scores = {r["recipe_id"]: r["score"] for r in response.json()["recommendations"]}

        assert always_recipe["id"] in scores
        assert conditional_recipe["id"] in scores
        assert scores[conditional_recipe["id"]] < scores[always_recipe["id"]]


class TestAITodayRecommendations:
    def test_ai_receives_only_eligible_inventory(self, client, mixed_recipe, monkeypatch):
        captured = {}

        async def fake_get_ai_recommendations(**kwargs):
            captured.update(kwargs)
            return None  # force rule-based fallback; no external call

        monkeypatch.setattr(
            "stock_manager.api.routers.recipes.get_ai_recommendations",
            fake_get_ai_recommendations,
        )

        response = client.post("/api/recipes/ai/today")
        assert response.status_code == 200
        assert response.json()["mode"] == "rule_based_fallback"

        assert "inventory_items" in captured, "AI path was not reached"
        sent = set(captured["inventory_items"])
        assert ALWAYS_NAME in sent
        assert CONDITIONAL_NAME in sent
        assert NEVER_NAME not in sent


class TestExplore:
    def test_explore_prompt_contains_only_eligible_inventory(self, client, inventory, monkeypatch):
        captured = {}

        async def fake_call_ai(prompt, system_prompt):
            captured["prompt"] = prompt
            return None  # AI unavailable; no external call

        monkeypatch.setattr("stock_manager.api.explore_services._call_ai", fake_call_ai)

        response = client.post(
            "/api/recipes/explore",
            json={"mode": "natural_language", "natural_language": "今晚吃什么"},
        )
        assert response.status_code == 200

        prompt = captured["prompt"]
        assert ALWAYS_NAME in prompt
        assert CONDITIONAL_NAME in prompt
        assert NEVER_NAME not in prompt


class TestConsumePreview:
    def test_preview_never_suggests_never_item(self, client, inventory, mixed_recipe):
        response = client.get(f"/api/recipes/{mixed_recipe['id']}/consume-preview")
        assert response.status_code == 200
        data = response.json()

        suggested_ids = {s["item_id"] for s in data["suggestions"]}
        assert inventory["always"]["id"] in suggested_ids
        assert inventory["conditional"]["id"] in suggested_ids
        assert inventory["never"]["id"] not in suggested_ids
        assert NEVER_NAME in data["unmatched_ingredients"]


class TestCookConsume:
    def test_cook_does_not_deduct_never_item(self, client, inventory, mixed_recipe):
        never_item = inventory["never"]
        always_item = inventory["always"]

        response = client.post(
            f"/api/recipes/{mixed_recipe['id']}/cook",
            json={"consume_items": [
                {"item_id": never_item["id"], "quantity": 1, "ingredient_name": NEVER_NAME},
                {"item_id": always_item["id"], "quantity": 1, "ingredient_name": ALWAYS_NAME},
            ]},
        )
        assert response.status_code == 200
        consumed_ids = {c["item_id"] for c in response.json()["consumed_items"]}
        assert never_item["id"] not in consumed_ids
        assert always_item["id"] in consumed_ids

        never_after = client.get(f"/api/items/{never_item['id']}").json()
        always_after = client.get(f"/api/items/{always_item['id']}").json()
        assert never_after["quantity_value"] == never_item["quantity_value"]
        assert always_after["quantity_value"] == always_item["quantity_value"] - 1

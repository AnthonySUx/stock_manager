"""Today recommendations (PR #14 local scoring) and the deprecated /ai/today endpoint.

Covers:
- synonym matching from DEFAULT_SYNONYM_MAP (inventory 西红柿 matches recipe 番茄)
- an always item matched through a synonym is not down-weighted as conditional
- GET /recommendations is read-only; only recipes cooked in the last 7 days are
  down-weighted (#46)
- scene filter: breakfast / meal / dessert_drink / all, mapped from HowToCook
  `dishes/<dir>` (#46)
- POST /ai/today reaches the AI layer and returns mode="ai" (regression: KeyError
  in the prompt builder used to force a silent fallback every time)
- POST /ai/today is marked deprecated in OpenAPI
"""

import json
from datetime import date, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from tests.helpers import make_item_create_payload


def _create_item(client, db_session, name, slug):
    far_future = (date.today() + timedelta(days=60)).isoformat()
    payload = make_item_create_payload(
        name=name,
        category_id=get_category_by_slug(db_session, slug).id,
        quantity_value=3,
        quantity_unit="个",
        unopened_expiration_date=far_future,
        current_expiration_date=far_future,
    )
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_recipe(client, title, ingredient_names):
    response = client.post("/api/recipes", json={
        "title": title,
        "category": "meat_dish",
        "ingredients": [{"ingredient_name": n} for n in ingredient_names],
        "steps": [{"step_number": 1, "instruction": "cook"}],
    })
    assert response.status_code == 201, response.text
    return response.json()


def _recs_by_id(response):
    assert response.status_code == 200, response.text
    return {r["recipe_id"]: r for r in response.json()["recommendations"]}


class TestSynonymMatching:
    def test_inventory_synonym_matches_recipe_ingredient(self, client, db_session):
        _create_item(client, db_session, "西红柿", "vegetables")
        recipe = _create_recipe(client, "番茄汤", ["番茄"])

        recs = _recs_by_id(client.get("/api/recipes/recommendations"))
        assert recipe["id"] in recs
        assert recs[recipe["id"]]["matched_inventory_items"] == ["番茄"]
        assert recs[recipe["id"]]["missing_ingredients"] == []

    def test_always_item_matched_via_synonym_keeps_full_weight(self, client, db_session):
        _create_item(client, db_session, "西红柿", "vegetables")  # always
        via_synonym = _create_recipe(client, "番茄汤", ["番茄"])
        exact_name = _create_recipe(client, "西红柿汤", ["西红柿"])

        recs = _recs_by_id(client.get("/api/recipes/recommendations"))
        assert recs[via_synonym["id"]]["score"] == recs[exact_name["id"]]["score"]


class TestRecommendationHistory:
    def test_repeated_get_is_stable_and_writes_nothing(self, client, db_session):
        from stock_manager.api.models import RecipeUsageHistory

        _create_item(client, db_session, "鸡蛋", "eggs")
        _create_recipe(client, "炒鸡蛋", ["鸡蛋"])
        _create_recipe(client, "鸡蛋饼", ["鸡蛋", "面粉"])  # has a missing ingredient

        responses = [client.get("/api/recipes/recommendations").json() for _ in range(3)]

        assert responses[0] == responses[1] == responses[2]
        assert len(responses[0]["recommendations"]) == 2
        assert db_session.query(RecipeUsageHistory).count() == 0

    def test_recently_cooked_recipe_is_down_weighted(self, client, db_session):
        _create_item(client, db_session, "鸡蛋", "eggs")
        recipe = _create_recipe(client, "炒鸡蛋", ["鸡蛋"])

        before = _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]]
        assert client.post(f"/api/recipes/{recipe['id']}/cook", json={}).status_code == 200
        after = _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]]

        assert before["is_new_suggestion"] is True
        assert after["is_new_suggestion"] is False
        # +5 (not cooked recently) is lost and -10 (cooked recently) applies
        assert after["score"] == before["score"] - 15

    def test_cooking_older_than_window_has_no_penalty(self, client, db_session):
        from stock_manager.api.models import RecipeUsageHistory, utcnow
        from stock_manager.api.recipe_services import RECENT_COOKED_DAYS

        _create_item(client, db_session, "鸡蛋", "eggs")
        recipe = _create_recipe(client, "炒鸡蛋", ["鸡蛋"])
        before = _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]]

        db_session.add(RecipeUsageHistory(
            recipe_id=recipe["id"], event_type="cooked",
            created_at=utcnow() - timedelta(days=RECENT_COOKED_DAYS + 1),
        ))
        db_session.commit()

        after = _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]]
        assert after == before

    def test_recommended_events_no_longer_affect_score(self, client, db_session):
        """Old 'recommended' rows (written before #46) are ignored."""
        from stock_manager.api.models import RecipeUsageHistory

        _create_item(client, db_session, "鸡蛋", "eggs")
        recipe = _create_recipe(client, "炒鸡蛋", ["鸡蛋"])
        before = _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]]

        db_session.add(RecipeUsageHistory(recipe_id=recipe["id"], event_type="recommended"))
        db_session.commit()

        assert _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]] == before

    def test_equal_scores_are_ordered_by_recipe_id(self, client, db_session):
        _create_item(client, db_session, "鸡蛋", "eggs")
        ids = [_create_recipe(client, f"鸡蛋菜{i}", ["鸡蛋"])["id"] for i in range(3)]

        recs = client.get("/api/recipes/recommendations").json()["recommendations"]
        assert [r["recipe_id"] for r in recs] == ids


def _add_recipe(db_session, title, *, source_path=None, category=None, source_type="howtocook"):
    """Insert a recipe that uses 鸡蛋, shaped like an imported or user recipe."""
    from stock_manager.api.models import Recipe, RecipeIngredient

    recipe = Recipe(title=title, source_type=source_type, source_path=source_path,
                    category=category, is_user_created=source_type == "user")
    db_session.add(recipe)
    db_session.flush()
    db_session.add(RecipeIngredient(recipe_id=recipe.id, ingredient_name="鸡蛋"))
    db_session.commit()
    return recipe.id


class TestScene:
    @pytest.fixture()
    def recipes(self, client, db_session):
        _create_item(client, db_session, "鸡蛋", "eggs")
        return {
            "breakfast": _add_recipe(db_session, "茶叶蛋", source_path="dishes/breakfast/茶叶蛋.md"),
            # nested one level deeper, like most HowToCook meat dishes
            "meat_nested": _add_recipe(
                db_session, "口水鸡", source_path="dishes/meat_dish/口水鸡/口水鸡.md",
                category="口水鸡",  # what the old importer stored
            ),
            "soup": _add_recipe(db_session, "蛋花汤", source_path="dishes/soup/蛋花汤.md"),
            "dessert": _add_recipe(db_session, "焦糖布丁", source_path="dishes/dessert/焦糖布丁/焦糖布丁.md"),
            "drink": _add_recipe(db_session, "蛋酒", source_path="dishes/drink/蛋酒.md"),
            "condiment": _add_recipe(db_session, "蛋黄酱", source_path="dishes/condiment/蛋黄酱.md"),
            "user_plain": _add_recipe(db_session, "我的炒蛋", source_type="user"),
            "user_dessert": _add_recipe(db_session, "我的蛋挞", source_type="user", category="甜品"),
            "user_breakfast": _add_recipe(db_session, "我的早餐", source_type="user", category="早餐"),
        }

    def _scene_ids(self, client, scene):
        params = {"limit": 50} if scene is None else {"limit": 50, "scene": scene}
        response = client.get("/api/recipes/recommendations", params=params)
        assert response.status_code == 200, response.text
        return {r["recipe_id"] for r in response.json()["recommendations"]}

    def test_breakfast(self, client, recipes):
        assert self._scene_ids(client, "breakfast") == {
            recipes["breakfast"], recipes["user_breakfast"]}

    def test_meal_includes_nested_and_uncategorized_user_recipes(self, client, recipes):
        assert self._scene_ids(client, "meal") == {
            recipes["meat_nested"], recipes["soup"], recipes["user_plain"]}

    def test_dessert_drink(self, client, recipes):
        assert self._scene_ids(client, "dessert_drink") == {
            recipes["dessert"], recipes["drink"], recipes["user_dessert"]}

    def test_all_includes_everything(self, client, recipes):
        assert self._scene_ids(client, "all") == set(recipes.values())

    def test_default_scene_is_all(self, client, recipes):
        assert self._scene_ids(client, None) == set(recipes.values())

    def test_non_dish_howtocook_rows_are_never_recommended(self, client, db_session, recipes):
        """tips/, .github/ and the template, imported by older importers."""
        old = [
            _add_recipe(db_session, "学习炒菜", source_path="tips/learn/学习炒菜.md", category="learn"),
            _add_recipe(db_session, "PR 模板", source_path=".github/pull_request_template.md"),
            _add_recipe(db_session, "示例菜", source_path="dishes/template/示例菜/示例菜.md"),
        ]
        for scene in ("all", "meal", "breakfast", "dessert_drink"):
            assert not set(old) & self._scene_ids(client, scene)

    def test_unknown_scene_is_422(self, client):
        response = client.get("/api/recipes/recommendations", params={"scene": "lunch"})
        assert response.status_code == 422


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestDeprecatedAIToday:
    def test_ai_path_reaches_ai_and_returns_ai_mode(self, client, db_session, monkeypatch):
        _create_item(client, db_session, "鸡蛋", "eggs")
        recipe = _create_recipe(client, "炒鸡蛋", ["鸡蛋"])

        import stock_manager.api.ai_recipe_service as ai_service

        monkeypatch.setattr(ai_service, "load_ai_config", lambda: {
            "enabled": True,
            "base_url": "http://ai.invalid",
            "api_key": "test-key",
            "model": "test-model",
            "timeout": 1,
            "temperature": 0.0,
        })

        captured = {}
        ai_content = json.dumps({
            "summary": "今天做炒鸡蛋",
            "recommendations": [{"recipe_id": recipe["id"], "reason": "用掉鸡蛋"}],
        })

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, headers=None, json=None):
                captured["user_prompt"] = json["messages"][1]["content"]
                return _FakeResponse({"choices": [{"message": {"content": ai_content}}]})

        monkeypatch.setattr(ai_service.httpx, "AsyncClient", FakeAsyncClient)

        response = client.post("/api/recipes/ai/today")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["mode"] == "ai"
        assert data["summary"] == "今天做炒鸡蛋"
        assert [r["recipe_id"] for r in data["recommendations"]] == [recipe["id"]]
        assert f"recipe_id={recipe['id']}" in captured["user_prompt"]

    def test_ai_today_marked_deprecated(self, client):
        spec = client.get("/openapi.json").json()
        assert spec["paths"]["/api/recipes/ai/today"]["post"].get("deprecated") is True
        assert not spec["paths"]["/api/recipes/recommendations"]["get"].get("deprecated", False)


class TestRecipeCategoryRequired:
    def test_create_without_category_is_422(self, client):
        response = client.post("/api/recipes", json={"title": "无分类"})
        assert response.status_code == 422

    def test_create_with_unknown_category_is_422(self, client):
        response = client.post("/api/recipes", json={"title": "x", "category": "lunch"})
        assert response.status_code == 422

    def test_created_recipe_lands_in_its_scene(self, client, db_session):
        _create_item(client, db_session, "鸡蛋", "eggs")
        response = client.post("/api/recipes", json={
            "title": "我的蛋挞", "category": "dessert",
            "ingredients": [{"ingredient_name": "鸡蛋"}],
        })
        assert response.status_code == 201
        recipe_id = response.json()["id"]

        def ids(scene):
            r = client.get("/api/recipes/recommendations", params={"scene": scene})
            return {x["recipe_id"] for x in r.json()["recommendations"]}

        assert recipe_id in ids("dessert_drink")
        assert recipe_id not in ids("meal")

    def test_update_category_null_is_422(self, client):
        recipe = _create_recipe(client, "炒鸡蛋", ["鸡蛋"])
        response = client.patch(f"/api/recipes/{recipe['id']}", json={"category": None})
        assert response.status_code == 422

    def test_update_category_change(self, client):
        recipe = _create_recipe(client, "炒鸡蛋", ["鸡蛋"])
        response = client.patch(f"/api/recipes/{recipe['id']}", json={"category": "breakfast"})
        assert response.status_code == 200
        assert response.json()["category"] == "breakfast"

    def test_fork_of_nested_howtocook_recipe_keeps_dish_category(self, client, db_session):
        recipe_id = _add_recipe(
            db_session, "口水鸡", source_path="dishes/meat_dish/口水鸡/口水鸡.md", category="口水鸡",
        )
        fork = client.post(f"/api/recipes/{recipe_id}/fork")
        assert fork.status_code == 200
        assert fork.json()["category"] == "meat_dish"

    def test_expand_draft_keeps_valid_category_only(self, client, monkeypatch):
        replies = iter([
            json.dumps({"title": "蛋挞", "category": "dessert"}),
            json.dumps({"title": "蛋挞", "category": "甜品"}),
        ])

        async def fake_call_ai(prompt, system_prompt):
            assert "Set category to exactly one of" in system_prompt
            return next(replies)

        monkeypatch.setattr("stock_manager.api.explore_services._call_ai", fake_call_ai)
        idea = {"idea": {"title": "蛋挞"}}
        first = client.post("/api/recipes/explore/expand", json=idea).json()["recipe_draft"]
        second = client.post("/api/recipes/explore/expand", json=idea).json()["recipe_draft"]
        assert first["category"] == "dessert"
        assert second["category"] is None

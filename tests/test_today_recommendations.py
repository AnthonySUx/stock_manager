"""Today recommendations (PR #14 local scoring) and the deprecated /ai/today endpoint.

Covers:
- synonym matching from DEFAULT_SYNONYM_MAP (inventory 西红柿 matches recipe 番茄)
- an always item matched through a synonym is not down-weighted as conditional
- GET /recommendations records history, so the next call applies the diversity penalty
- POST /ai/today reaches the AI layer and returns mode="ai" (regression: KeyError
  in the prompt builder used to force a silent fallback every time)
- POST /ai/today is marked deprecated in OpenAPI
"""

import json
from datetime import date, timedelta

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
    def test_second_call_applies_recent_penalty(self, client, db_session):
        _create_item(client, db_session, "鸡蛋", "eggs")
        recipe = _create_recipe(client, "炒鸡蛋", ["鸡蛋"])

        first = _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]]
        second = _recs_by_id(client.get("/api/recipes/recommendations"))[recipe["id"]]

        assert first["is_new_suggestion"] is True
        assert second["is_new_suggestion"] is False
        # novelty +5 is lost and recent-recommendation -10 is applied
        assert second["score"] == first["score"] - 15


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

        monkeypatch.setattr(ai_service, "_load_config", lambda: {
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

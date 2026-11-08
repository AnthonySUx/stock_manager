"""Issue #45: Explore robustness and request fields. The AI is always mocked."""

import json
from datetime import date, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from tests.helpers import make_item_create_payload

IDEA = {"title": "番茄炒蛋", "matched_ingredients": ["番茄"]}


def _create_item(client, db_session, name, slug, **overrides):
    future = (date.today() + timedelta(days=60)).isoformat()
    payload = make_item_create_payload(
        name=name,
        category_id=get_category_by_slug(db_session, slug).id,
        unopened_expiration_date=future,
        current_expiration_date=future,
        **overrides,
    )
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def fake_ai(monkeypatch):
    """Replace the AI call; `fake_ai.reply` is what the AI 'returns'."""
    class Fake:
        reply = None
        prompts: list = []

    async def _call(prompt, system_prompt):
        Fake.prompts.append(prompt)
        return Fake.reply

    Fake.prompts = []
    monkeypatch.setattr("stock_manager.api.explore_services._call_ai", _call)
    return Fake


def _explore_nl(client, text="今晚吃什么"):
    return client.post(
        "/api/recipes/explore", json={"mode": "natural_language", "natural_language": text}
    )


# ─── 1. AI response shapes ────────────────────────────────────────


class TestResponseShapes:
    def test_object_with_ideas(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [IDEA]})
        data = _explore_nl(client).json()
        assert [i["title"] for i in data["ideas"]] == ["番茄炒蛋"]
        assert data["warnings"] == []

    def test_bare_list(self, client, fake_ai):
        fake_ai.reply = json.dumps([IDEA])
        response = _explore_nl(client)
        assert response.status_code == 200
        assert [i["title"] for i in response.json()["ideas"]] == ["番茄炒蛋"]

    def test_bare_list_in_code_fence(self, client, fake_ai):
        fake_ai.reply = "Here you go:\n```json\n" + json.dumps([IDEA]) + "\n```"
        assert [i["title"] for i in _explore_nl(client).json()["ideas"]] == ["番茄炒蛋"]

    @pytest.mark.parametrize("reply", ['"just a string"', "42", "null", "not json at all", "{}", "[]"])
    def test_unusable_reply_is_warning_not_500(self, client, fake_ai, reply):
        fake_ai.reply = reply
        response = _explore_nl(client)
        assert response.status_code == 200
        assert response.json()["ideas"] == []
        assert response.json()["warnings"] == ["Failed to parse AI response."]

    def test_malformed_idea_is_skipped(self, client, fake_ai):
        bad = {"title": "坏数据", "matched_ingredients": "番茄"}  # should be a list
        fake_ai.reply = json.dumps({"ideas": [bad, IDEA]})
        response = _explore_nl(client)
        assert response.status_code == 200
        assert [i["title"] for i in response.json()["ideas"]] == ["番茄炒蛋"]

    def test_expand_with_list_reply_is_not_500(self, client, fake_ai):
        fake_ai.reply = json.dumps([{"title": "x"}])
        response = client.post("/api/recipes/explore/expand", json={"idea": IDEA})
        assert response.status_code == 200
        assert response.json()["recipe_draft"]["title"] == "番茄炒蛋"


# ─── 2. Event loop not blocked ────────────────────────────────────


def test_explore_db_work_runs_off_the_event_loop(client, fake_ai, monkeypatch):
    """The async endpoint must run its DB query in a worker thread."""
    import threading

    import starlette.concurrency
    from stock_manager.api.routers import recipes

    loop_thread = {}
    query_thread = {}
    real_run = starlette.concurrency.run_in_threadpool
    real_load = recipes._load_explore_inventory

    async def spy_run(func, *args, **kwargs):
        loop_thread["id"] = threading.get_ident()
        return await real_run(func, *args, **kwargs)

    def spy_load(*args, **kwargs):
        query_thread["id"] = threading.get_ident()
        return real_load(*args, **kwargs)

    monkeypatch.setattr(starlette.concurrency, "run_in_threadpool", spy_run)
    monkeypatch.setattr(recipes, "_load_explore_inventory", spy_load)

    assert _explore_nl(client).status_code == 200
    assert "id" in query_thread, "inventory was not loaded via _load_explore_inventory"
    assert query_thread["id"] != loop_thread["id"]


# ─── 3. inventory_item_ids ────────────────────────────────────────


class TestInventoryItemIds:
    def test_only_selected_items_are_sent(self, client, db_session, fake_ai):
        tomato = _create_item(client, db_session, "番茄", "vegetables")
        _create_item(client, db_session, "土豆", "vegetables")

        response = client.post(
            "/api/recipes/explore",
            json={"mode": "structured", "structured": {"inventory_item_ids": [tomato["id"]]}},
        )

        assert response.status_code == 200
        assert response.json()["input_mode"] == "structured"
        prompt = fake_ai.prompts[-1]
        assert "番茄" in prompt
        assert "土豆" not in prompt

    def test_empty_ids_send_all_eligible_items(self, client, db_session, fake_ai):
        _create_item(client, db_session, "番茄", "vegetables")
        _create_item(client, db_session, "土豆", "vegetables")

        response = client.post("/api/recipes/explore", json={"mode": "structured", "structured": {}})

        assert response.status_code == 200
        assert "番茄" in fake_ai.prompts[-1] and "土豆" in fake_ai.prompts[-1]

    def test_unknown_id_is_400(self, client, db_session, fake_ai):
        tomato = _create_item(client, db_session, "番茄", "vegetables")
        response = client.post(
            "/api/recipes/explore",
            json={"mode": "structured", "structured": {"inventory_item_ids": [tomato["id"], 99999]}},
        )
        assert response.status_code == 400
        assert "99999" in response.json()["detail"]
        assert fake_ai.prompts == []

    def test_ineligible_category_id_is_400(self, client, db_session, fake_ai):
        pet = _create_item(client, db_session, "狗粮", "pet_food")
        response = client.post(
            "/api/recipes/explore",
            json={"mode": "structured", "structured": {"inventory_item_ids": [pet["id"]]}},
        )
        assert response.status_code == 400

    def test_consumed_item_id_is_400(self, client, db_session, fake_ai):
        egg = _create_item(client, db_session, "鸡蛋", "eggs")
        consumed = client.post(f"/api/items/{egg['id']}/consume", json={"quantity": egg["quantity_value"]})
        assert consumed.status_code == 200
        response = client.post(
            "/api/recipes/explore",
            json={"mode": "structured", "structured": {"inventory_item_ids": [egg["id"]]}},
        )
        assert response.status_code == 400


# ─── 4. mode must match payload ───────────────────────────────────


class TestModeValidation:
    @pytest.mark.parametrize(
        "body",
        [
            {"mode": "structured"},
            {"mode": "structured", "structured": None},
            {"mode": "structured", "structured": {}, "natural_language": "来点辣的"},
            {"mode": "natural_language"},
            {"mode": "natural_language", "natural_language": "   "},
            {"mode": "natural_language", "natural_language": "辣", "structured": {}},
            {"mode": "other", "natural_language": "辣"},
        ],
    )
    def test_mismatch_is_422(self, client, fake_ai, body):
        assert client.post("/api/recipes/explore", json=body).status_code == 422
        assert fake_ai.prompts == []

    def test_natural_language_with_null_structured_is_ok(self, client, fake_ai):
        response = client.post(
            "/api/recipes/explore",
            json={"mode": "natural_language", "natural_language": "  来点辣的 ", "structured": None},
        )
        assert response.status_code == 200
        assert response.json()["input_mode"] == "natural_language"
        assert "来点辣的" in fake_ai.prompts[-1]

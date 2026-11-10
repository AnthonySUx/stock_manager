"""Issue #49: settings validation, literal search, UTC timestamps, AI config."""

from datetime import date, datetime, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.models import Setting, utcnow
from stock_manager.api.text_search import escape_like
from tests.helpers import make_item_create_payload

# ─── Settings ─────────────────────────────────────────────────────


class TestSettings:
    def test_response_has_no_default_database(self, client):
        assert client.get("/api/settings").json() == {"expiration_reminder_days": "2"}

    def test_old_default_database_row_is_ignored(self, client, db_session):
        db_session.add(Setting(key="default_database", value="stock.db"))
        db_session.commit()
        assert "default_database" not in client.get("/api/settings").json()

    def test_old_client_sending_default_database_still_works(self, client, db_session):
        response = client.patch(
            "/api/settings", json={"default_database": "x.db", "expiration_reminder_days": "4"}
        )
        assert response.status_code == 200
        assert response.json() == {"expiration_reminder_days": "4"}
        assert db_session.query(Setting).filter_by(key="default_database").count() == 0

    @pytest.mark.parametrize("value,stored", [("5", "5"), (7, "7"), (" 3 ", "3"), ("0", "0"), ("365", "365"), ("007", "7")])
    def test_valid_reminder_days(self, client, value, stored):
        response = client.patch("/api/settings", json={"expiration_reminder_days": value})
        assert response.status_code == 200
        assert response.json()["expiration_reminder_days"] == stored

    @pytest.mark.parametrize("value", ["-1", "abc", "1.5", 1.5, "366", True, "", "２", [3]])
    def test_invalid_reminder_days_is_422_and_unchanged(self, client, value):
        assert client.patch("/api/settings", json={"expiration_reminder_days": "4"}).status_code == 200

        response = client.patch("/api/settings", json={"expiration_reminder_days": value})

        assert response.status_code == 422
        assert "expiration_reminder_days" in response.text
        assert client.get("/api/settings").json()["expiration_reminder_days"] == "4"

    def test_reminder_days_change_item_status(self, client, db_session):
        in_five_days = (date.today() + timedelta(days=5)).isoformat()
        payload = make_item_create_payload(
            category_id=get_category_by_slug(db_session, "dairy").id,
            unopened_expiration_date=in_five_days,
            current_expiration_date=in_five_days,
        )
        item_id = client.post("/api/items", json=payload).json()["id"]
        assert client.get(f"/api/items/{item_id}").json()["status"] == "active"

        client.patch("/api/settings", json={"expiration_reminder_days": 7})

        assert [i["id"] for i in client.get("/api/items/reminders").json()] == [item_id]


# ─── Literal keyword search ───────────────────────────────────────


class TestLiteralSearch:
    @pytest.mark.parametrize("text,expected", [
        ("50%", "50/%"), ("a_b", "a/_b"), ("x/y", "x//y"), ("/%_", "///%/_"), ("番茄", "番茄"),
    ])
    def test_escape_like(self, text, expected):
        assert escape_like(text) == expected

    def _item(self, client, db_session, name):
        payload = make_item_create_payload(
            name=name, category_id=get_category_by_slug(db_session, "dairy").id
        )
        assert client.post("/api/items", json=payload).status_code == 201

    @pytest.mark.parametrize("keyword,expected", [
        ("50%", ["50%牛奶"]),
        ("%", ["50%牛奶"]),
        ("_", ["a_b"]),
        ("a_b", ["a_b"]),
        ("/", ["1/2 奶"]),
        ("50", ["50%牛奶", "500 奶"]),
        ("A_B", ["a_b"]),  # case-insensitive, and _ is not "any character"
    ])
    def test_item_search_matches_literally(self, client, db_session, keyword, expected):
        for name in ["50%牛奶", "500 奶", "a_b", "axb", "1/2 奶"]:
            self._item(client, db_session, name)
        response = client.get("/api/items/search", params={"keyword": keyword})

        assert response.status_code == 200
        assert sorted(i["name"] for i in response.json()) == sorted(expected)

    def test_recipe_search_matches_literally(self, client):
        for title in ["50%糖奶茶", "500 克牛肉", "a_b 饼", "axb 饼"]:
            assert client.post("/api/recipes", json={"title": title, "category": "drink"}).status_code == 201

        def titles(query):
            return sorted(r["title"] for r in client.get("/api/recipes", params={"query": query}).json())

        assert titles("50%") == ["50%糖奶茶"]
        assert titles("a_b") == ["a_b 饼"]
        assert titles("50") == sorted(["500 克牛肉", "50%糖奶茶"])


# ─── UTC timestamps ───────────────────────────────────────────────


class TestUtcTimestamps:
    def test_utcnow_is_naive_utc(self):
        from datetime import timezone

        value = utcnow()
        assert value.tzinfo is None
        aware_now = datetime.now(timezone.utc).replace(tzinfo=None)
        assert abs((aware_now - value).total_seconds()) < 5

    def test_created_and_updated_at_are_utc(self, client, db_session):
        from stock_manager.api.models import Item

        payload = make_item_create_payload(category_id=get_category_by_slug(db_session, "dairy").id)
        item_id = client.post("/api/items", json=payload).json()["id"]
        assert client.patch(f"/api/items/{item_id}", json={"notes": "x"}).status_code == 200

        db_session.expire_all()
        item = db_session.get(Item, item_id)
        for value in (item.created_at, item.updated_at):
            assert abs((utcnow() - value).total_seconds()) < 60

    def test_onupdate_uses_python_utc_clock(self):
        """Not func.now(): on MySQL that is server-local time, not UTC."""
        from stock_manager.api.models import Base

        for table in Base.metadata.tables.values():
            column = table.columns.get("updated_at")
            if column is not None:
                assert column.onupdate.arg.__name__ == "utcnow", table.name


# ─── One AI config reader ─────────────────────────────────────────


class TestSharedAiConfig:
    def test_explore_reads_the_shared_config(self, monkeypatch):
        import asyncio

        import httpx

        import stock_manager.api.ai_recipe_service as ai_service
        from stock_manager.api import explore_services

        # Environment says enabled, but the shared reader decides.
        monkeypatch.setenv("AI_RECIPE_ENABLED", "true")
        monkeypatch.setenv("AI_API_KEY", "env-key")
        monkeypatch.setattr(ai_service, "load_ai_config", lambda: {
            "enabled": False, "base_url": "", "api_key": "k", "model": "m",
            "timeout": 1, "temperature": 0.0,
        })
        assert asyncio.run(explore_services._call_ai("p", "s")) is None

        captured = {}

        class FakeClient:
            def __init__(self, timeout):
                captured["timeout"] = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, headers, json):
                captured.update(url=url, model=json["model"], temperature=json["temperature"])
                return httpx.Response(
                    200, json={"choices": [{"message": {"content": "ok"}}]},
                    request=httpx.Request("POST", url),
                )

        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
        monkeypatch.setattr(ai_service, "load_ai_config", lambda: {
            "enabled": True, "base_url": "http://ai.invalid/", "api_key": "k",
            "model": "shared-model", "timeout": 3, "temperature": 0.7,
        })

        assert asyncio.run(explore_services._call_ai("p", "s")) == "ok"
        assert captured == {
            "timeout": 3, "url": "http://ai.invalid/chat/completions",
            "model": "shared-model", "temperature": 0.7,
        }

    def test_load_ai_config_reads_environment(self, monkeypatch):
        from stock_manager.api.ai_recipe_service import load_ai_config

        monkeypatch.setenv("AI_RECIPE_ENABLED", "TRUE")
        monkeypatch.setenv("AI_MODEL", "m1")
        monkeypatch.setenv("AI_TIMEOUT_SECONDS", "9")
        config = load_ai_config()
        assert (config["enabled"], config["model"], config["timeout"]) == (True, "m1", 9)

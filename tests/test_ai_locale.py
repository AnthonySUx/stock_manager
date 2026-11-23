"""Issue #65: locale, household timezone, and validation of AI output.

The AI is always mocked (`fake_ai` in conftest).
"""

import asyncio
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from stock_manager.api.ai_output import Inventory, clean_quantity, in_locale
from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.localization import normalize_locale, resolve_locale, today
from stock_manager.api.models import Setting
from stock_manager.api.recipe_schemas import RecipeCreate
from tests.helpers import make_item_create_payload, make_restock_create_payload

STEPS = [{"step_number": 1, "instruction": "番茄切块，下锅翻炒"}]


def _create_item(client, db_session, name, slug="vegetables", days=60, **overrides):
    exp = (date.today() + timedelta(days=days)).isoformat()
    payload = make_item_create_payload(
        name=name,
        category_id=get_category_by_slug(db_session, slug).id,
        unopened_expiration_date=exp,
        current_expiration_date=exp,
        **overrides,
    )
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _explore(client, headers=None, **extra):
    body = {"mode": "natural_language", "natural_language": "今晚吃什么", **extra}
    return client.post("/api/recipes/explore", json=body, headers=headers or {})


def _expand(client, idea=None, headers=None, **extra):
    body = {"idea": idea or {"title": "番茄炒蛋"}, **extra}
    return client.post("/api/recipes/explore/expand", json=body, headers=headers or {})


def _codes(response):
    return [w["code"] for w in response.json()["warnings"]]


# ─── Locale resolution ───────────────────────────────────────────


@pytest.mark.parametrize("tag,expected", [
    ("zh-CN", "zh-CN"), ("zh", "zh-CN"), ("zh-Hans", "zh-CN"), ("zh_CN", "zh-CN"),
    ("ZH-hans-cn", "zh-CN"), ("en-US", "en"), ("EN", "en"), ("ja-JP", "ja"),
    ("zh-TW", None), ("zh-Hant", None), ("fr", None), ("", None), (None, None), ("  ", None),
])
def test_normalize_locale(tag, expected):
    assert normalize_locale(tag) == expected


class TestResolveLocale:
    def test_explicit_wins(self):
        assert resolve_locale("en", "ja", "ja") == ("en", [])

    def test_setting_before_header(self):
        # iOS sends Accept-Language on every request; the household setting must still apply.
        assert resolve_locale(None, "en-US,en;q=0.9", "ja") == ("ja", [])

    def test_header_when_no_setting(self):
        assert resolve_locale(None, "fr-FR, ja;q=0.8, en;q=0.9", None) == ("en", [])

    def test_header_q_zero_is_ignored(self):
        assert resolve_locale(None, "en;q=0", None) == ("zh-CN", [])
        assert resolve_locale(None, "en;q=0, ja;q=0.5", None) == ("ja", [])

    def test_default_is_zh_cn(self):
        assert resolve_locale(None, None, None) == ("zh-CN", [])
        assert resolve_locale(None, "fr, de;q=0.5, *", None) == ("zh-CN", [])  # no warning for the device language

    def test_unsupported_explicit_falls_back_with_warning(self):
        locale, warnings = resolve_locale("fr", "ja", None)
        assert locale == "ja"
        assert warnings == [{"code": "locale_fallback", "params": {"requested": "fr"}}]

    def test_blank_explicit_is_ignored(self):
        assert resolve_locale("  ", None, "en") == ("en", [])


# ─── Settings ────────────────────────────────────────────────────


class TestLocaleSettings:
    def test_defaults_are_null(self, client):
        body = client.get("/api/settings").json()
        assert body["default_locale"] is None and body["default_timezone"] is None

    def test_set_normalize_and_clear(self, client, db_session):
        response = client.patch("/api/settings", json={"default_locale": "zh-Hans", "default_timezone": "Asia/Tokyo"})
        assert response.status_code == 200
        assert (response.json()["default_locale"], response.json()["default_timezone"]) == ("zh-CN", "Asia/Tokyo")

        response = client.patch("/api/settings", json={"default_locale": "", "default_timezone": " "})
        assert response.status_code == 200
        assert response.json()["default_locale"] is None and response.json()["default_timezone"] is None
        assert db_session.query(Setting).filter(Setting.key.in_(["default_locale", "default_timezone"])).count() == 0

    def test_clearing_an_unset_value_is_fine(self, client):
        assert client.patch("/api/settings", json={"default_locale": ""}).status_code == 200

    @pytest.mark.parametrize("body", [
        {"default_locale": "fr"}, {"default_locale": "zh-TW"}, {"default_locale": 1},
        {"default_timezone": "Mars/Base"}, {"default_timezone": "../etc/passwd"}, {"default_timezone": 9},
    ])
    def test_invalid_values_are_422(self, client, body):
        assert client.patch("/api/settings", json=body).status_code == 422

    def test_reminder_days_cannot_be_cleared(self, client):
        assert client.patch("/api/settings", json={"expiration_reminder_days": ""}).status_code == 422


# ─── Household "today" ───────────────────────────────────────────


class TestToday:
    def test_without_setting_uses_server_date(self, db_session):
        assert today(db_session) == date.today()

    @pytest.mark.parametrize("tz", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
    def test_uses_household_timezone(self, db_session, tz):
        db_session.add(Setting(key="default_timezone", value=tz))
        db_session.commit()
        assert today(db_session) == datetime.now(ZoneInfo(tz)).date()

    def test_invalid_stored_timezone_falls_back(self, db_session):
        db_session.add(Setting(key="default_timezone", value="Not/AZone"))
        db_session.commit()
        assert today(db_session) == date.today()

    def test_item_purchase_date_defaults_to_household_today(self, client, db_session):
        # UTC+14 and UTC-11 are 25 hours apart, so at least one differs from the server date.
        for tz in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
            client.patch("/api/settings", json={"default_timezone": tz})
            payload = make_item_create_payload(category_id=get_category_by_slug(db_session, "dairy").id)
            del payload["purchase_date"]
            response = client.post("/api/items", json=payload)
            assert response.status_code == 201, response.text
            assert response.json()["purchase_date"] == datetime.now(ZoneInfo(tz)).date().isoformat()

    def test_expiration_status_uses_household_today(self, client, db_session, monkeypatch):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        payload = make_item_create_payload(
            category_id=get_category_by_slug(db_session, "dairy").id,
            unopened_expiration_date=tomorrow, current_expiration_date=tomorrow,
        )
        from stock_manager.api import services

        # Two days ahead of the server date: tomorrow's expiry is already past.
        monkeypatch.setattr(services, "household_today", lambda db: date.today() + timedelta(days=2))
        assert client.post("/api/items", json=payload).json()["status"] == "expired"


    def test_restock_done_purchase_date_defaults_to_household_today(self, client, db_session):
        for tz in ("Pacific/Kiritimati", "Pacific/Pago_Pago"):
            client.patch("/api/settings", json={"default_timezone": tz})
            created = client.post("/api/restock", json=make_restock_create_payload(name=f"牛奶-{tz}")).json()
            response = client.post(f"/api/restock/{created['id']}/done", json={
                "purchased_quantity": 1, "owner": "me", "location": "冰箱",
                "category_id": get_category_by_slug(db_session, "dairy").id,
            })
            assert response.status_code == 200, response.text
            item = next(i for i in client.get("/api/items").json() if i["name"] == f"牛奶-{tz}")
            assert item["purchase_date"] == datetime.now(ZoneInfo(tz)).date().isoformat()

    def test_cooking_status_uses_household_today(self, client, db_session, monkeypatch):
        from stock_manager.api import services

        item = _create_item(client, db_session, "番茄", days=1, quantity_value=5)
        recipe = client.post("/api/recipes", json={
            "title": "番茄汤", "category": "soup",
            "ingredients": [{"ingredient_name": "番茄", "quantity": "1", "unit": "瓶"}],
            "steps": [{"step_number": 1, "instruction": "煮"}],
        }).json()
        monkeypatch.setattr(services, "household_today", lambda db: date.today() + timedelta(days=2))
        response = client.post(f"/api/recipes/{recipe['id']}/cook", json={"consume_items": [
            {"item_id": item["id"], "quantity": 1, "ingredient_name": "番茄"}]})
        assert response.status_code == 200, response.text
        assert client.get(f"/api/items/{item['id']}").json()["status"] == "expired"


def test_ginseng_is_not_a_carrot():
    from stock_manager.api.recipe_services import _normalize_name

    assert _normalize_name("人参") == "人参"
    assert _normalize_name("にんじん") == "胡萝卜"


# ─── Language check ──────────────────────────────────────────────


INV = Inventory([{"name": "Bacon", "unit": "片"}, {"name": "番茄", "unit": "个"}])


@pytest.mark.parametrize("text,locale,ok", [
    ("番茄炒蛋", "zh-CN", True),
    ("番茄炒蛋 (Tomato Egg)", "zh-CN", False),
    ("Tomato egg", "zh-CN", False),
    ("加入 200g 面粉，180°C 烤 20 分钟", "zh-CN", True),
    ("bacon 煎香", "zh-CN", True),          # inventory name, copied verbatim
    ("トマト炒め", "zh-CN", False),          # kana is not Chinese
    ("トマトと卵の炒め物", "ja", True),
    ("Scrambled eggs", "ja", False),
    ("Scrambled eggs with 番茄", "en", True),  # inventory name
    ("Scrambled eggs with 鸡蛋", "en", False),
    ("Tomato egg stir-fry", "en", True),
    ("2", "zh-CN", True),
    ("", "zh-CN", True),
    (None, "en", True),
])
def test_in_locale(text, locale, ok):
    assert in_locale(text, locale, INV) is ok


# ─── Quantities ──────────────────────────────────────────────────


@pytest.mark.parametrize("qty,unit,locale,stock,expected", [
    ("2", "个", "zh-CN", None, ("2", "个", True)),
    (2, None, "zh-CN", None, ("2", None, True)),
    (0.5, "千克", "zh-CN", None, ("0.5", "千克", True)),
    (2.0, "g", "zh-CN", None, ("2", "克", True)),         # alias → the locale's spelling
    ("500克", None, "zh-CN", None, ("500", "克", True)),
    ("500克", "克", "zh-CN", None, ("500", "克", True)),
    ("500克", "个", "zh-CN", None, (None, None, False)),  # text and unit disagree
    ("1", "大勺", "zh-CN", None, ("1", "汤匙", True)),
    ("3", "pcs", "zh-CN", "个", ("3", "个", True)),       # the stock unit
    ("2", "瓶", "zh-CN", "瓶", ("2", "瓶", True)),         # stock unit outside the list
    ("2", "瓶", "zh-CN", None, (None, None, False)),
    ("1", "斤", "zh-CN", None, (None, None, False)),
    ("1/2", "杯", "zh-CN", None, (None, None, False)),
    ("2-3", "个", "zh-CN", None, (None, None, False)),
    ("0", "个", "zh-CN", None, (None, None, False)),
    ("适量", None, "zh-CN", None, ("适量", None, True)),
    ("少许", "克", "zh-CN", None, ("少许", None, True)),
    ("To taste", None, "en", None, ("to taste", None, True)),
    ("适量", None, "en", None, (None, None, False)),
    ("2", "tablespoons", "en", None, ("2", "tbsp", True)),
    ("2", "大さじ", "ja", None, ("2", "大さじ", True)),
    (None, None, "zh-CN", None, (None, None, True)),
    (None, "克", "zh-CN", None, (None, None, False)),
    (True, None, "zh-CN", None, (None, None, True)),
])
def test_clean_quantity(qty, unit, locale, stock, expected):
    assert clean_quantity(qty, unit, locale, stock) == expected


# ─── Explore ─────────────────────────────────────────────────────


class TestExploreLocale:
    def test_default_prompt_and_response_locale(self, client, fake_ai):
        response = _explore(client)
        assert response.status_code == 200
        assert response.json()["locale"] == "zh-CN"
        assert "in Simplified Chinese only" in fake_ai.system_prompts[-1]
        assert response.json()["warnings"] == []

    def test_explicit_locale(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [{"title": "Tomato egg stir-fry"}]})
        response = _explore(client, locale="en-US")
        assert response.json()["locale"] == "en"
        assert "in English only" in fake_ai.system_prompts[-1]

    def test_accept_language_header(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [{"title": "トマト炒め"}]})
        response = _explore(client, headers={"Accept-Language": "ja-JP,en;q=0.5"})
        assert response.json()["locale"] == "ja"

    def test_setting_beats_header(self, client, fake_ai):
        client.patch("/api/settings", json={"default_locale": "zh-CN"})
        response = _explore(client, headers={"Accept-Language": "en-US"})
        assert response.json()["locale"] == "zh-CN"

    def test_unsupported_locale_warns(self, client, fake_ai):
        response = _explore(client, locale="fr")
        assert response.json()["locale"] == "zh-CN"
        assert response.json()["warnings"] == [{"code": "locale_fallback", "params": {"requested": "fr"}}]

    def test_enum_lists_are_in_the_prompt(self, client, fake_ai):
        _explore(client)
        system = fake_ai.system_prompts[-1]
        assert "stir_fry, steam, boil" in system and "chinese, japanese, korean" in system


class TestExploreValidation:
    def test_wrong_language_idea_is_dropped(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [
            {"title": "Tomato Egg"},
            {"title": "番茄炒蛋", "reason": "Quick and easy"},
            {"title": "番茄炒蛋（Tomato Egg）"},
            {"title": "红烧肉", "reason": "下饭"},
        ]})
        response = _explore(client)
        assert [i["title"] for i in response.json()["ideas"]] == ["红烧肉"]
        assert _codes(response) == ["idea_dropped_wrong_language"] * 3

    def test_all_wrong_language_is_502(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [{"title": "Tomato Egg"}]})
        response = _explore(client)
        assert response.status_code == 502
        assert response.json()["code"] == "ai_upstream_error"
        assert {"params", "detail"} <= response.json().keys()

    def test_enums_are_validated(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [{
            "title": "番茄炒蛋", "cooking_method": "Stir-Fry", "cuisine_group": "川菜",
        }]})
        response = _explore(client)
        idea = response.json()["ideas"][0]
        assert idea["cooking_method"] == "stir_fry"
        assert idea["cuisine_group"] is None
        assert response.json()["warnings"] == [
            {"code": "field_value_dropped", "params": {"field": "cuisine_group", "value": "川菜"}}
        ]

    def test_repeated_warnings_are_merged(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [
            {"title": "甲", "cuisine_group": "川菜"}, {"title": "乙", "cuisine_group": "川菜"},
        ]})
        assert _codes(_explore(client)) == ["field_value_dropped"]

    def test_free_text_lists_drop_wrong_language_entries(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [{
            "title": "番茄炒蛋", "flavors": ["酸甜", "sweet", 3], "textures": ["嫩"], "cuisine": "Sichuan",
        }]})
        idea = _explore(client).json()["ideas"][0]
        assert (idea["flavors"], idea["textures"], idea["cuisine"]) == (["酸甜"], ["嫩"], None)

    def test_ingredient_lists_are_recomputed_from_inventory(self, client, db_session, fake_ai):
        _create_item(client, db_session, "番茄", days=1)  # expiring soon
        _create_item(client, db_session, "土豆")
        fake_ai.reply = json.dumps({"ideas": [{
            "title": "番茄牛腩",
            "matched_ingredients": ["西红柿", "牛腩"],      # 牛腩 is not in stock
            "expiring_ingredients": [],
            "missing_ingredients": ["土豆", "八角", "star anise"],  # 土豆 is in stock
        }]})
        response = _explore(client)
        idea = response.json()["ideas"][0]
        assert idea["matched_ingredients"] == ["番茄", "土豆"]
        assert idea["expiring_ingredients"] == ["番茄"]
        assert idea["missing_ingredients"] == ["牛腩", "八角"]
        assert _codes(response) == ["field_value_dropped"]

    def test_model_cannot_link_ideas_to_recipes(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [{
            "title": "番茄炒蛋", "source_type": "existing_recipe", "recipe_id": 7, "can_expand_to_recipe": False,
        }]})
        idea = _explore(client).json()["ideas"][0]
        assert (idea["source_type"], idea["recipe_id"], idea["can_expand_to_recipe"]) == ("ai_idea", None, True)

    def test_time_is_a_positive_int_or_null(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [
            {"title": "甲", "estimated_time_minutes": "20"},
            {"title": "乙", "estimated_time_minutes": "二十分钟"},
            {"title": "丙", "estimated_time_minutes": -5},
        ]})
        times = [i["estimated_time_minutes"] for i in _explore(client).json()["ideas"]]
        assert times == [20, None, None]


# ─── Expand ──────────────────────────────────────────────────────


def _draft(**overrides):
    data = {"title": "番茄炒蛋", "category": "vegetable_dish", "difficulty": "easy",
            "servings": 2, "cook_time_minutes": 15, "ingredients": [], "steps": STEPS}
    data.update(overrides)
    return json.dumps(data)


class TestExpand:
    def test_draft_shape_and_warnings(self, client, fake_ai):
        fake_ai.reply = _draft()
        response = _expand(client)
        assert response.status_code == 200
        body = response.json()
        assert body["locale"] == "zh-CN"
        assert body["warnings"] == [{"code": "draft_ai_generated", "params": {}}]
        assert body["recipe_draft"]["servings"] == "2"
        assert body["recipe_draft"]["steps"] == STEPS

    def test_draft_validates_as_recipe_create(self, client, fake_ai):
        fake_ai.reply = _draft(category=None, ingredients=[{"name": "鸡蛋", "quantity": 2, "unit": "个"}])
        draft = _expand(client).json()["recipe_draft"]
        assert draft["category"] is None
        RecipeCreate(**{**draft, "category": "vegetable_dish"})

    def test_no_invented_defaults(self, client, fake_ai):
        fake_ai.reply = json.dumps({"title": "番茄炒蛋", "steps": STEPS})
        draft = _expand(client, idea={"title": "番茄炒蛋"}).json()["recipe_draft"]
        assert (draft["difficulty"], draft["servings"], draft["cook_time_minutes"]) == (None, None, None)

    def test_cook_time_falls_back_to_the_idea(self, client, fake_ai):
        fake_ai.reply = json.dumps({"title": "番茄炒蛋", "steps": STEPS, "cook_time_minutes": "很快"})
        draft = _expand(client, idea={"title": "番茄炒蛋", "estimated_time_minutes": 12}).json()["recipe_draft"]
        assert draft["cook_time_minutes"] == 12

    @pytest.mark.parametrize("difficulty,expected", [("Easy", "easy"), ("hard", "hard"), ("简单", None)])
    def test_difficulty_enum(self, client, fake_ai, difficulty, expected):
        fake_ai.reply = _draft(difficulty=difficulty)
        response = _expand(client)
        assert response.json()["recipe_draft"]["difficulty"] == expected
        assert ("field_value_dropped" in _codes(response)) is (expected is None)

    @pytest.mark.parametrize("servings,expected", [("2", "2"), ("两人份", "两人份"), ("2 people", None), (0, None)])
    def test_servings(self, client, fake_ai, servings, expected):
        fake_ai.reply = _draft(servings=servings)
        assert _expand(client).json()["recipe_draft"]["servings"] == expected

    def test_saved_draft_matches_stock_in_consume_preview(self, client, db_session, fake_ai):
        """#66 part 5: stock 番茄 → draft says 番茄 (not 西红柿) → consume-preview finds the item."""
        tomato = _create_item(client, db_session, "番茄", quantity_unit="个")
        fake_ai.reply = _draft(ingredients=[{"ingredient_name": "西红柿", "quantity": "2", "unit": "个"}])
        draft = _expand(client).json()["recipe_draft"]
        assert draft["ingredients"][0]["ingredient_name"] == "番茄"

        # The edited draft is sent as-is as the POST /api/recipes body.
        recipe = client.post("/api/recipes", json={k: v for k, v in draft.items() if k != "warnings"})
        assert recipe.status_code == 201, recipe.text
        preview = client.get(f"/api/recipes/{recipe.json()['id']}/consume-preview").json()
        assert [(s["ingredient_name"], s["item_id"]) for s in preview["suggestions"]] == [("番茄", tomato["id"])]

    def test_ingredients_use_stock_names_and_units(self, client, db_session, fake_ai):
        _create_item(client, db_session, "番茄", quantity_unit="个")
        _create_item(client, db_session, "鸡蛋", slug="eggs", quantity_unit="盒")
        fake_ai.reply = _draft(ingredients=[
            {"ingredient_name": "西红柿", "quantity": "2", "unit": "pcs"},
            {"ingredient_name": "鸡蛋", "quantity": 1, "unit": "盒"},
            {"ingredient_name": "盐", "quantity": "适量", "unit": "克", "is_seasoning": True},
            {"ingredient_name": "糖", "quantity": "1/2", "unit": "茶匙"},
            {"ingredient_name": "葱", "quantity": "1", "unit": "斤", "is_optional": "yes"},
            {"quantity": "1"},
            "油",
        ])
        response = _expand(client)
        assert response.status_code == 200, response.text
        rows = [(i["ingredient_name"], i["quantity"], i["unit"], i["is_seasoning"], i["is_optional"])
                for i in response.json()["recipe_draft"]["ingredients"]]
        assert rows == [
            ("番茄", "2", "个", False, False),
            ("鸡蛋", "1", "盒", False, False),
            ("盐", "适量", None, True, False),
            ("糖", None, None, False, False),
            ("葱", None, None, False, False),
        ]
        assert [i["sort_order"] for i in response.json()["recipe_draft"]["ingredients"]] == [0, 1, 2, 3, 4]
        assert response.json()["warnings"] == [
            {"code": "draft_ai_generated", "params": {}},
            {"code": "quantity_dropped", "params": {"ingredient": "糖"}},
            {"code": "quantity_dropped", "params": {"ingredient": "葱"}},
            {"code": "ingredient_dropped_malformed", "params": {"index": "6"}},
            {"code": "ingredient_dropped_malformed", "params": {"index": "7"}},
        ]

    def test_prompt_lists_inventory_with_units(self, client, db_session, fake_ai):
        _create_item(client, db_session, "番茄", quantity_unit="个")
        fake_ai.reply = _draft()
        _expand(client)
        assert "- 番茄 (unit: 个)" in fake_ai.prompts[-1]
        system = fake_ai.system_prompts[-1]
        assert "克, 千克, 毫升" in system and "适量 / 少许" in system and "easy, medium, hard" in system

    def test_steps_are_renumbered_and_malformed_ones_dropped(self, client, fake_ai):
        fake_ai.reply = _draft(steps=[{"step_number": 5, "instruction": "切菜"}, {"x": 1}, "下锅", ""])
        response = _expand(client)
        assert response.json()["recipe_draft"]["steps"] == [
            {"step_number": 1, "instruction": "切菜"}, {"step_number": 2, "instruction": "下锅"},
        ]
        assert response.json()["warnings"][1:] == [
            {"code": "step_dropped_malformed", "params": {"index": "2"}},
            {"code": "step_dropped_malformed", "params": {"index": "4"}},
        ]

    def test_wrong_language_is_retried_once(self, client, fake_ai):
        fake_ai.responses = [
            _draft(steps=[{"step_number": 1, "instruction": "Cut the tomatoes"}]),
            _draft(),
        ]
        response = _expand(client)
        assert response.status_code == 200
        assert len(fake_ai.requests) == 2

    @pytest.mark.parametrize("bad", [
        _draft(title="Tomato Egg"),
        _draft(ingredients=[{"ingredient_name": "tomato", "quantity": "2", "unit": "个"}]),
        _draft(description="Easy dinner"),
        _draft(steps=[]),
        json.dumps({"title": "番茄炒蛋"}),
        json.dumps([{"title": "番茄炒蛋"}]),
    ])
    def test_unusable_twice_is_502(self, client, fake_ai, bad):
        fake_ai.reply = bad
        response = _expand(client)
        assert response.status_code == 502
        assert response.json()["code"] == "ai_upstream_error"
        assert {"params", "detail"} <= response.json().keys()
        assert len(fake_ai.requests) == 2

    def test_english_draft(self, client, fake_ai):
        fake_ai.reply = json.dumps({
            "title": "Tomato egg stir-fry", "difficulty": "easy",
            "ingredients": [{"ingredient_name": "salt", "quantity": "to taste"},
                            {"ingredient_name": "eggs", "quantity": "3", "unit": "pieces"}],
            "steps": ["Beat the eggs."],
        })
        response = _expand(client, idea={"title": "Tomato egg"}, locale="en")
        assert response.status_code == 200
        ingredients = response.json()["recipe_draft"]["ingredients"]
        assert [(i["quantity"], i["unit"]) for i in ingredients] == [("to taste", None), ("3", "pcs")]

    def test_repair_has_its_own_time_budget(self, client, fake_ai, monkeypatch):
        """Each round may use the whole AI_TOTAL_TIMEOUT_SECONDS: two 0.7 s
        rounds succeed under a 1 s limit."""
        _slow_provider(monkeypatch, [
            {"title": "Tomato Egg", "steps": ["Cook"]}, {"title": "番茄炒蛋", "steps": ["炒"]},
        ])
        response = _expand(client)
        assert response.status_code == 200
        assert response.json()["recipe_draft"]["title"] == "番茄炒蛋"

    def test_ai_off_is_503(self, client):
        assert _expand(client).status_code == 503


# ─── Repair rounds with feedback ─────────────────────────────────


def _followup(fake_ai, index=-1):
    """The (assistant, user) messages appended to a repair request."""
    messages = fake_ai.requests[index]["messages"]
    return messages[2:]


class TestExpandRepair:
    def test_feedback_names_the_problems(self, client, fake_ai):
        bad = _draft(steps=[{"step_number": 1, "instruction": "Cut the tomatoes"}], difficulty="简单")
        fake_ai.responses = [bad, _draft()]
        response = _expand(client)
        assert response.status_code == 200
        assert response.json()["recipe_draft"]["steps"] == STEPS
        assert len(fake_ai.requests) == 2
        assert _followup(fake_ai, 0) == []
        assistant, feedback = _followup(fake_ai)
        assert assistant["role"] == "assistant" and json.loads(assistant["content"]) == json.loads(bad)
        assert feedback["role"] == "user"
        assert 'steps[1].instruction "Cut the tomatoes" is not in Simplified Chinese.' in feedback["content"]
        assert 'difficulty "简单" must be one of: easy, medium, hard.' in feedback["content"]
        # The repaired draft is clean, so no warnings from the first round remain.
        assert response.json()["warnings"] == [{"code": "draft_ai_generated", "params": {}}]

    def test_lost_quantity_triggers_repair(self, client, fake_ai):
        fake_ai.responses = [
            _draft(ingredients=[{"ingredient_name": "糖", "quantity": "1/2", "unit": "茶匙"}]),
            _draft(ingredients=[{"ingredient_name": "糖", "quantity": "0.5", "unit": "茶匙"}]),
        ]
        response = _expand(client)
        feedback = _followup(fake_ai)[1]["content"]
        assert 'ingredients[1] "糖": quantity "1/2" with unit "茶匙" is not allowed' in feedback
        assert "适量 / 少许" in feedback
        ingredient = response.json()["recipe_draft"]["ingredients"][0]
        assert (ingredient["quantity"], ingredient["unit"]) == ("0.5", "茶匙")
        assert "quantity_dropped" not in _codes(response)

    @pytest.mark.parametrize("reply", [_draft(), _draft(difficulty="简单", servings="2 people", category="甜品")])
    def test_no_repair_when_only_enums_are_wrong(self, client, fake_ai, reply):
        fake_ai.reply = reply
        assert _expand(client).status_code == 200
        assert len(fake_ai.requests) == 1

    def test_worse_repair_keeps_the_first_draft(self, client, fake_ai):
        first = _draft(title="番茄炒蛋一", ingredients=[{"ingredient_name": "糖", "quantity": "1/2", "unit": "茶匙"}])
        fake_ai.responses = [first, _draft(title="Tomato Egg")]
        response = _expand(client)
        assert response.status_code == 200
        assert response.json()["recipe_draft"]["title"] == "番茄炒蛋一"
        assert "quantity_dropped" in _codes(response)

    def test_repair_with_more_problems_keeps_the_first_draft(self, client, fake_ai):
        one_bad = [{"ingredient_name": "糖", "quantity": "1/2", "unit": "茶匙"}]
        two_bad = one_bad + [{"ingredient_name": "盐", "quantity": "1", "unit": "斤"}]
        fake_ai.responses = [_draft(title="一", ingredients=one_bad), _draft(title="二", ingredients=two_bad)]
        assert _expand(client).json()["recipe_draft"]["title"] == "一"

    def test_equal_repair_is_preferred(self, client, fake_ai):
        bad_qty = [{"ingredient_name": "糖", "quantity": "1/2", "unit": "茶匙"}]
        fake_ai.responses = [_draft(title="一", ingredients=bad_qty), _draft(title="二", ingredients=bad_qty)]
        assert _expand(client).json()["recipe_draft"]["title"] == "二"

    def test_failed_repair_call_keeps_a_usable_first_draft(self, client, fake_ai):
        import httpx

        bad_qty = [{"ingredient_name": "糖", "quantity": "1/2", "unit": "茶匙"}]
        fake_ai.responses = [_draft(ingredients=bad_qty), httpx.Response(500), httpx.Response(500)]
        response = _expand(client)
        assert response.status_code == 200
        assert "quantity_dropped" in _codes(response)

    def test_failed_repair_call_with_unusable_first_draft_is_502(self, client, fake_ai):
        import httpx

        fake_ai.responses = [_draft(title="Tomato Egg"), httpx.Response(500), httpx.Response(500)]
        assert _expand(client).status_code == 502

    def test_non_object_reply_feedback(self, client, fake_ai):
        fake_ai.responses = [json.dumps([1, 2]), _draft()]
        assert _expand(client).status_code == 200
        assert "must be one JSON object" in _followup(fake_ai)[1]["content"]

    def test_missing_steps_feedback(self, client, fake_ai):
        fake_ai.responses = [_draft(steps=[]), _draft()]
        assert _expand(client).status_code == 200
        assert "steps is empty" in _followup(fake_ai)[1]["content"]


def _ideas(*titles, **fields):
    return json.dumps({"ideas": [{"title": t, **fields} for t in titles]})


class TestExploreRepair:
    def test_enough_ideas_means_no_repair(self, client, fake_ai):
        fake_ai.reply = _ideas("甲", "乙", "丙", "Tomato Egg")
        response = _explore(client)
        assert len(response.json()["ideas"]) == 3
        assert len(fake_ai.requests) == 1
        assert _codes(response) == ["idea_dropped_wrong_language"]

    def test_too_few_ideas_are_repaired(self, client, fake_ai):
        first = json.dumps({"ideas": [{"title": "甲"}, {"title": "Tomato Egg"}, {"title": "乙", "reason": "Fast"}, "x"]})
        fake_ai.responses = [first, _ideas("番茄炒蛋", "丙", "甲")]
        response = _explore(client)
        assert [i["title"] for i in response.json()["ideas"]] == ["甲", "番茄炒蛋", "丙"]
        assistant, feedback = _followup(fake_ai)
        assert json.loads(assistant["content"]) == json.loads(first)
        text = feedback["content"]
        assert 'Idea #2 title "Tomato Egg" is not in Simplified Chinese.' in text
        assert 'Idea #3 reason "Fast" is not in Simplified Chinese.' in text
        assert "Idea #4: not a JSON object." in text
        assert "only the ideas listed" in text
        # The first round's drops were repaired: no drop warnings remain.
        assert response.json()["warnings"] == []

    def test_repair_drops_are_reported(self, client, fake_ai):
        fake_ai.responses = [_ideas("Tomato Egg"), _ideas("番茄炒蛋", "Still English")]
        response = _explore(client)
        assert [i["title"] for i in response.json()["ideas"]] == ["番茄炒蛋"]
        assert response.json()["warnings"] == [
            {"code": "idea_dropped_wrong_language", "params": {"title": "Still English"}}
        ]

    def test_malformed_feedback(self, client, fake_ai):
        fake_ai.responses = [
            json.dumps({"ideas": [{"title": ""}, {"title": "甲", "flavors": "辣"}]}),
            _ideas("甲"),
        ]
        assert _explore(client).status_code == 200
        text = _followup(fake_ai)[1]["content"]
        assert "Idea #1: missing title." in text
        assert "Idea #2: flavors must be a list of strings." in text

    def test_empty_reply_feedback(self, client, fake_ai):
        fake_ai.responses = [json.dumps({"ideas": []}), _ideas("甲")]
        assert _explore(client).status_code == 200
        assert 'must be {"ideas": [...]}' in _followup(fake_ai)[1]["content"]

    def test_failed_repair_keeps_first_round_ideas(self, client, fake_ai):
        import httpx

        fake_ai.responses = [_ideas("甲", "Tomato Egg"), httpx.Response(500), httpx.Response(500)]
        response = _explore(client)
        assert response.status_code == 200
        assert [i["title"] for i in response.json()["ideas"]] == ["甲"]
        assert _codes(response) == ["idea_dropped_wrong_language"]

    def test_nothing_usable_after_repair_is_502(self, client, fake_ai):
        fake_ai.reply = _ideas("Tomato Egg")
        assert _explore(client).status_code == 502
        assert len(fake_ai.requests) == 2

    def test_two_good_ideas_are_too_few(self, client, fake_ai):
        fake_ai.responses = [_ideas("甲", "乙", "Egg"), _ideas("丙")]
        assert len(_explore(client).json()["ideas"]) == 3
        assert len(fake_ai.requests) == 2

    def test_too_few_but_nothing_to_fix_means_no_repair(self, client, fake_ai):
        fake_ai.reply = _ideas("甲")
        assert _explore(client).status_code == 200
        assert len(fake_ai.requests) == 1

    def test_repair_has_its_own_time_budget(self, client, fake_ai, monkeypatch):
        _slow_provider(monkeypatch, [
            {"ideas": [{"title": "甲"}, {"title": "Egg"}]}, {"ideas": [{"title": "乙"}]},
        ])
        response = _explore(client)
        assert response.status_code == 200
        assert [i["title"] for i in response.json()["ideas"]] == ["甲", "乙"]


def _slow_provider(monkeypatch, replies, delay=0.7, total="1"):
    """A provider that takes `delay` seconds per reply, under a `total` limit per round."""
    from stock_manager.api import ai_client
    from tests.conftest import sse_body

    monkeypatch.setenv("AI_TOTAL_TIMEOUT_SECONDS", total)
    ai_client.reload_config()
    queue = list(replies)

    async def handler(request):
        await asyncio.sleep(delay)
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=sse_body(json.dumps(queue.pop(0), ensure_ascii=False)))

    monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(handler))


@pytest.mark.parametrize("locale,rule", [
    ("zh-CN", "Do not use Japanese kana"), ("ja", "Use Japanese."), ("en", "Do not use Chinese or Japanese"),
])
def test_prompt_states_the_script_rules(client, fake_ai, locale, rule):
    fake_ai.reply = _ideas("甲" if locale != "en" else "Egg")
    _explore(client, locale=locale)
    assert rule in fake_ai.system_prompts[-1]

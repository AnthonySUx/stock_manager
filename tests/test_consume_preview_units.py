"""Issue #47: consume preview suggests an amount only in the stock's own unit."""

from datetime import date, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.quantity import normalize_unit, parse_quantity, same_unit
from tests.helpers import make_item_create_payload


def _create_item(client, db_session, name, quantity, unit):
    future = (date.today() + timedelta(days=60)).isoformat()
    payload = make_item_create_payload(
        name=name,
        category_id=get_category_by_slug(db_session, "vegetables").id,
        quantity_value=quantity,
        quantity_unit=unit,
        unopened_expiration_date=future,
        current_expiration_date=future,
    )
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _preview(client, ingredients):
    recipe = client.post(
        "/api/recipes",
        json={"title": "测试菜", "category": "vegetable_dish", "ingredients": ingredients},
    )
    assert recipe.status_code == 201, recipe.text
    response = client.get(f"/api/recipes/{recipe.json()['id']}/consume-preview")
    assert response.status_code == 200
    return {s["ingredient_name"]: s for s in response.json()["suggestions"]}


# ─── Parsing ──────────────────────────────────────────────────────


class TestParseQuantity:
    @pytest.mark.parametrize("quantity,unit,expected", [
        ("2个", None, (2.0, "个")),
        ("500克", "克", (500.0, "克")),
        ("1.5 kg", None, (1.5, "kg")),
        ("2", "个", (2.0, "个")),
        ("2", None, (2.0, None)),
        ("500克", "个", (500.0, None)),  # text and unit disagree → unknown
        ("适量", None, (None, None)),
        ("1/2", "个", (None, None)),
        ("2-3个", None, (None, None)),
        ("", "个", (None, None)),
        (None, None, (None, None)),
    ])
    def test_parse(self, quantity, unit, expected):
        assert parse_quantity(quantity, unit) == expected

    @pytest.mark.parametrize("a,b", [("克", "g"), ("G", "g"), ("毫升", "ml"), ("个", "pcs"), ("pieces", "个"), (" 瓶 ", "瓶")])
    def test_aliases_match(self, a, b):
        assert same_unit(a, b)

    @pytest.mark.parametrize("a,b", [("g", "kg"), ("克", "个"), ("ml", "l"), ("", ""), (None, "个")])
    def test_different_or_missing_units_do_not_match(self, a, b):
        assert not same_unit(a, b)

    def test_unknown_unit_is_kept_as_is(self):
        assert normalize_unit("Bottle") == "bottle"


# ─── Preview ──────────────────────────────────────────────────────


class TestPreviewUnits:
    def test_same_unit_suggests_recipe_amount(self, client, db_session):
        _create_item(client, db_session, "番茄", 5, "个")
        s = _preview(client, [{"ingredient_name": "番茄", "quantity": "2", "unit": "个"}])["番茄"]
        assert s["suggested_quantity"] == 2
        assert s["needs_user_input"] is False
        assert s["unit"] == "个"
        assert s["recipe_quantity"] == "2 个"

    def test_alias_unit_and_quantity_with_unit_in_text(self, client, db_session):
        _create_item(client, db_session, "土豆", 1000, "g")
        s = _preview(client, [{"ingredient_name": "土豆", "quantity": "500克", "unit": "克"}])["土豆"]
        assert s["suggested_quantity"] == 500
        assert s["needs_user_input"] is False
        assert s["recipe_quantity"] == "500克"

    def test_same_unit_is_capped_at_stock(self, client, db_session):
        _create_item(client, db_session, "番茄", 1, "个")
        s = _preview(client, [{"ingredient_name": "番茄", "quantity": "3", "unit": "个"}])["番茄"]
        assert s["suggested_quantity"] == 1

    def test_different_unit_needs_user_input(self, client, db_session):
        """The bug in #47: 500 g against 3 个 used to suggest the whole stock."""
        _create_item(client, db_session, "番茄", 3, "个")
        s = _preview(client, [{"ingredient_name": "番茄", "quantity": "500", "unit": "g"}])["番茄"]
        assert s["suggested_quantity"] is None
        assert s["needs_user_input"] is True
        assert s["confidence"] == "low"
        assert s["unit"] == "个"  # the user enters the amount in the stock unit
        assert s["recipe_quantity"] == "500 g"

    @pytest.mark.parametrize("quantity,unit", [
        ("适量", None),       # unparseable
        (None, None),         # no amount at all (used to become 1)
        ("2", None),          # number without a unit
        ("0", "个"),          # zero is not a suggestion
    ])
    def test_unknown_amount_needs_user_input(self, client, db_session, quantity, unit):
        _create_item(client, db_session, "番茄", 3, "个")
        s = _preview(client, [{"ingredient_name": "番茄", "quantity": quantity, "unit": unit}])["番茄"]
        assert s["suggested_quantity"] is None
        assert s["needs_user_input"] is True

    def test_preview_does_not_change_stock(self, client, db_session):
        item = _create_item(client, db_session, "番茄", 3, "个")
        _preview(client, [{"ingredient_name": "番茄", "quantity": "2", "unit": "个"}])
        assert client.get(f"/api/items/{item['id']}").json()["quantity_value"] == 3

"""Recipe batch allocations and the inventory-to-restock loop (#99)."""

from datetime import date

import pytest

from stock_manager.api import recipe_services
from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.models import Item, RecipeUsageHistory
from tests.helpers import make_item_create_payload, make_restock_create_payload


@pytest.fixture
def category_id(db_session, monkeypatch):
    monkeypatch.setattr("stock_manager.api.services.household_today", lambda db: date(2026, 11, 24))
    return get_category_by_slug(db_session, "vegetables").id


def _created(client, url, payload):
    response = client.post(url, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _stock(client, category_id, name, **overrides):
    return _created(client, "/api/items", make_item_create_payload(
        name=name, category_id=category_id, purchase_date="2026-11-18",
        **{"unopened_expiration_date": "infinite", "quantity_unit": "pcs", **overrides},
    ))


def _recipe(client, *ingredients):
    return _created(client, "/api/recipes", {
        "title": "Vegetable soup", "category": "soup", "ingredients": ingredients,
    })


def _ingredient(name, quantity="2", unit="pcs", **fields):
    return {"ingredient_name": name, "quantity": quantity, "unit": unit, **fields}


def _consume(item, quantity):
    return {"item_id": item["id"], "quantity": quantity, "ingredient_name": item["name"]}


@pytest.mark.parametrize(("required", "short"), [("4", False), ("6", True)])
def test_preview_allocates_matching_batches_in_expiration_order(client, category_id, required, short):
    later = _stock(client, category_id, "番茄", quantity_value=3,
                   unopened_expiration_date="2026-11-26")
    earlier = _stock(client, category_id, "西红柿", quantity_value=2,
                     unopened_expiration_date="2026-11-25", quantity_unit="个")
    _stock(client, category_id, "番茄", quantity_value=100,
           unopened_expiration_date="2026-11-24", quantity_unit="g")
    recipe = _recipe(client, _ingredient("番茄", required))

    response = client.get(f"/api/recipes/{recipe['id']}/consume-preview")

    assert response.status_code == 200, response.text
    suggestion, = response.json()["suggestions"]
    assert suggestion["allocations"] == [
        {"item_id": earlier["id"], "quantity": 2},
        {"item_id": later["id"], "quantity": 3 if short else 2},
    ]
    assert suggestion["needs_user_input"] is short
    assert (suggestion["item_id"], suggestion["item_name"], suggestion["unit"]) == (
        earlier["id"], earlier["name"], "个",
    )
    assert (suggestion["available_quantity"], suggestion["suggested_quantity"]) == (2, 2)
    for item in (earlier, later):
        assert client.get(f"/api/items/{item['id']}").json()["quantity_value"] == item["quantity_value"]


def test_preview_matching_fractional_batches_fill_the_requested_amount(client, category_id):
    first = _stock(client, category_id, "Tomato", quantity_value=0.1)
    second = _stock(client, category_id, "Tomato", quantity_value=0.2)
    recipe = _recipe(client, _ingredient("Tomato", "0.3"))

    response = client.get(f"/api/recipes/{recipe['id']}/consume-preview")

    assert response.status_code == 200, response.text
    suggestion, = response.json()["suggestions"]
    assert suggestion["allocations"] == [
        {"item_id": first["id"], "quantity": 0.1},
        {"item_id": second["id"], "quantity": 0.2},
    ]
    assert suggestion["needs_user_input"] is False


def test_missing_to_restock_creates_required_gaps_once_and_skips_synonyms(client, category_id):
    _stock(client, category_id, "西红柿")
    existing = _created(client, "/api/restock", make_restock_create_payload(name="马铃薯"))
    recipe = _recipe(
        client, _ingredient("番茄"), _ingredient("土豆"),
        _ingredient("Carrot", "300 g", None), _ingredient("Parsley", is_optional=True),
        _ingredient("Pepper", is_seasoning=True), _ingredient("carrot"),
    )
    url = f"/api/recipes/{recipe['id']}/missing-to-restock"

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == second.status_code == 200
    created, = first.json()["created"]
    assert {field: created[field] for field in (
        "name", "quantity_value", "quantity_unit", "status", "source_item_id",
    )} == {
        "name": "Carrot", "quantity_value": 300, "quantity_unit": "g",
        "status": "pending", "source_item_id": None,
    }
    assert first.json()["skipped"] == [
        {"name": "土豆", "reason": "already_pending"},
        {"name": "carrot", "reason": "already_pending"},
    ]
    assert second.json() == {"created": [], "skipped": [
        {"name": "土豆", "reason": "already_pending"},
        {"name": "Carrot", "reason": "already_pending"},
        {"name": "carrot", "reason": "already_pending"},
    ]}
    assert client.get("/api/restock").json() == [existing, created]


def test_missing_to_restock_rolls_back_all_rows_after_status_refresh(
    client, db_session, monkeypatch, category_id,
):
    monkeypatch.setattr("stock_manager.api.services.household_today", lambda db: date(2026, 11, 18))
    stale = _stock(client, category_id, "Tomato", unopened_expiration_date="2026-11-23")
    assert stale["status"] == "active"
    recipe = _recipe(client, _ingredient("Tomato"), _ingredient("Carrot"))
    monkeypatch.setattr("stock_manager.api.services.household_today", lambda db: date(2026, 11, 24))
    real_add = recipe_services._restock_recipe_ingredient
    attempted = []

    def fail_second(db, ingredient):
        attempted.append(ingredient.ingredient_name)
        if len(attempted) == 2:
            raise RuntimeError("simulated restock failure")
        row = real_add(db, ingredient)
        db.flush()
        return row

    monkeypatch.setattr(recipe_services, "_restock_recipe_ingredient", fail_second)
    with pytest.raises(RuntimeError, match="simulated restock failure"):
        client.post(f"/api/recipes/{recipe['id']}/missing-to-restock")

    assert attempted == ["Tomato", "Carrot"]
    assert db_session.get(Item, stale["id"]).status == "expired"
    assert client.get("/api/restock").json() == []


def test_cook_queues_only_depleted_stock_for_this_deduction(client, category_id):
    depleted = _stock(client, category_id, "Tomato", quantity_value=3)
    partial = _stock(client, category_id, "Carrot", quantity_value=3)
    before = client.post(f"/api/items/{depleted['id']}/consume", json={"quantity": 1})
    assert before.status_code == 200, before.text
    recipe = _recipe(client, _ingredient("Tomato"), _ingredient("Carrot"))

    response = client.post(f"/api/recipes/{recipe['id']}/cook", json={
        "consume_items": [_consume(depleted, 2), _consume(partial, 1)],
        "add_depleted_to_restock": True,
    })

    assert response.status_code == 200, response.text
    assert [item["remaining_quantity"] for item in response.json()["consumed_items"]] == [0, 2]
    entry, = client.get("/api/restock").json()
    assert (entry["source_item_id"], entry["quantity_value"], entry["status"]) == (
        depleted["id"], 2, "pending",
    )


def test_cook_rolls_back_deduction_if_depleted_restock_fails(
    client, db_session, monkeypatch, category_id,
):
    stock = _stock(client, category_id, "Tomato")
    recipe = _recipe(client, _ingredient("Tomato"))

    def fail(*args, **kwargs):
        raise RuntimeError("simulated restock failure")

    monkeypatch.setattr(recipe_services, "_add_stock_to_restock", fail)
    with pytest.raises(RuntimeError, match="simulated restock failure"):
        client.post(f"/api/recipes/{recipe['id']}/cook", json={
            "consume_items": [_consume(stock, 2)], "add_depleted_to_restock": True,
        })

    assert client.get(f"/api/items/{stock['id']}").json() == stock
    assert db_session.query(RecipeUsageHistory).count() == 0
    assert client.get("/api/restock").json() == []


def test_inventory_loop_restores_stock_from_a_recipe_gap(client, category_id):
    original = _stock(client, category_id, "Tomato")
    recipe = _recipe(client, _ingredient("Tomato"))
    url = f"/api/recipes/{recipe['id']}"

    cook = client.post(f"{url}/cook", json={"consume_items": [_consume(original, 2)]})
    assert cook.status_code == 200, cook.text
    assert cook.json()["consumed_items"][0]["remaining_quantity"] == 0
    assert client.get("/api/restock").json() == []

    gap = client.post(f"{url}/missing-to-restock")
    assert gap.status_code == 200, gap.text
    assert gap.json()["skipped"] == []
    entry, = gap.json()["created"]
    assert (entry["name"], entry["quantity_value"], entry["status"]) == ("Tomato", 2, "pending")

    done = client.post(f"/api/restock/{entry['id']}/done", json={
        "category_id": category_id, "purchased_quantity": entry["quantity_value"],
        "owner": original["owner"], "location": original["location"],
    })
    assert done.status_code == 200, done.text
    assert client.get(f"/api/restock/{entry['id']}").json()["status"] == "done"

    restored, = client.get("/api/items", params={"status": "active"}).json()
    assert restored["id"] != original["id"]
    assert (restored["name"], restored["quantity_unit"], restored["quantity_value"]) == (
        original["name"], original["quantity_unit"], original["quantity_value"],
    )
    assert client.get(f"{url}/consume-preview").json()["suggestions"][0]["allocations"] == [
        {"item_id": restored["id"], "quantity": 2},
    ]

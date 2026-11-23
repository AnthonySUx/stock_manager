"""Atomic inventory deductions and their API results (#98)."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.errors import APIError
from stock_manager.api.models import Base, Category, Item, Recipe, RecipeUsageHistory, RestockItem
from stock_manager.api.recipe_services import cook_recipe_and_consume
from stock_manager.api.services import consume_item
from tests.helpers import (
    make_item_create_payload,
    make_item_model_data,
    make_restock_create_payload,
)


def _created(client, url, payload):
    response = client.post(url, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _item(client, db, *, quantity=3, category="vegetables"):
    return _created(client, "/api/items", make_item_create_payload(
        category_id=get_category_by_slug(db, category).id,
        quantity_value=quantity,
        notes="Keep refrigerated",
    ))


def _recipe(client):
    return _created(client, "/api/recipes", {"title": "Soup", "category": "soup"})


def _line(item_id, quantity, name):
    return {"item_id": item_id, "quantity": quantity, "ingredient_name": name}


def test_consume_over_stock_returns_available_and_leaves_inventory_unchanged(client, db_session):
    item = _item(client, db_session)
    url = f"/api/items/{item['id']}"

    response = client.post(f"{url}/consume", json={"quantity": 10, "add_to_restock": True})

    assert response.status_code == 422
    assert response.json()["code"] == "consume_exceeds_stock"
    assert response.json()["params"] == {"available": 3}
    assert client.get(url).json() == item
    assert client.get("/api/restock").json() == []


def test_consume_missing_item_returns_404_without_creating_restock(client):
    response = client.post("/api/items/99999/consume", json={
        "quantity": 1, "add_to_restock": True,
    })

    assert response.status_code == 404
    assert client.get("/api/restock").json() == []


@pytest.mark.parametrize("quantity", [1, 3])
def test_consume_response_includes_restock_for_the_deducted_amount(client, db_session, quantity):
    item = _item(client, db_session)
    url = f"/api/items/{item['id']}"

    response = client.post(f"{url}/consume", json={"quantity": quantity, "add_to_restock": True})

    assert response.status_code == 200, response.text
    stock = response.json()
    restock = stock.pop("restock_item")
    assert stock == client.get(url).json()
    assert stock["quantity_value"] == 3 - quantity
    assert (restock["quantity_value"], restock["status"], restock["source_item_id"]) == (
        quantity, "pending", item["id"],
    )
    assert client.get("/api/restock").json() == [restock]


def test_consume_returns_null_restock_when_not_requested(client, db_session):
    item = _item(client, db_session)
    response = client.post(f"/api/items/{item['id']}/consume", json={"quantity": 1})
    assert response.status_code == 200, response.text
    assert response.json()["restock_item"] is None
    assert client.get("/api/restock").json() == []


def test_repeated_full_consume_deducts_and_queues_restock_once(client, db_session):
    item = _item(client, db_session)
    url = f"/api/items/{item['id']}"
    payload = {"quantity": 3, "add_to_restock": True}

    first, second, third = [client.post(f"{url}/consume", json=payload) for _ in range(3)]

    assert [response.status_code for response in (first, second, third)] == [200, 409, 409]
    assert second.json()["code"] == third.json()["code"] == "item_already_consumed"
    stored = client.get(url).json()
    assert (stored["quantity_value"], stored["status"]) == (0, "consumed")
    assert client.get("/api/restock").json() == [first.json()["restock_item"]]


def test_cook_reports_every_line_and_deducts_only_eligible_stock(client, db_session):
    valid = _item(client, db_session)
    never = _item(client, db_session, category="medicine")
    short = _item(client, db_session, quantity=1)
    recipe = _recipe(client)
    entries = [
        _line(short["id"], 2, "Small batch"),
        _line(99999, 1, "Missing"),
        _line(never["id"], 1, "Ineligible"),
        _line(valid["id"], 2, "Vegetables"),
    ]

    response = client.post(f"/api/recipes/{recipe['id']}/cook", json={
        "consume_items": entries, "notes": "Dinner",
    })

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lines"] == [
        {"item_id": short["id"], "ingredient_name": "Small batch", "result": "insufficient",
         "requested": 2, "available": 1},
        {"item_id": 99999, "ingredient_name": "Missing", "result": "skipped",
         "reason": "item_not_found"},
        {"item_id": never["id"], "ingredient_name": "Ineligible", "result": "skipped",
         "reason": "not_recipe_usable"},
        {"item_id": valid["id"], "ingredient_name": "Vegetables", "result": "consumed",
         "consumed_quantity": 2},
    ]
    assert [row["item_id"] for row in body["consumed_items"]] == [valid["id"]]
    assert body["notes"] == "Dinner"
    assert db_session.get(Item, valid["id"]).quantity_value == 1
    assert db_session.get(Item, never["id"]).quantity_value == never["quantity_value"]
    assert db_session.get(Item, short["id"]).quantity_value == short["quantity_value"]
    history = db_session.query(RecipeUsageHistory).one()
    assert (history.recipe_id, history.event_type) == (recipe["id"], "cooked")


def test_cook_with_all_lines_failing_leaves_stock_and_history_unchanged(client, db_session):
    item = _item(client, db_session, quantity=1)
    recipe = _recipe(client)

    response = client.post(f"/api/recipes/{recipe['id']}/cook", json={
        "consume_items": [_line(item["id"], 2, "Vegetables"), _line(99999, 1, "Missing")],
    })

    assert response.status_code == 409
    assert response.json()["code"] == "cook_nothing_consumed"
    assert response.json()["params"]["lines"] == [
        {"item_id": item["id"], "ingredient_name": "Vegetables", "result": "insufficient",
         "requested": 2, "available": 1},
        {"item_id": 99999, "ingredient_name": "Missing", "result": "skipped",
         "reason": "item_not_found"},
    ]
    assert db_session.get(Item, item["id"]).quantity_value == 1
    assert db_session.query(RecipeUsageHistory).count() == 0


def test_cook_with_empty_list_still_records_history(client, db_session):
    item = _item(client, db_session)
    recipe = _recipe(client)

    response = client.post(f"/api/recipes/{recipe['id']}/cook", json={"consume_items": []})

    assert response.status_code == 200, response.text
    assert response.json()["lines"] == response.json()["consumed_items"] == []
    assert db_session.get(Item, item["id"]).quantity_value == 3
    assert db_session.query(RecipeUsageHistory).one().event_type == "cooked"


def test_cook_rejects_duplicate_before_any_deduction(client, db_session):
    item = _item(client, db_session)
    other = _item(client, db_session)
    recipe = _recipe(client)

    response = client.post(f"/api/recipes/{recipe['id']}/cook", json={
        "consume_items": [
            _line(other["id"], 1, "Other"),
            _line(item["id"], 1, "First"),
            _line(item["id"], 2, "Repeat"),
        ],
    })

    assert response.status_code == 422
    assert response.json()["code"] == "duplicate_item"
    assert response.json()["params"] == {"item_id": item["id"]}
    assert [db_session.get(Item, row["id"]).quantity_value for row in (item, other)] == [3, 3]
    assert db_session.query(RecipeUsageHistory).count() == 0


def test_repeated_cook_of_same_depleted_stock_records_history_once(client, db_session):
    item = _item(client, db_session)
    recipe = _recipe(client)
    url = f"/api/recipes/{recipe['id']}/cook"
    payload = {"consume_items": [_line(item["id"], 3, "Vegetables")]}

    first, second = [client.post(url, json=payload) for _ in range(2)]

    assert [first.status_code, second.status_code] == [200, 409]
    assert second.json()["code"] == "cook_nothing_consumed"
    assert second.json()["params"]["lines"][0]["available"] == 0
    assert db_session.get(Item, item["id"]).quantity_value == 0
    assert db_session.query(RecipeUsageHistory).count() == 1


@pytest.mark.parametrize(("operation", "quantity", "error_code"), [
    ("consume", 3, "item_already_consumed"),
    ("consume", 2, "consume_exceeds_stock"),
    ("cook", 3, "cook_nothing_consumed"),
    ("cook", 2, "cook_nothing_consumed"),
])
def test_concurrent_deductions_with_stale_reads_cannot_overdraw_stock(
    tmp_path, operation, quantity, error_code,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent-deduction.db'}")
    Session = sessionmaker(bind=engine, autoflush=False)
    try:
        Base.metadata.create_all(engine)
        with Session.begin() as db:
            category = Category(name="Vegetables", slug="vegetables", recipe_usage="always")
            recipe = Recipe(title="Soup", source_type="user", source_name="User")
            db.add_all([category, recipe])
            db.flush()
            item = Item(**make_item_model_data(category_id=category.id, quantity_value=3))
            db.add(item)
            db.flush()
            item_id, recipe_id = item.id, recipe.id

        both_have_read = Barrier(2)

        def deduct():
            with Session() as db:
                stale = db.get(Item, item_id)
                assert stale.quantity_value == 3
                both_have_read.wait(timeout=5)
                try:
                    if operation == "consume":
                        consume_item(db, item_id, quantity, add_to_restock=True)
                    else:
                        cook_recipe_and_consume(db, recipe_id, [_line(item_id, quantity, "Vegetables")])
                except APIError as exc:
                    if error_code == "consume_exceeds_stock":
                        assert exc.status_code == 422
                        assert exc.params["available"] == 1
                    else:
                        assert exc.status_code == 409
                    if operation == "cook":
                        assert exc.params["lines"][0]["available"] == 3 - quantity
                    return exc.code
                return "success"

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: deduct(), range(2)))

        assert sorted(results) == sorted(["success", error_code])
        with Session() as db:
            stored = db.get(Item, item_id)
            assert stored.quantity_value == 3 - quantity
            assert stored.status == ("consumed" if quantity == 3 else "active")
            assert db.query(RestockItem).count() == (operation == "consume")
            assert db.query(RecipeUsageHistory).count() == (operation == "cook")
    finally:
        engine.dispose()


def test_delete_queues_remaining_stock_and_detaches_existing_restock(client, db_session):
    item = _item(client, db_session)
    existing = _created(client, "/api/restock", make_restock_create_payload(
        name="Existing", source_item_id=item["id"],
    ))
    url = f"/api/items/{item['id']}"

    response = client.delete(url, params={"add_to_restock": True})

    assert response.status_code == 200, response.text
    assert client.get(url).status_code == 404
    assert client.delete(url, params={"add_to_restock": True}).status_code == 404
    old, queued = client.get("/api/restock").json()
    assert old["id"] == existing["id"]
    assert old["source_item_id"] is None
    for field in ("name", "quantity_unit", "quantity_value", "category_id", "notes"):
        assert queued[field] == item[field]
    assert (queued["status"], queued["source_item_id"]) == ("pending", None)


@pytest.mark.parametrize(("remaining", "add_to_restock"), [(0, True), (3, False)])
def test_delete_without_a_positive_requested_restock_queues_nothing(
    client, db_session, remaining, add_to_restock,
):
    item = _item(client, db_session)
    url = f"/api/items/{item['id']}"
    if remaining == 0:
        assert client.post(f"{url}/consume", json={"quantity": 3}).status_code == 200

    response = client.delete(url, params={"add_to_restock": add_to_restock})

    assert response.status_code == 200, response.text
    assert client.get("/api/restock").json() == []


@pytest.mark.parametrize(("operation", "failure_target"), [
    ("consume", "stock_manager.api.services.RestockItem"),
    ("cook", "stock_manager.api.recipe_services.RecipeUsageHistory"),
    ("delete", "stock_manager.api.services._add_stock_to_restock"),
])
def test_write_rolls_back_if_its_companion_insert_fails(
    client, db_session, monkeypatch, operation, failure_target,
):
    item = _item(client, db_session)
    recipe = _recipe(client)
    existing = _created(client, "/api/restock", make_restock_create_payload(source_item_id=item["id"]))
    url = f"/api/items/{item['id']}"

    def fail(*args, **kwargs):
        raise RuntimeError("simulated insert failure")

    with monkeypatch.context() as patch:
        patch.setattr(failure_target, fail)
        with pytest.raises(RuntimeError, match="simulated insert failure"):
            if operation == "consume":
                client.post(f"{url}/consume", json={"quantity": 3, "add_to_restock": True})
            elif operation == "cook":
                client.post(f"/api/recipes/{recipe['id']}/cook", json={
                    "consume_items": [_line(item["id"], 3, "Vegetables")],
                })
            else:
                client.delete(url, params={"add_to_restock": True})

    assert client.get(url).json() == item
    assert client.get("/api/restock").json() == [existing]
    assert db_session.query(RecipeUsageHistory).count() == 0

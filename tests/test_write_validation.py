"""Regression tests for inventory write validation (#96)."""

import json

import pytest

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.models import RecipeUsageHistory
from tests.helpers import make_item_create_payload, make_restock_create_payload


@pytest.fixture
def item_payload(db_session):
    return make_item_create_payload(
        category_id=get_category_by_slug(db_session, "vegetables").id,
        unopened_expiration_date="infinite",
    )


def _create(client, url, payload):
    response = client.post(url, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("status", ["banana", "active", None])
def test_item_patch_rejects_status_without_writing(client, item_payload, status):
    original = _create(client, "/api/items", item_payload)
    url = f"/api/items/{original['id']}"

    response = client.patch(url, json={"status": status, "name": "Changed"})

    assert response.status_code == 422
    assert response.json()["code"] == "item_status_readonly"
    assert client.get(url).json() == original


@pytest.mark.parametrize(
    ("already_done", "status"),
    [(False, "banana"), (False, "done"), (False, None), (True, "pending")],
)
def test_restock_patch_rejects_status_without_writing(
    client, item_payload, already_done, status
):
    original = _create(
        client, "/api/restock",
        make_restock_create_payload(category_id=item_payload["category_id"]),
    )
    url = f"/api/restock/{original['id']}"
    if already_done:
        response = client.post(f"{url}/done", json={
            "purchased_quantity": 12, "owner": "Alex", "location": "Pantry",
        })
        assert response.status_code == 200, response.text
        original = client.get(url).json()
        assert original["status"] == "done"
    items_before = client.get("/api/items").json()

    response = client.patch(url, json={"status": status, "notes": "Changed"})

    assert response.status_code == 422
    assert response.json()["code"] == "restock_status_readonly"
    assert client.get(url).json() == original
    assert client.get("/api/items").json() == items_before


@pytest.mark.parametrize(
    "invalid_number", ["NaN", "Infinity", "-Infinity", "1e999", '"NaN"', '"Infinity"']
)
@pytest.mark.parametrize(
    "operation",
    ["item-create", "item-patch", "consume", "restock-create", "restock-patch", "done", "cook"],
)
def test_quantity_must_be_finite_without_writing(
    client, db_session, item_payload, operation, invalid_number
):
    items_url = "/api/items"
    restock_url = "/api/restock"
    item = _create(client, items_url, item_payload)
    restock_payload = make_restock_create_payload(category_id=item_payload["category_id"])
    restock = _create(client, restock_url, restock_payload)
    item_url = f"{items_url}/{item['id']}"
    restock_item_url = f"{restock_url}/{restock['id']}"
    recipe = _create(client, "/api/recipes", {"title": "Soup", "category": "soup"})

    method, url, payload = {
        "item-create": ("POST", items_url, {**item_payload, "quantity_value": "INVALID"}),
        "item-patch": ("PATCH", item_url, {"quantity_value": "INVALID"}),
        "consume": ("POST", f"{item_url}/consume", {"quantity": "INVALID"}),
        "restock-create": ("POST", restock_url, {**restock_payload, "quantity_value": "INVALID"}),
        "restock-patch": ("PATCH", restock_item_url, {"quantity_value": "INVALID"}),
        "done": ("POST", f"{restock_item_url}/done", {"purchased_quantity": "INVALID"}),
        "cook": ("POST", f"/api/recipes/{recipe['id']}/cook", {
            "consume_items": [{"item_id": item["id"], "quantity": "INVALID"}],
        }),
    }[operation]
    body = json.dumps(payload).replace('"INVALID"', invalid_number)

    response = client.request(
        method, url, content=body, headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["type"] == "finite_number"
    assert client.get(items_url).json() == [item]
    assert client.get(restock_url).json() == [restock]
    assert db_session.query(RecipeUsageHistory).count() == 0


@pytest.mark.parametrize("field", ["name", "owner", "location"])
def test_item_writes_reject_blank_text_without_writing(client, item_payload, field):
    original = _create(client, "/api/items", item_payload)
    payload = {**item_payload, field: " \t\n "}

    create = client.post("/api/items", json=payload)
    patch = client.patch(f"/api/items/{original['id']}", json={field: payload[field]})

    for response in (create, patch):
        assert response.status_code == 422, response.text
        assert response.json()["detail"][0]["loc"] == ["body", field]
    assert client.get("/api/items").json() == [original]


def test_restock_writes_reject_blank_name_without_writing(client):
    payload = make_restock_create_payload()
    original = _create(client, "/api/restock", payload)

    create = client.post("/api/restock", json={**payload, "name": " \t\n "})
    patch = client.patch(f"/api/restock/{original['id']}", json={"name": " \t\n "})

    for response in (create, patch):
        assert response.status_code == 422, response.text
        assert response.json()["detail"][0]["loc"] == ["body", "name"]
    assert client.get("/api/restock").json() == [original]


def test_stock_and_restock_writes_trim_text(client, item_payload):
    stock_text = {"name": " Tomato ", "owner": " Alex ", "location": " Fridge "}
    item = _create(client, "/api/items", {**item_payload, **stock_text})
    assert {field: item[field] for field in stock_text} == {
        "name": "Tomato", "owner": "Alex", "location": "Fridge",
    }
    response = client.patch(
        f"/api/items/{item['id']}",
        json={"name": " Spinach ", "owner": " Jamie ", "location": " Pantry ", "extra": 1},
    )
    assert response.status_code == 200, response.text
    assert {field: response.json()[field] for field in stock_text} == {
        "name": "Spinach", "owner": "Jamie", "location": "Pantry",
    }

    restock = _create(client, "/api/restock", make_restock_create_payload(name=" Milk "))
    assert restock["name"] == "Milk"
    response = client.patch(
        f"/api/restock/{restock['id']}", json={"name": " Oat milk ", "extra": 1},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Oat milk"


@pytest.mark.parametrize("field", ["notes", "category_id", "quantity_value", "quantity_unit"])
def test_restock_patch_explicit_null_clears_only_the_sent_field(client, item_payload, field):
    original = _create(
        client, "/api/restock",
        make_restock_create_payload(category_id=item_payload["category_id"]),
    )
    url = f"/api/restock/{original['id']}"

    response = client.patch(url, json={field: None})

    expected = {**original, field: None}
    if field == "category_id":
        expected["category"] = None
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert client.get(url).json() == expected


@pytest.mark.parametrize(("payload", "status_code"), [({}, 400), ({"name": None}, 422)])
def test_restock_patch_rejects_empty_body_and_null_name(client, payload, status_code):
    original = _create(client, "/api/restock", make_restock_create_payload())
    url = f"/api/restock/{original['id']}"

    assert client.patch(url, json=payload).status_code == status_code
    assert client.get(url).json() == original


def test_item_create_derives_fields_with_or_without_legacy_inputs(client, item_payload):
    supplied = _create(
        client, "/api/items",
        {**item_payload, "current_expiration_date": "2000-01-01", "status": "banana"},
    )
    del item_payload["current_expiration_date"], item_payload["status"]
    omitted = _create(client, "/api/items", item_payload)
    explicit_null = _create(
        client, "/api/items",
        {**item_payload, "current_expiration_date": None, "status": None},
    )

    assert supplied["current_expiration_date"] == "infinite"
    assert supplied["status"] == "active"
    server_metadata = {"id", "created_at", "updated_at"}
    assert supplied.keys() == omitted.keys() == explicit_null.keys()
    for field in supplied.keys() - server_metadata:
        assert supplied[field] == omitted[field] == explicit_null[field]


def test_cook_can_report_zero_remaining_quantity(client, item_payload):
    item = _create(client, "/api/items", item_payload)
    recipe = _create(client, "/api/recipes", {"title": "Soup", "category": "soup"})

    response = client.post(f"/api/recipes/{recipe['id']}/cook", json={
        "consume_items": [{"item_id": item["id"], "quantity": item["quantity_value"]}],
    })

    assert response.status_code == 200, response.text
    consumed, = response.json()["consumed_items"]
    assert consumed["item_id"] == item["id"]
    assert consumed["consumed_quantity"] == item["quantity_value"]
    assert consumed["remaining_quantity"] == 0
    assert consumed["status"] == "consumed"
    stored = client.get(f"/api/items/{item['id']}").json()
    assert (stored["quantity_value"], stored["status"]) == (0, "consumed")

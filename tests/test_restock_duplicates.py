"""GET /api/restock/duplicates finds pending items with the same or a synonym name (#18)."""

import pytest

from tests.helpers import make_restock_create_payload

URL = "/api/restock/duplicates"


def _add(client, name, **fields):
    response = client.post("/api/restock", json=make_restock_create_payload(name=name, **fields))
    assert response.status_code == 201, response.text
    return response.json()


def _done(client, item_id):
    response = client.post(f"/api/restock/{item_id}/done", json={
        "purchased_quantity": 12, "owner": "me", "location": "Fridge",
        "unopened_expiration_date": "infinite",
    })
    assert response.status_code == 200, response.text


def test_same_name_and_synonym_match_pending_items(client):
    egg = _add(client, "鸡蛋")
    upper = _add(client, " EGG ")
    _add(client, "茄子")

    body = client.get(URL, params={"name": "  egg "}).json()

    assert body["query"] == "egg" and body["normalized_name"] == "鸡蛋"
    assert [(c["id"], c["match_reason"]) for c in body["candidates"]] == [
        (egg["id"], "synonym"), (upper["id"], "same_name"),
    ]
    first = body["candidates"][0]
    assert first["name"] == "鸡蛋" and first["status"] == "pending"
    assert first["quantity_value"] == 12 and first["quantity_unit"] == "个"
    assert "category" in first and "created_at" in first


@pytest.mark.parametrize(("query", "stored"), [
    ("egg", "eggplant"), ("蛋", "蛋糕"), ("鸡蛋", "鸭蛋"), ("鸡蛋", "鹌鹑蛋"),
])
def test_no_substring_matching(client, query, stored):
    _add(client, stored)
    assert client.get(URL, params={"name": query}).json()["candidates"] == []


def test_done_items_are_ignored(client):
    category_id = client.get("/api/categories").json()[0]["id"]
    item = _add(client, "牛奶", category_id=category_id)
    _done(client, item["id"])
    assert client.get(URL, params={"name": "牛奶"}).json()["candidates"] == []


def test_unknown_name_returns_itself_as_normalized_name(client):
    body = client.get(URL, params={"name": " 自制辣酱 "}).json()
    assert body == {"query": "自制辣酱", "normalized_name": "自制辣酱", "candidates": []}


@pytest.mark.parametrize("params", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 256}])
def test_invalid_name_returns_422(client, params):
    response = client.get(URL, params=params)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_check_is_read_only(client):
    _add(client, "鸡蛋")
    before = client.get("/api/restock").json()
    client.get(URL, params={"name": "egg"})
    assert client.get("/api/restock").json() == before


def test_restock_item_route_still_works(client):
    item = _add(client, "鸡蛋")
    assert client.get(f"/api/restock/{item['id']}").json()["id"] == item["id"]

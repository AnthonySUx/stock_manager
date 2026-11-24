"""Shopping check state for restock items (#22)."""

from stock_manager.api.models import Item
from tests.helpers import make_restock_create_payload


def _add(client, name="鸡蛋", **fields):
    category_id = client.get("/api/categories").json()[0]["id"]
    response = client.post("/api/restock", json=make_restock_create_payload(
        name=name, category_id=category_id, **fields,
    ))
    assert response.status_code == 201, response.text
    return response.json()


def _check(client, item_id, action="check"):
    return client.post(f"/api/restock/{item_id}/shopping-{action}")


def _done(client, item_id, quantity):
    response = client.post(f"/api/restock/{item_id}/done", json={
        "purchased_quantity": quantity, "owner": "me", "location": "Fridge",
        "unopened_expiration_date": "infinite",
    })
    assert response.status_code == 200, response.text


def test_new_items_are_unchecked(client):
    item = _add(client)
    assert item["shopping_checked"] is False and item["shopping_checked_at"] is None


def test_check_keeps_item_pending_and_creates_no_stock(client, db_session):
    item = _add(client)
    response = _check(client, item["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["shopping_checked"] is True and body["shopping_checked_at"] is not None
    assert body["status"] == "pending" and body["quantity_value"] == 12
    assert db_session.query(Item).count() == 0


def test_repeated_check_keeps_first_time_and_uncheck_clears(client):
    item = _add(client)
    first = _check(client, item["id"]).json()["shopping_checked_at"]
    assert _check(client, item["id"]).json()["shopping_checked_at"] == first

    body = _check(client, item["id"], "uncheck").json()
    assert body["shopping_checked"] is False and body["shopping_checked_at"] is None
    assert _check(client, item["id"], "uncheck").status_code == 200
    assert client.get(f"/api/restock/{item['id']}").json()["status"] == "pending"


def test_list_filters_by_shopping_state(client):
    eggs, milk, rice = _add(client, "鸡蛋"), _add(client, "牛奶"), _add(client, "大米")
    _check(client, milk["id"])
    _done(client, rice["id"], 12)

    def ids(**params):
        return [row["id"] for row in client.get("/api/restock", params=params).json()]

    assert ids(status="pending", shopping_checked="false") == [eggs["id"]]
    assert ids(status="pending", shopping_checked="true") == [milk["id"]]
    assert ids() == [eggs["id"], milk["id"], rice["id"]]
    assert client.get("/api/restock", params={"shopping_checked": "maybe"}).status_code == 422


def test_done_item_cannot_be_checked_or_unchecked(client):
    item = _add(client)
    _done(client, item["id"], 12)
    for action in ("check", "uncheck"):
        response = _check(client, item["id"], action)
        assert response.status_code == 409 and response.json()["code"] == "restock_already_done"


def test_unknown_item_returns_404(client):
    for action in ("check", "uncheck"):
        response = _check(client, 999_999, action)
        assert response.status_code == 404 and response.json()["code"] == "restock_not_found"


def test_full_purchase_of_checked_item_still_stocks_it(client, db_session):
    item = _add(client)
    _check(client, item["id"])
    _done(client, item["id"], 12)
    assert client.get(f"/api/restock/{item['id']}").json()["status"] == "done"
    assert db_session.query(Item).count() == 1


def test_partial_purchase_puts_the_rest_back_on_the_shopping_list(client):
    item = _add(client)
    _check(client, item["id"])
    _done(client, item["id"], 5)
    body = client.get(f"/api/restock/{item['id']}").json()
    assert body["status"] == "pending" and body["quantity_value"] == 7
    assert body["shopping_checked"] is False and body["shopping_checked_at"] is None


def test_patch_cannot_set_shopping_state(client):
    item = _add(client)
    response = client.patch(f"/api/restock/{item['id']}", json={"shopping_checked_at": "2026-11-25T10:00:00"})
    assert client.get(f"/api/restock/{item['id']}").json()["shopping_checked"] is False
    assert response.status_code in (400, 422)

"""Inventory date derivation and status freshness regressions for issue #97."""

from datetime import date, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.models import Item, Setting
from stock_manager.api.routers.recipes import _load_explore_inventory
from stock_manager.api.services import _calculate_status, refresh_item_statuses
from tests.helpers import (
    make_item_create_payload,
    make_item_model_data,
    make_restock_create_payload,
)


TODAY = date(2026, 11, 24)
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


@pytest.fixture
def item_payload(db_session, monkeypatch):
    monkeypatch.setattr("stock_manager.api.services.household_today", lambda db: TODAY)
    return make_item_create_payload(
        name="Tomato",
        category_id=get_category_by_slug(db_session, "vegetables").id,
        owner="Alex",
        location="Pantry",
        purchase_date="2026-11-20",
        unopened_expiration_date="infinite",
    )


def _post_created(client, url, payload):
    response = client.post(url, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _restock(client, item_payload, **fields):
    return _post_created(client, "/api/restock", make_restock_create_payload(
        name=item_payload["name"],
        category_id=item_payload["category_id"],
        **fields,
    ))


def _status_and_expiration(item):
    return item.current_expiration_date, item.status


@pytest.mark.parametrize(
    ("dates", "expiration", "status"),
    [
        ({"unopened_expiration_date": "infinite"}, "infinite", "active"),
        ({"unopened_expiration_date": TODAY.isoformat()}, TODAY.isoformat(), "expiring soon"),
        ({"unopened_expiration_date": YESTERDAY}, YESTERDAY, "expired"),
        ({
            "unopened_expiration_date": "2026-12-01",
            "opened_date": "2026-11-21",
            "opened_expiration_date": YESTERDAY,
        }, YESTERDAY, "expired"),
        ({
            "unopened_expiration_date": YESTERDAY,
            "opened_date": "2026-11-21",
            "opened_expiration_date": "infinite",
        }, "infinite", "active"),
    ],
)
def test_stock_write_paths_derive_identical_dates_and_status(
    client, db_session, item_payload, dates, expiration, status,
):
    created = _post_created(client, "/api/items", {**item_payload, **dates})
    original = _post_created(client, "/api/items", item_payload)
    patch = client.patch(f"/api/items/{original['id']}", json=dates)
    assert patch.status_code == 200, patch.text

    restock = _restock(client, item_payload)
    purchase = client.post(f"/api/restock/{restock['id']}/done", json={
        "purchased_quantity": 12, "owner": "Alex", "location": "Pantry",
        "purchase_date": item_payload["purchase_date"], **dates,
    })
    assert purchase.status_code == 200, purchase.text
    purchased = db_session.query(Item).order_by(Item.id.desc()).first()

    confirmed = _post_created(client, "/api/intake/confirm", {"items": [{
        **item_payload, **dates, "temporary_id": "cand_00000001",
    }]})
    confirmed_item = db_session.get(Item, confirmed["created"][0]["item_id"])
    assert _status_and_expiration(purchased) == _status_and_expiration(confirmed_item) == (
        expiration, status,
    )
    for result in (created, patch.json()):
        assert (result["current_expiration_date"], result["status"]) == (expiration, status)


@pytest.mark.parametrize(("dates", "code"), [
    ({"unopened_expiration_date": "2026-11-19"}, "expiration_before_purchase"),
    ({
        "opened_date": "2026-11-22",
        "opened_expiration_date": "2026-11-21",
    }, "opened_expiration_before_opened"),
])
def test_invalid_date_pairs_are_rejected_without_writing(
    client, db_session, item_payload, dates, code,
):
    original = _post_created(client, "/api/items", item_payload)
    restock = _restock(client, item_payload)
    item_url = f"/api/items/{original['id']}"
    restock_url = f"/api/restock/{restock['id']}"

    responses = (
        client.post("/api/items", json={**item_payload, **dates}),
        client.patch(item_url, json=dates),
        client.post(f"{restock_url}/done", json={
            "purchased_quantity": 12, "owner": "Alex", "location": "Pantry",
            "purchase_date": item_payload["purchase_date"], **dates,
        }),
        client.post("/api/intake/confirm", json={"items": [{
            **item_payload, **dates, "temporary_id": "cand_00000001",
        }]}),
    )

    for response in responses:
        assert response.status_code == 422, response.text
        assert response.json()["code"] == code
    assert db_session.query(Item).count() == 1
    assert client.get(item_url).json() == original
    assert client.get(restock_url).json() == restock


def test_create_with_default_purchase_date_accepts_already_expired_item(
    client, item_payload,
):
    del item_payload["purchase_date"]
    item = _post_created(
        client, "/api/items", {**item_payload, "unopened_expiration_date": YESTERDAY},
    )
    assert item["purchase_date"] == TODAY.isoformat()
    assert item["status"] == "expired"

    url = f"/api/items/{item['id']}"
    assert client.patch(url, json={"notes": "Already expired"}).status_code == 200
    response = client.patch(url, json={"purchase_date": TODAY.isoformat()})
    assert response.status_code == 422
    assert response.json()["code"] == "expiration_before_purchase"


def test_patch_clears_opened_expiration_when_opened_date_is_cleared(client, item_payload):
    item = _post_created(client, "/api/items", {
        **item_payload, "opened_date": "2026-11-21", "opened_expiration_date": YESTERDAY,
    })
    url = f"/api/items/{item['id']}"
    assert item["current_expiration_date"] == YESTERDAY

    response = client.patch(url, json={"opened_date": None})
    assert response.status_code == 200, response.text
    assert response.json()["opened_expiration_date"] is None
    assert response.json()["current_expiration_date"] == "infinite"
    reopened = client.patch(url, json={"opened_date": TODAY.isoformat()})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["current_expiration_date"] == "infinite"


def test_restock_done_resolves_each_field_and_defaults_purchase_date(
    client, db_session, item_payload,
):
    original = _post_created(client, "/api/items", item_payload)
    restock = _restock(client, item_payload, source_item_id=original["id"])
    response = client.post(f"/api/restock/{restock['id']}/done", json={
        "purchased_quantity": 12, "owner": " Jamie ", "location": "  ",
        "unopened_expiration_date": YESTERDAY,
    })
    assert response.status_code == 200, response.text
    purchased = db_session.query(Item).filter(Item.id != original["id"]).one()
    assert (purchased.owner, purchased.location) == ("Jamie", item_payload["location"])
    assert purchased.purchase_date == TODAY.isoformat()
    assert _status_and_expiration(purchased) == (YESTERDAY, "expired")


@pytest.mark.parametrize("field", ["owner", "location"])
def test_restock_done_requires_values_without_source(client, db_session, item_payload, field):
    restock = _restock(client, item_payload)
    url = f"/api/restock/{restock['id']}"
    payload = {"purchased_quantity": 12, "owner": "Alex", "location": "Pantry", field: " "}

    response = client.post(f"{url}/done", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "restock_item_invalid"
    assert response.json()["params"]["field"] == field
    assert db_session.query(Item).count() == 0
    assert client.get(url).json() == restock


@pytest.mark.parametrize("entry_point", ["recommendations", "preview", "explore"])
def test_recipe_inventory_excludes_stale_active_item(
    client, db_session, monkeypatch, item_payload, entry_point,
):
    today = TODAY - timedelta(days=4)
    monkeypatch.setattr("stock_manager.api.services.household_today", lambda db: today)
    item = _post_created(
        client, "/api/items", {**item_payload, "unopened_expiration_date": YESTERDAY},
    )
    recipe = _post_created(client, "/api/recipes", {
        "title": "Tomato soup", "category": "soup",
        "ingredients": [{"ingredient_name": item["name"], "quantity": "1", "unit": "pcs"}],
    })
    assert item["status"] == "active"

    # Yesterday the persisted status was still active because no inventory read refreshed it.
    today = TODAY - timedelta(days=1)
    assert db_session.get(Item, item["id"]).status == "active"
    today = TODAY

    if entry_point == "recommendations":
        response = client.get("/api/recipes/recommendations")
        assert response.status_code == 200, response.text
        suggestion, = response.json()["recommendations"]
        assert suggestion["recipe_id"] == recipe["id"]
        assert suggestion["matched_inventory_items"] == []
        assert suggestion["missing_ingredients"] == [item["name"]]
    elif entry_point == "preview":
        response = client.get(f"/api/recipes/{recipe['id']}/consume-preview")
        assert response.status_code == 200, response.text
        assert response.json()["suggestions"] == []
        assert response.json()["unmatched_ingredients"] == [item["name"]]
    else:
        inventory, rejected, _ = _load_explore_inventory(db_session, [item["id"]])
        assert inventory == []
        assert rejected == [item["id"]]

    assert db_session.get(Item, item["id"]).status == "expired"


@pytest.mark.parametrize(("quantity", "expiration", "warning_days"), [
    (0, "infinite", 2),
    (0, YESTERDAY, 2),
    (-1, "infinite", 2),
    (2, "infinite", 2),
    (2, YESTERDAY, 2),
    (2, TODAY.isoformat(), 0),
    (2, "2026-11-26", 2),
    (2, "2026-11-27", 2),
])
def test_bulk_statuses_match_single_item_calculation(
    db_session, item_payload, quantity, expiration, warning_days,
):
    expected = _calculate_status(quantity, expiration, warning_days, TODAY)
    previous = "expired" if expected == "active" else "active"
    item = Item(**make_item_model_data(
        category_id=item_payload["category_id"],
        quantity_value=quantity,
        current_expiration_date=expiration,
        status=previous,
    ))
    db_session.add_all([item, Setting(key="expiration_reminder_days", value=str(warning_days))])
    db_session.commit()

    assert refresh_item_statuses(db_session) == 1
    assert item.status == expected
    assert refresh_item_statuses(db_session) == 0


@pytest.mark.parametrize(
    ("change", "expected_status"),
    [({"expiration_reminder_days": 5}, "expiring soon"), ({"default_timezone": "UTC"}, "expired")],
)
def test_settings_change_refreshes_stored_statuses(
    client, db_session, monkeypatch, item_payload, change, expected_status,
):
    def household_today(db):
        return TODAY + timedelta(days=5) if db.get(Setting, "default_timezone") else TODAY

    monkeypatch.setattr("stock_manager.api.services.household_today", household_today)
    item = _post_created(
        client, "/api/items", {**item_payload, "unopened_expiration_date": "2026-11-28"},
    )
    assert item["status"] == "active"

    response = client.patch("/api/settings", json=change)

    assert response.status_code == 200, response.text
    assert db_session.get(Item, item["id"]).status == expected_status

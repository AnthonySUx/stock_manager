"""Issue #40: restrict destructive bulk cleanup and CORS.

- POST /api/items/clean only deletes finished stock (consumed / expired)
- POST /api/restock/clean only deletes done restock items
- CORS only allows the configured browser origins, without credentials
"""

from datetime import date, timedelta

import pytest

from stock_manager.api.category_services import get_category_by_slug
from tests.helpers import make_item_create_payload, make_restock_create_payload


def _create_item(client, db_session, name, quantity=2):
    future = (date.today() + timedelta(days=60)).isoformat()
    response = client.post("/api/items", json=make_item_create_payload(
        name=name,
        category_id=get_category_by_slug(db_session, "dairy").id,
        quantity_value=quantity,
        unopened_expiration_date=future,
        current_expiration_date=future,
    ))
    assert response.status_code == 201, response.text
    return response.json()


def _item_ids(client):
    return {i["id"] for i in client.get("/api/items").json()}


class TestItemClean:
    @pytest.mark.parametrize("statuses", [
        ["active"],
        ["expiring soon"],
        ["consumed", "active"],
    ])
    def test_rejects_live_stock_statuses(self, client, db_session, statuses):
        item = _create_item(client, db_session, "牛奶")

        response = client.post("/api/items/clean", params={"statuses": statuses})

        assert response.status_code == 400
        assert item["id"] in _item_ids(client)

    def test_default_cleans_consumed_and_keeps_active(self, client, db_session):
        active = _create_item(client, db_session, "牛奶")
        used_up = _create_item(client, db_session, "酸奶", quantity=1)
        consume = client.post(f"/api/items/{used_up['id']}/consume",
                              json={"quantity": 1, "add_to_restock": False})
        assert consume.json()["status"] == "consumed"

        response = client.post("/api/items/clean")

        assert response.status_code == 200
        ids = _item_ids(client)
        assert active["id"] in ids
        assert used_up["id"] not in ids

    def test_expired_is_allowed(self, client, db_session):
        response = client.post("/api/items/clean", params={"statuses": ["expired"]})
        assert response.status_code == 200


class TestRestockClean:
    def test_rejects_pending(self, client):
        created = client.post("/api/restock", json=make_restock_create_payload()).json()

        response = client.post("/api/restock/clean", params={"status": "pending"})

        assert response.status_code == 400
        ids = {r["id"] for r in client.get("/api/restock").json()}
        assert created["id"] in ids


class TestCors:
    def _preflight(self, client, origin):
        return client.options("/api/items", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        })

    def test_allowed_origin_without_credentials(self, client):
        response = self._preflight(client, "http://localhost:8081")
        assert response.headers.get("access-control-allow-origin") == "http://localhost:8081"
        assert "access-control-allow-credentials" not in response.headers

    def test_unknown_origin_is_not_allowed(self, client):
        response = self._preflight(client, "http://evil.example")
        assert "access-control-allow-origin" not in response.headers

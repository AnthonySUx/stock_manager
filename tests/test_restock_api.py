"""Restock items REST API tests.

Tests only cover routes currently present on the main branch:
    GET    /api/restock
    GET    /api/restock/{item_id}
    POST   /api/restock
    PATCH  /api/restock/{item_id}
    POST   /api/restock/{item_id}/done
    DELETE /api/restock/{item_id}
    POST   /api/restock/clean

The following are NOT tested here (not on main branch yet):
    GET  /api/restock/duplicates
    POST /api/restock/{id}/shopping-check
    POST /api/restock/{id}/shopping-uncheck
"""

from datetime import date, timedelta

from tests.helpers import make_restock_create_payload


class TestCreateRestockItem:
    def test_create_restock_item_success(self, client):
        """POST /api/restock with valid data returns 201."""
        payload = make_restock_create_payload()

        response = client.post("/api/restock", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "鸡蛋"
        assert data["quantity_value"] == 12
        assert data["status"] == "pending"
        assert "id" in data


class TestListRestockItems:
    def test_list_restock_items(self, client):
        """GET /api/restock returns all restock items."""
        client.post("/api/restock", json=make_restock_create_payload(name="鸡蛋"))

        response = client.get("/api/restock")

        assert response.status_code == 200
        names = [item["name"] for item in response.json()]
        assert "鸡蛋" in names

    def test_list_restock_items_filter_by_status(self, client):
        """GET /api/restock?status=pending filters correctly."""
        # Create a pending item
        client.post("/api/restock", json=make_restock_create_payload(name="鸡蛋"))

        response = client.get("/api/restock", params={"status": "pending"})

        assert response.status_code == 200
        assert all(item["status"] == "pending" for item in response.json())


class TestGetRestockItem:
    def test_get_restock_item_by_id(self, client):
        """GET /api/restock/{id} returns the item."""
        created = client.post(
            "/api/restock", json=make_restock_create_payload()
        ).json()

        response = client.get(f"/api/restock/{created['id']}")

        assert response.status_code == 200
        assert response.json()["name"] == created["name"]

    def test_get_restock_item_not_found(self, client):
        """GET /api/restock/{id} with non-existing id returns 404."""
        response = client.get("/api/restock/999999")

        assert response.status_code == 404


class TestUpdateRestockItem:
    def test_update_restock_item(self, client):
        """PATCH /api/restock/{id} updates fields."""
        created = client.post(
            "/api/restock", json=make_restock_create_payload()
        ).json()

        response = client.patch(
            f"/api/restock/{created['id']}",
            json={"quantity_value": 24, "notes": "多买一点"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["quantity_value"] == 24
        assert data["notes"] == "多买一点"


class TestDoneRestockItem:
    def test_done_restock_item_adds_to_stock(self, client):
        """POST /api/restock/{id}/done marks done and adds to stock."""
        created = client.post(
            "/api/restock", json=make_restock_create_payload(quantity_value=12)
        ).json()

        response = client.post(
            f"/api/restock/{created['id']}/done",
            json={
                "purchased_quantity": 12,
                "owner": "me",
                "purchase_date": date.today().isoformat(),
                "location": "冰箱",
                "unopened_expiration_date": (
                    (date.today() + timedelta(days=30)).isoformat()
                ),
            },
        )

        assert response.status_code == 200
        assert "message" in response.json()

        # Verify item appears in stock
        stock_response = client.get("/api/items")
        names = [item["name"] for item in stock_response.json()]
        assert "鸡蛋" in names

        # Verify restock item is marked done
        get_response = client.get(f"/api/restock/{created['id']}")
        assert get_response.json()["status"] == "done"

    def test_partial_done_restock_item(self, client):
        """POST /api/restock/{id}/done with partial purchase keeps rest as pending."""
        created = client.post(
            "/api/restock", json=make_restock_create_payload(quantity_value=12)
        ).json()

        response = client.post(
            f"/api/restock/{created['id']}/done",
            json={
                "purchased_quantity": 5,
                "owner": "me",
                "purchase_date": date.today().isoformat(),
                "location": "冰箱",
                "unopened_expiration_date": (
                    (date.today() + timedelta(days=30)).isoformat()
                ),
            },
        )

        assert response.status_code == 200

        # Stock should have quantity=5
        stock_response = client.get("/api/items")
        names = [item["name"] for item in stock_response.json() if item["name"] == "鸡蛋"]
        assert any(item["quantity_value"] == 5 for item in stock_response.json())

        # Original restock item should still be pending with remaining quantity
        get_response = client.get(f"/api/restock/{created['id']}")
        assert get_response.json()["status"] == "pending"
        assert get_response.json()["quantity_value"] == 7


class TestCleanRestockItems:
    def test_clean_done_restock_items(self, client):
        """POST /api/restock/clean removes done restock items."""
        # Create and mark as done
        created = client.post(
            "/api/restock", json=make_restock_create_payload(quantity_value=1)
        ).json()

        client.post(
            f"/api/restock/{created['id']}/done",
            json={
                "purchased_quantity": 1,
                "owner": "me",
                "purchase_date": date.today().isoformat(),
                "location": "冰箱",
                "unopened_expiration_date": (
                    (date.today() + timedelta(days=30)).isoformat()
                ),
            },
        )

        # Clean done items
        response = client.post("/api/restock/clean", params={"status": "done"})

        assert response.status_code == 200
        assert "message" in response.json()

        # Verify removed from list
        list_response = client.get("/api/restock")
        restock_ids = [item["id"] for item in list_response.json()]
        assert created["id"] not in restock_ids


class TestDeleteRestockItem:
    def test_delete_restock_item(self, client):
        """DELETE /api/restock/{id} removes the item."""
        created = client.post(
            "/api/restock", json=make_restock_create_payload()
        ).json()

        response = client.delete(f"/api/restock/{created['id']}")

        assert response.status_code == 200

        # Verify 404 on re-fetch
        missing = client.get(f"/api/restock/{created['id']}")
        assert missing.status_code == 404

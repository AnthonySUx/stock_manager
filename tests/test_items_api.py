"""Stock items REST API tests."""

from tests.helpers import make_item_create_payload

def _cat_id(db_session, slug):
    """Helper to get category ID by slug."""
    from stock_manager.api.category_services import get_category_by_slug
    cat = get_category_by_slug(db_session, slug)
    return cat.id if cat else None



class TestCreateItem:
    def test_create_item_success(self, client, db_session):
        """POST /api/items with valid data returns 201."""
        payload = make_item_create_payload(category_id=_cat_id(db_session, "dairy"))

        response = client.post("/api/items", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "牛奶"
        assert data["quantity_value"] == 2
        assert data["quantity_unit"] == "瓶"
        assert "id" in data

    def test_create_item_missing_required_fields(self, client):
        """POST /api/items with empty body returns 422."""
        response = client.post("/api/items", json={})

        assert response.status_code == 422


class TestListItems:
    def test_list_items(self, client, db_session):
        """GET /api/items returns all created items."""
        client.post("/api/items", json=make_item_create_payload(category_id=_cat_id(db_session, "dairy"), name="牛奶"))
        client.post("/api/items", json=make_item_create_payload(category_id=_cat_id(db_session, "eggs"), name="鸡蛋"))

        response = client.get("/api/items")

        assert response.status_code == 200
        names = [item["name"] for item in response.json()]
        assert "牛奶" in names
        assert "鸡蛋" in names


class TestGetItem:
    def test_get_item_by_id(self, client, db_session):
        """GET /api/items/{id} returns the item."""
        created = client.post(
            "/api/items", json=make_item_create_payload(category_id=_cat_id(db_session, "dairy"))
        ).json()

        response = client.get(f"/api/items/{created['id']}")

        assert response.status_code == 200
        assert response.json()["name"] == created["name"]

    def test_get_item_not_found(self, client):
        """GET /api/items/{id} with non-existing id returns 404."""
        response = client.get("/api/items/999999")

        assert response.status_code == 404


class TestUpdateItem:
    def test_update_item(self, client, db_session):
        """PATCH /api/items/{id} updates fields."""
        created = client.post(
            "/api/items", json=make_item_create_payload(category_id=_cat_id(db_session, "dairy"))
        ).json()

        response = client.patch(
            f"/api/items/{created['id']}",
            json={"quantity_value": 5, "location": "储物柜"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["quantity_value"] == 5
        assert data["location"] == "储物柜"


class TestConsumeItem:
    def test_consume_item_reduces_quantity(self, client, db_session):
        """POST /api/items/{id}/consume deducts quantity."""
        created = client.post(
            "/api/items", json=make_item_create_payload(category_id=_cat_id(db_session, "dairy"), quantity_value=3)
        ).json()

        response = client.post(
            f"/api/items/{created['id']}/consume",
            json={"quantity": 1, "add_to_restock": False},
        )

        assert response.status_code == 200
        assert response.json()["quantity_value"] == 2

    def test_consume_to_zero_adds_restock(self, client, db_session):
        """Consuming all quantity with add_to_restock=True creates restock item."""
        created = client.post(
            "/api/items",
            json=make_item_create_payload(category_id=_cat_id(db_session, "dairy"), name="牛奶", quantity_value=1),
        ).json()

        response = client.post(
            f"/api/items/{created['id']}/consume",
            json={"quantity": 1, "add_to_restock": True},
        )

        assert response.status_code == 200
        assert response.json()["quantity_value"] == 0

        # Verify restock item was created
        restock_response = client.get("/api/restock")
        names = [item["name"] for item in restock_response.json()]
        assert "牛奶" in names


class TestDeleteItem:
    def test_delete_item(self, client, db_session):
        """DELETE /api/items/{id} removes the item."""
        created = client.post(
            "/api/items", json=make_item_create_payload(category_id=_cat_id(db_session, "dairy"))
        ).json()

        response = client.delete(f"/api/items/{created['id']}")

        assert response.status_code == 200

        # Verify 404 on re-fetch
        missing = client.get(f"/api/items/{created['id']}")
        assert missing.status_code == 404

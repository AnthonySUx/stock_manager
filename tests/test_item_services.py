"""Stock item service-level tests (no HTTP)."""

from datetime import date, timedelta


def _cat_id(db_session, slug):
    """Helper to get category ID by slug."""
    from stock_manager.api.category_services import get_category_by_slug
    cat = get_category_by_slug(db_session, slug)
    return cat.id if cat else None


from tests.helpers import make_item_model_data


class TestCreateAndGetItem:
    def test_create_item(self, db_session):
        """create_item returns a persisted Item with an id."""
        from stock_manager.api.services import create_item, get_item

        model = make_item_model_data(category_id=_cat_id(db_session, "dairy"))
        item = create_item(db_session, model)

        assert item.id is not None
        assert item.name == "牛奶"

        found = get_item(db_session, item.id)
        assert found is not None
        assert found.name == item.name

    def test_get_item_not_found(self, db_session):
        """get_item returns None for non-existing id."""
        from stock_manager.api.services import get_item

        assert get_item(db_session, 999999) is None


class TestUpdateItem:
    def test_update_item(self, db_session):
        """update_item modifies fields and returns the updated item."""
        from stock_manager.api.services import create_item, update_item

        item = create_item(db_session, make_item_model_data(category_id=_cat_id(db_session, "dairy")))

        updated = update_item(
            db_session, item.id, {"quantity_value": 5, "location": "储物柜"}
        )

        assert updated is not None
        assert updated.quantity_value == 5
        assert updated.location == "储物柜"

    def test_update_item_not_found(self, db_session):
        """update_item returns None for non-existing id."""
        from stock_manager.api.services import update_item

        assert update_item(db_session, 999999, {"name": "x"}) is None


class TestConsumeItem:
    def test_consume_reduces_quantity(self, db_session):
        """consume_item deducts the specified quantity."""
        from stock_manager.api.services import consume_item, create_item

        item = create_item(db_session, make_item_model_data(category_id=_cat_id(db_session, "dairy"), quantity_value=3))

        result = consume_item(db_session, item.id, quantity=1)

        assert result["item"].quantity_value == 2

    def test_consume_to_zero(self, db_session):
        """consume_item to zero sets status to consumed."""
        from stock_manager.api.services import consume_item, create_item

        item = create_item(db_session, make_item_model_data(category_id=_cat_id(db_session, "dairy"), quantity_value=1))

        result = consume_item(db_session, item.id, quantity=1)

        assert result["item"].quantity_value == 0
        assert result["item"].status == "consumed"

    def test_consume_to_zero_creates_restock(self, db_session):
        """consume_item with add_to_restock=True creates a restock item."""
        from stock_manager.api.services import consume_item, create_item

        item = create_item(
            db_session, make_item_model_data(category_id=_cat_id(db_session, "dairy"), name="牛奶", quantity_value=1)
        )

        result = consume_item(db_session, item.id, quantity=1, add_to_restock=True)

        assert result["restock_item"] is not None
        assert result["restock_item"].name == "牛奶"
        assert result["restock_item"].status == "pending"


class TestDeleteItem:
    def test_delete_item(self, db_session):
        """delete_item removes an existing item and returns True."""
        from stock_manager.api.services import create_item, delete_item, get_item

        item = create_item(db_session, make_item_model_data(category_id=_cat_id(db_session, "dairy")))

        assert delete_item(db_session, item.id) is True
        assert get_item(db_session, item.id) is None

    def test_delete_item_not_found(self, db_session):
        """delete_item returns False for non-existing id."""
        from stock_manager.api.services import delete_item

        assert delete_item(db_session, 999999) is False


class TestCalculateItemStatus:
    def test_consumed_status(self, db_session):
        """quantity <= 0 should produce consumed status."""
        from stock_manager.api.services import calculate_item_status

        status = calculate_item_status(0, "infinite", db_session)
        assert status == "consumed"

    def test_expired_status(self, db_session):
        """Past expiration date should produce expired status."""
        from stock_manager.api.services import calculate_item_status

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        status = calculate_item_status(1, yesterday, db_session)
        assert status == "expired"

    def test_expiring_soon_status(self, db_session):
        """Expiration within warning days should produce expiring soon."""
        from stock_manager.api.services import calculate_item_status

        # Default expiration_reminder_days is 2
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        status = calculate_item_status(1, tomorrow, db_session)
        assert status == "expiring soon"

    def test_active_status(self, db_session):
        """Infinite expiration date with positive quantity should be active."""
        from stock_manager.api.services import calculate_item_status

        status = calculate_item_status(1, "infinite", db_session)
        assert status == "active"

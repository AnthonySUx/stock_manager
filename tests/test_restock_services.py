"""Restock item service-level tests (no HTTP).

Tests only cover functions currently present on the main branch:
    create_restock_item
    get_restock_item
    get_restock_items
    update_restock_item
    mark_restock_item_done
    update_restock_item_quantity
    delete_restock_item
    delete_restock_items_by_status

The following are NOT tested here (not on main branch yet):
    shopping_check_restock_item
    shopping_uncheck_restock_item
    find_restock_duplicates
"""

from tests.helpers import make_restock_model_data


class TestCreateAndGetRestockItem:
    def test_create_restock_item(self, db_session):
        """create_restock_item returns a persisted RestockItem."""
        from stock_manager.api.services import create_restock_item, get_restock_item

        data = make_restock_model_data()
        item = create_restock_item(db_session, data)

        assert item.id is not None
        assert item.name == "鸡蛋"
        assert item.status == "pending"

        found = get_restock_item(db_session, item.id)
        assert found is not None
        assert found.name == item.name

    def test_get_restock_item_not_found(self, db_session):
        """get_restock_item returns None for non-existing id."""
        from stock_manager.api.services import get_restock_item

        assert get_restock_item(db_session, 999999) is None


class TestGetRestockItems:
    def test_list_by_status(self, db_session):
        """get_restock_items filters by status correctly."""
        from stock_manager.api.services import (
            create_restock_item,
            get_restock_items,
            mark_restock_item_done,
        )

        pending_item = create_restock_item(
            db_session, make_restock_model_data(name="鸡蛋")
        )
        done_item = create_restock_item(
            db_session, make_restock_model_data(name="牛奶")
        )
        mark_restock_item_done(db_session, done_item.id)

        pending_list = get_restock_items(db_session, status="pending")
        done_list = get_restock_items(db_session, status="done")

        assert all(item.status == "pending" for item in pending_list)
        assert pending_item.id in {item.id for item in pending_list}

        assert all(item.status == "done" for item in done_list)
        assert done_item.id in {item.id for item in done_list}


class TestUpdateRestockItem:
    def test_update_restock_item(self, db_session):
        """update_restock_item modifies fields."""
        from stock_manager.api.services import (
            create_restock_item,
            update_restock_item,
        )

        item = create_restock_item(db_session, make_restock_model_data())

        updated = update_restock_item(
            db_session, item.id, {"quantity_value": 24, "notes": "多买一点"}
        )

        assert updated is not None
        assert updated.quantity_value == 24
        assert updated.notes == "多买一点"

    def test_update_restock_item_not_found(self, db_session):
        """update_restock_item returns None for non-existing id."""
        from stock_manager.api.services import update_restock_item

        assert update_restock_item(db_session, 999999, {"name": "x"}) is None


class TestMarkRestockItemDone:
    def test_mark_done(self, db_session):
        """mark_restock_item_done sets status to done and returns True."""
        from stock_manager.api.services import (
            create_restock_item,
            mark_restock_item_done,
        )

        item = create_restock_item(db_session, make_restock_model_data())

        result = mark_restock_item_done(db_session, item.id)

        assert result is True
        assert item.status == "done"
        assert item.done_at is not None

    def test_mark_done_twice_returns_false(self, db_session):
        """mark_restock_item_done on already-done item returns False."""
        from stock_manager.api.services import (
            create_restock_item,
            mark_restock_item_done,
        )

        item = create_restock_item(db_session, make_restock_model_data())
        mark_restock_item_done(db_session, item.id)

        result = mark_restock_item_done(db_session, item.id)

        assert result is False

    def test_mark_done_not_found(self, db_session):
        """mark_restock_item_done on non-existing id returns False."""
        from stock_manager.api.services import mark_restock_item_done

        assert mark_restock_item_done(db_session, 999999) is False


class TestUpdateRestockItemQuantity:
    def test_update_quantity(self, db_session):
        """update_restock_item_quantity updates quantity for pending items."""
        from stock_manager.api.services import (
            create_restock_item,
            get_restock_item,
            update_restock_item_quantity,
        )

        item = create_restock_item(db_session, make_restock_model_data(quantity_value=12))

        result = update_restock_item_quantity(db_session, item.id, 7)

        assert result is True
        assert get_restock_item(db_session, item.id).quantity_value == 7

    def test_update_quantity_not_found(self, db_session):
        """update_restock_item_quantity returns False for non-existing id."""
        from stock_manager.api.services import update_restock_item_quantity

        assert update_restock_item_quantity(db_session, 999999, 5) is False

    def test_update_quantity_on_done_returns_false(self, db_session):
        """update_restock_item_quantity returns False for done items."""
        from stock_manager.api.services import (
            create_restock_item,
            mark_restock_item_done,
            update_restock_item_quantity,
        )

        item = create_restock_item(db_session, make_restock_model_data())
        mark_restock_item_done(db_session, item.id)

        result = update_restock_item_quantity(db_session, item.id, 5)

        assert result is False


class TestDeleteRestockItem:
    def test_delete_restock_item(self, db_session):
        """delete_restock_item removes an existing item."""
        from stock_manager.api.services import (
            create_restock_item,
            delete_restock_item,
            get_restock_item,
        )

        item = create_restock_item(db_session, make_restock_model_data())

        assert delete_restock_item(db_session, item.id) is True
        assert get_restock_item(db_session, item.id) is None

    def test_delete_restock_item_not_found(self, db_session):
        """delete_restock_item returns False for non-existing id."""
        from stock_manager.api.services import delete_restock_item

        assert delete_restock_item(db_session, 999999) is False


class TestDeleteRestockItemsByStatus:
    def test_clean_by_status(self, db_session):
        """delete_restock_items_by_status removes only matching items."""
        from stock_manager.api.services import (
            create_restock_item,
            delete_restock_items_by_status,
            get_restock_items,
            mark_restock_item_done,
        )

        pending_item = create_restock_item(
            db_session, make_restock_model_data(name="鸡蛋")
        )
        done_item = create_restock_item(
            db_session, make_restock_model_data(name="牛奶")
        )
        done_item_id = done_item.id
        mark_restock_item_done(db_session, done_item.id)

        deleted_count = delete_restock_items_by_status(db_session, "done")

        assert deleted_count == 1

        remaining = get_restock_items(db_session)
        remaining_ids = {item.id for item in remaining}
        assert pending_item.id in remaining_ids
        assert done_item_id not in remaining_ids

    def test_clean_no_match(self, db_session):
        """delete_restock_items_by_status returns 0 when no items match."""
        from stock_manager.api.services import delete_restock_items_by_status

        count = delete_restock_items_by_status(db_session, "nonexistent")

        assert count == 0

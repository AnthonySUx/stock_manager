"""Issue #42: POST /api/restock/{id}/done is idempotent and atomic."""

from datetime import date, timedelta

import pytest

from stock_manager.api.models import Item, RestockItem
from tests.helpers import make_restock_create_payload


def _cat_id(db_session, slug):
    from stock_manager.api.category_services import get_category_by_slug
    return get_category_by_slug(db_session, slug).id


def _done_payload(db_session, quantity):
    return {
        "purchased_quantity": quantity,
        "owner": "me",
        "purchase_date": date.today().isoformat(),
        "location": "冰箱",
        "unopened_expiration_date": (date.today() + timedelta(days=30)).isoformat(),
        "category_id": _cat_id(db_session, "dairy"),
    }


def _stock_count(db_session, name="鸡蛋"):
    db_session.expire_all()
    return db_session.query(Item).filter(Item.name == name).count()


def _create_restock(client, quantity=12):
    return client.post(
        "/api/restock", json=make_restock_create_payload(quantity_value=quantity)
    ).json()


class TestDoneIsIdempotent:
    def test_repeated_done_creates_one_stock_item(self, client, db_session):
        created = _create_restock(client)
        url = f"/api/restock/{created['id']}/done"
        payload = _done_payload(db_session, 12)

        codes = [client.post(url, json=payload).status_code for _ in range(3)]

        assert codes == [200, 409, 409]
        assert _stock_count(db_session) == 1
        assert client.get(f"/api/restock/{created['id']}").json()["status"] == "done"

    def test_409_detail(self, client, db_session):
        created = _create_restock(client)
        url = f"/api/restock/{created['id']}/done"
        client.post(url, json=_done_payload(db_session, 12))

        response = client.post(url, json=_done_payload(db_session, 12))
        assert response.status_code == 409
        assert response.json()["detail"] == "Restock item is already done"

    def test_partial_then_rest_then_409(self, client, db_session):
        """Partial purchases stay allowed until the item is done."""
        created = _create_restock(client)
        url = f"/api/restock/{created['id']}/done"

        assert client.post(url, json=_done_payload(db_session, 5)).status_code == 200
        pending = client.get(f"/api/restock/{created['id']}").json()
        assert (pending["status"], pending["quantity_value"]) == ("pending", 7)

        assert client.post(url, json=_done_payload(db_session, 7)).status_code == 200
        assert client.get(f"/api/restock/{created['id']}").json()["status"] == "done"

        assert client.post(url, json=_done_payload(db_session, 1)).status_code == 409
        assert _stock_count(db_session) == 2


class TestDoneIsAtomic:
    def test_stock_failure_leaves_restock_untouched(self, client, db_session, monkeypatch):
        """If creating the stock item fails, the restock update is rolled back."""
        created = _create_restock(client)

        def broken_item(**_kwargs):
            raise RuntimeError("simulated stock insert failure")

        monkeypatch.setattr("stock_manager.api.services.Item", broken_item)
        with pytest.raises(RuntimeError, match="simulated"):
            client.post(
                f"/api/restock/{created['id']}/done", json=_done_payload(db_session, 12)
            )
        monkeypatch.undo()

        db_session.expire_all()
        restock = db_session.get(RestockItem, created["id"])
        assert restock.status == "pending"
        assert restock.quantity_value == 12
        assert restock.done_at is None
        assert _stock_count(db_session) == 0

    def test_stale_read_is_rejected(self, db_session):
        """A restock row changed after it was read is not completed twice."""
        from stock_manager.api.services import (
            RestockAlreadyDoneError,
            complete_restock_purchase,
            create_restock_item,
        )

        restock = create_restock_item(
            db_session, {"name": "鸡蛋", "quantity_value": 12, "status": "pending"}
        )
        # Another request changes the row after we read it (object stays stale).
        db_session.query(RestockItem).filter(RestockItem.id == restock.id).update(
            {RestockItem.quantity_value: 7}, synchronize_session=False
        )

        with pytest.raises(RestockAlreadyDoneError):
            complete_restock_purchase(
                db_session,
                restock,
                12,
                {"name": "鸡蛋", "purchase_date": date.today().isoformat(),
                 "category_id": _cat_id(db_session, "dairy"),
                 "current_expiration_date": "infinite", "status": "active"},
            )
        assert _stock_count(db_session) == 0

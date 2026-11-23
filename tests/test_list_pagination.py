"""Stock and restock pagination contracts (#102)."""

import pytest

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.models import Item, RestockItem
from tests.helpers import make_item_model_data


@pytest.fixture(params=["items", "restock"])
def listing(request, db_session):
    category_id = get_category_by_slug(db_session, "vegetables").id
    if request.param == "items":
        rows = [
            Item(**make_item_model_data(category_id=category_id, current_expiration_date="infinite"))
            for _ in range(105)
        ]
    else:
        rows = [
            RestockItem(
                name=f"Restock {i}", category_id=category_id, status="pending" if i % 2 else "done",
            )
            for i in range(105)
        ]
    db_session.add_all(rows)
    db_session.commit()
    if request.param == "restock":
        rows.sort(key=lambda row: (row.status == "done", row.id))
    return f"/api/{request.param}", [row.id for row in rows]


def test_list_paging_retains_order_and_supports_offset_without_limit(client, listing):
    url, ids = listing
    for params, expected in (
        ({}, ids),
        ({"limit": 100}, ids[:100]),
        ({"limit": 100, "offset": 100}, ids[100:]),
        ({"offset": 20}, ids[20:]),
        ({"limit": 1, "offset": 42}, ids[42:43]),
        ({"offset": 106}, []),
    ):
        response = client.get(url, params=params)
        assert response.status_code == 200, response.text
        assert [row["id"] for row in response.json()] == expected


def test_list_rejects_invalid_page_parameters(client, listing):
    url, _ = listing
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert client.get(url, params=params).status_code == 422


def test_item_status_refresh_and_filter_run_before_paging(client, db_session):
    category_id = get_category_by_slug(db_session, "vegetables").id
    expired = Item(**make_item_model_data(
        category_id=category_id, current_expiration_date="2000-01-01", status="active",
    ))
    available = Item(**make_item_model_data(
        category_id=category_id, current_expiration_date="infinite", status="expired",
    ))
    db_session.add_all([expired, available])
    db_session.commit()

    response = client.get("/api/items", params={"status": "active", "limit": 1})

    assert response.status_code == 200, response.text
    assert [(row["id"], row["status"]) for row in response.json()] == [(available.id, "active")]
    assert expired.status == "expired"

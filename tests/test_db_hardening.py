"""Exact stock amounts, UTC connection setup, and idempotent favorites (#101)."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.db import _set_mysql_utc, engine
from stock_manager.api.models import Base, Item, Recipe, RecipeFavorite, RecipeUsageHistory
from stock_manager.api.recipe_services import add_favorite
from tests.helpers import make_item_create_payload, make_restock_create_payload


def _created(client, url, payload):
    response = client.post(url, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_twenty_fractional_deductions_reach_exact_zero(client, db_session):
    category_id = get_category_by_slug(db_session, "vegetables").id
    item = _created(client, "/api/items", make_item_create_payload(
        category_id=category_id, quantity_value=2,
    ))
    url = f"/api/items/{item['id']}/consume"

    for step in range(1, 21):
        response = client.post(url, json={"quantity": 0.1, "add_to_restock": step == 20})
        assert response.status_code == 200, response.text
        assert response.json()["quantity_value"] == (20 - step) / 10

    stored = db_session.get(Item, item["id"])
    assert isinstance(stored.quantity_value, Decimal)
    assert (stored.quantity_value, stored.status) == (Decimal("0"), "consumed")
    assert response.json()["restock_item"]["quantity_value"] == 0.1


def test_list_items_serializes_decimal_quantities_as_json_numbers(client, db_session):
    category_id = get_category_by_slug(db_session, "vegetables").id
    item = _created(client, "/api/items", make_item_create_payload(
        category_id=category_id, quantity_value=1.2345,
    ))

    response = client.get("/api/items")

    assert response.status_code == 200, response.text
    stored, = response.json()
    assert stored["id"] == item["id"]
    assert type(stored["quantity_value"]) is float
    assert stored["quantity_value"] == 1.235


def test_fractional_restock_purchases_use_the_exact_remaining_amount(client, db_session):
    category_id = get_category_by_slug(db_session, "vegetables").id
    restock = _created(client, "/api/restock", make_restock_create_payload(
        category_id=category_id, quantity_value=0.3,
    ))
    url = f"/api/restock/{restock['id']}"

    for remaining in (0.2, 0.1, 0.1):
        response = client.post(f"{url}/done", json={
            "purchased_quantity": 0.1, "owner": "Alex", "location": "Pantry",
        })
        assert response.status_code == 200, response.text
        current = client.get(url).json()
        assert current["quantity_value"] == remaining
    assert current["status"] == "done"
    assert [item["quantity_value"] for item in client.get("/api/items").json()] == [0.1] * 3


def test_sqlite_engine_has_no_mysql_utc_listener():
    assert engine.dialect.name == "sqlite"
    assert not event.contains(engine, "connect", _set_mysql_utc)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_favoriting_twice_creates_one_favorite_and_history_row(client, db_session):
    recipe = _created(client, "/api/recipes", {"title": "Soup", "category": "soup"})
    url = f"/api/recipes/{recipe['id']}/favorite"
    assert client.post(url).status_code == 200
    assert client.post(url).status_code == 200
    assert db_session.query(RecipeFavorite).count() == 1
    assert db_session.query(RecipeUsageHistory).filter_by(event_type="favorited").count() == 1


def test_concurrent_favorites_return_the_same_row(tmp_path):
    sqlite = create_engine(f"sqlite:///{tmp_path / 'favorites.db'}")
    session_factory = sessionmaker(bind=sqlite)
    try:
        Base.metadata.create_all(sqlite)
        with session_factory.begin() as db:
            recipe = Recipe(title="Soup", source_type="user", source_name="User")
            db.add(recipe)
            db.flush()
            recipe_id = recipe.id

        both_ready = Barrier(2)

        def favorite():
            with session_factory() as db:
                def sync(_session):
                    both_ready.wait(timeout=5)

                event.listen(db, "before_commit", sync, once=True)
                return add_favorite(db, recipe_id).id

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(favorite) for _ in range(2)]
            assert [future.result(timeout=10) for future in futures] == [1, 1]

        with session_factory() as db:
            assert db.query(RecipeFavorite).count() == 1
            assert db.query(RecipeUsageHistory).filter_by(event_type="favorited").count() == 1
    finally:
        sqlite.dispose()

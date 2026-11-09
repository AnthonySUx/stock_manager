"""Issue #43: data integrity and input validation.

The test engine enforces foreign keys (see conftest), like MySQL does.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from stock_manager.api.models import Recipe, RecipeFavorite, RecipeUsageHistory
from tests.helpers import make_item_create_payload, make_restock_create_payload


def _cat_id(db_session, slug="dairy"):
    from stock_manager.api.category_services import get_category_by_slug
    return get_category_by_slug(db_session, slug).id


def _create_item(client, db_session, **overrides):
    payload = make_item_create_payload(category_id=_cat_id(db_session), **overrides)
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_foreign_keys_are_enforced_in_tests(db_session):
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1


# ─── 1. Recipe delete with dependent rows ─────────────────────────


class TestRecipeDelete:
    def _user_recipe(self, client, title="自制菜"):
        response = client.post("/api/recipes", json={"title": title, "category": "meat_dish"})
        assert response.status_code == 201
        return response.json()["id"]

    def test_delete_favorited_and_cooked_recipe(self, client, db_session):
        recipe_id = self._user_recipe(client)
        assert client.post(f"/api/recipes/{recipe_id}/favorite").status_code == 200
        assert client.post(f"/api/recipes/{recipe_id}/cook", json={}).status_code == 200

        response = client.delete(f"/api/recipes/{recipe_id}")

        assert response.status_code == 200
        db_session.expire_all()
        assert db_session.get(Recipe, recipe_id) is None
        assert db_session.query(RecipeFavorite).filter_by(recipe_id=recipe_id).count() == 0
        assert db_session.query(RecipeUsageHistory).filter_by(recipe_id=recipe_id).count() == 0

    def test_delete_recipe_that_has_forks(self, client, db_session):
        """An AI-saved recipe can be forked and then deleted; the fork stays."""
        from stock_manager.api.recipe_schemas import RecipeCreate
        from stock_manager.api.recipe_services import create_recipe

        base_id = create_recipe(db_session, RecipeCreate(title="AI 菜", category="meat_dish"), source_type="ai_saved").id
        fork = client.post(f"/api/recipes/{base_id}/fork")
        assert fork.status_code == 200
        fork_id = fork.json()["id"]

        assert client.delete(f"/api/recipes/{base_id}").status_code == 200

        db_session.expire_all()
        remaining = db_session.get(Recipe, fork_id)
        assert remaining is not None
        assert remaining.base_recipe_id is None


# ─── 2. Restock references ────────────────────────────────────────


class TestRestockReferences:
    def test_create_with_unknown_category_is_400(self, client):
        response = client.post(
            "/api/restock", json=make_restock_create_payload(category_id=99999)
        )
        assert response.status_code == 400
        assert "Category id=99999 not found" in response.json()["detail"]

    def test_create_with_unknown_source_item_is_400(self, client):
        response = client.post(
            "/api/restock", json=make_restock_create_payload(source_item_id=99999)
        )
        assert response.status_code == 400
        assert "Source item id=99999 not found" in response.json()["detail"]

    def test_create_with_existing_references_is_201(self, client, db_session):
        item = _create_item(client, db_session)
        response = client.post(
            "/api/restock",
            json=make_restock_create_payload(
                category_id=_cat_id(db_session), source_item_id=item["id"]
            ),
        )
        assert response.status_code == 201

    def test_update_with_unknown_category_is_400(self, client):
        created = client.post("/api/restock", json=make_restock_create_payload()).json()
        response = client.patch(f"/api/restock/{created['id']}", json={"category_id": 99999})
        assert response.status_code == 400

    def test_source_item_id_must_be_positive(self, client):
        response = client.post(
            "/api/restock", json=make_restock_create_payload(source_item_id=0)
        )
        assert response.status_code == 422


# ─── 3. PATCH null on required fields ─────────────────────────────


class TestItemPatchNull:
    @pytest.mark.parametrize(
        "field",
        ["name", "category_id", "owner", "purchase_date", "quantity_value",
         "quantity_unit", "location", "unopened_expiration_date",
         "current_expiration_date", "status"],
    )
    def test_null_for_required_field_is_422(self, client, db_session, field):
        item = _create_item(client, db_session)
        response = client.patch(f"/api/items/{item['id']}", json={field: None})
        assert response.status_code == 422
        assert f"{field} cannot be null" in response.text

    @pytest.mark.parametrize("field", ["opened_date", "opened_expiration_date", "notes"])
    def test_null_for_nullable_field_is_allowed(self, client, db_session, field):
        item = _create_item(client, db_session)
        response = client.patch(f"/api/items/{item['id']}", json={field: None})
        assert response.status_code == 200
        assert response.json()[field] is None


# ─── 4. Date validation ───────────────────────────────────────────


BAD_DATES = ["2026-02-30", "2026-2-3", "20260101", "tomorrow", ""]


class TestDateValidation:
    @pytest.mark.parametrize("bad", BAD_DATES)
    def test_create_rejects_bad_purchase_date(self, client, db_session, bad):
        payload = make_item_create_payload(category_id=_cat_id(db_session), purchase_date=bad)
        assert client.post("/api/items", json=payload).status_code == 422

    @pytest.mark.parametrize("bad", BAD_DATES)
    def test_create_rejects_bad_expiration(self, client, db_session, bad):
        payload = make_item_create_payload(
            category_id=_cat_id(db_session),
            unopened_expiration_date=bad,
            current_expiration_date=bad,
        )
        assert client.post("/api/items", json=payload).status_code == 422

    def test_infinite_expiration_is_allowed(self, client, db_session):
        item = _create_item(
            client, db_session,
            unopened_expiration_date="infinite", current_expiration_date="infinite",
        )
        assert item["current_expiration_date"] == "infinite"

    def test_opened_date_cannot_be_infinite(self, client, db_session):
        payload = make_item_create_payload(
            category_id=_cat_id(db_session), opened_date="infinite"
        )
        assert client.post("/api/items", json=payload).status_code == 422

    def test_patch_rejects_bad_date(self, client, db_session):
        item = _create_item(client, db_session)
        response = client.patch(f"/api/items/{item['id']}", json={"opened_date": "2026-13-01"})
        assert response.status_code == 422

    def test_restock_done_rejects_bad_date(self, client, db_session):
        created = client.post("/api/restock", json=make_restock_create_payload()).json()
        response = client.post(
            f"/api/restock/{created['id']}/done",
            json={
                "purchased_quantity": 12,
                "category_id": _cat_id(db_session),
                "unopened_expiration_date": "2026-02-30",
            },
        )
        assert response.status_code == 422
        # Nothing changed
        assert client.get(f"/api/restock/{created['id']}").json()["status"] == "pending"

    def test_valid_dates_still_work(self, client, db_session):
        future = (date.today() + timedelta(days=10)).isoformat()
        item = _create_item(
            client, db_session,
            opened_date=date.today().isoformat(),
            opened_expiration_date=future,
        )
        assert item["current_expiration_date"] == future

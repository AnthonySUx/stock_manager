"""Issue #44: seed parent lookup and moving a subcategory to top level."""

from stock_manager.api.category_services import get_category_by_slug, seed_default_categories
from stock_manager.api.models import Category


def _id(db_session, slug):
    return get_category_by_slug(db_session, slug).id


def _create(client, name, parent_id=None):
    response = client.post("/api/categories", json={"name": name, "parent_id": parent_id})
    assert response.status_code == 201, response.text
    return response.json()


class TestSeedParentLookup:
    def test_reseed_missing_child_uses_existing_parent(self, db_session):
        food_id = _id(db_session, "food")
        db_session.delete(get_category_by_slug(db_session, "baking"))
        db_session.commit()

        seed_default_categories(db_session)

        baking = get_category_by_slug(db_session, "baking")
        assert baking is not None
        assert baking.parent_id == food_id

    def test_reseed_is_idempotent(self, db_session):
        before = db_session.query(Category).count()
        seed_default_categories(db_session)
        assert db_session.query(Category).count() == before


class TestMoveToTopLevel:
    def test_explicit_null_moves_subcategory_to_top_level(self, client, db_session):
        sub = _create(client, "自制酱料", _id(db_session, "food"))

        response = client.patch(f"/api/categories/{sub['id']}", json={"parent_id": None})

        assert response.status_code == 200
        assert response.json()["parent_id"] is None
        assert client.get(f"/api/categories/{sub['id']}").json()["parent_id"] is None

    def test_omitted_parent_id_keeps_parent(self, client, db_session):
        food_id = _id(db_session, "food")
        sub = _create(client, "自制酱料", food_id)

        response = client.patch(f"/api/categories/{sub['id']}", json={"sort_order": 5})

        assert response.status_code == 200
        assert response.json()["parent_id"] == food_id
        assert response.json()["sort_order"] == 5

    def test_move_to_another_parent_still_works(self, client, db_session):
        sub = _create(client, "自制酱料", _id(db_session, "food"))
        other_id = _id(db_session, "household")

        response = client.patch(f"/api/categories/{sub['id']}", json={"parent_id": other_id})

        assert response.status_code == 200
        assert response.json()["parent_id"] == other_id

    def test_move_to_top_level_rejects_duplicate_name(self, client, db_session):
        _create(client, "同名分类")
        sub = _create(client, "同名分类", _id(db_session, "food"))

        response = client.patch(f"/api/categories/{sub['id']}", json={"parent_id": None})

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_system_subcategory_cannot_move_to_top_level(self, client, db_session):
        response = client.patch(
            f"/api/categories/{_id(db_session, 'baking')}", json={"parent_id": None}
        )
        assert response.status_code == 400
        assert get_category_by_slug(db_session, "baking").parent_id == _id(db_session, "food")

    def test_system_category_unchanged_parent_is_allowed(self, client, db_session):
        """Sending the current parent_id is a no-op, not a parent change."""
        response = client.patch(
            f"/api/categories/{_id(db_session, 'baking')}",
            json={"parent_id": _id(db_session, "food"), "sort_order": 3},
        )
        assert response.status_code == 200
        assert response.json()["sort_order"] == 3

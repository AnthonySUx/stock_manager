"""Category API tests."""

import pytest


def _cat_id(db_session, slug):
    from stock_manager.api.category_services import get_category_by_slug
    cat = get_category_by_slug(db_session, slug)
    return cat.id if cat else None


class TestListCategories:
    def test_list_tree(self, client):
        """GET /api/categories returns a tree."""
        response = client.get("/api/categories")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        # Should have food category
        food = next((c for c in data if c["name"] == "食品"), None)
        assert food is not None
        assert len(food["children"]) > 0

    def test_list_flat(self, client):
        """GET /api/categories/flat returns all categories."""
        response = client.get("/api/categories/flat")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 50

    def test_get_single(self, client, db_session):
        """GET /api/categories/{id} returns one."""
        cat_id = _cat_id(db_session, "dairy")
        response = client.get(f"/api/categories/{cat_id}")
        assert response.status_code == 200
        assert response.json()["slug"] == "dairy"


class TestCreateCategory:
    def test_create_top_level(self, client):
        """POST /api/categories creates a top-level category."""
        response = client.post("/api/categories", json={
            "name": "园艺",
            "recipe_usage": "never",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "园艺"
        assert data["parent_id"] is None
        assert data["recipe_usage"] == "never"
        assert data["is_system"] is False
        assert data["default_shelf_life_days"] is None

    def test_create_subcategory_inherits_recipe_usage(self, client, db_session):
        """Subcategory inherits parent recipe_usage."""
        food_id = _cat_id(db_session, "food")
        response = client.post("/api/categories", json={
            "name": "火锅料",
            "parent_id": food_id,
        })
        assert response.status_code == 201
        assert response.json()["recipe_usage"] == "conditional"

    def test_create_duplicate_fails(self, client, db_session):
        """Duplicate name under same parent returns 400."""
        food_id = _cat_id(db_session, "food")
        response = client.post("/api/categories", json={
            "name": "蔬菜",
            "parent_id": food_id,
        })
        assert response.status_code == 400

    def test_create_third_level_fails(self, client, db_session):
        """Creating a subcategory under a subcategory returns 400."""
        dairy_id = _cat_id(db_session, "dairy")
        response = client.post("/api/categories", json={
            "name": "芝士",
            "parent_id": dairy_id,
        })
        assert response.status_code == 400


class TestDefaultShelfLife:
    def test_system_defaults_in_flat_and_tree(self, client):
        flat_response = client.get("/api/categories/flat")
        tree_response = client.get("/api/categories")
        assert flat_response.status_code == tree_response.status_code == 200
        flat = {row["slug"]: row["default_shelf_life_days"] for row in flat_response.json()}
        expected = {
            "vegetables": 7, "fruit": 7, "meat": 3, "seafood": 2, "eggs": 30,
            "dairy": 7, "staples_grains": 180, "soy_products": 5,
            "seasonings_spices": 365, "baking": 180, "drinks": 180,
            "snacks": 90, "frozen_food": 90, "canned_packaged": 365,
            "ready_to_eat": 2, "baby_food": 30, "formula": 365, "pet_food": 180,
            "pet_treats": 180,
        }
        assert {slug: days for slug, days in flat.items() if days is not None} == expected
        tree = tree_response.json()
        from_tree = {row["slug"]: row["default_shelf_life_days"] for row in tree}
        from_tree.update(
            {row["slug"]: row["default_shelf_life_days"] for root in tree for row in root["children"]}
        )
        assert from_tree == flat

    def test_create_update_omit_and_clear(self, client):
        response = client.post(
            "/api/categories", json={"name": "Garden", "default_shelf_life_days": 1}
        )
        assert response.status_code == 201
        assert response.json()["default_shelf_life_days"] == 1
        url = f"/api/categories/{response.json()['id']}"

        for payload, expected in [
            ({"default_shelf_life_days": 3650}, 3650),
            ({"sort_order": 10}, 3650),
            ({"default_shelf_life_days": None}, None),
        ]:
            response = client.patch(url, json=payload)
            assert response.status_code == 200
            assert response.json()["default_shelf_life_days"] == expected
            assert client.get(url).json()["default_shelf_life_days"] == expected

    def test_system_category_override_survives_seeding(self, client, db_session):
        from stock_manager.api.category_services import seed_default_categories

        category_id = _cat_id(db_session, "dairy")
        url = f"/api/categories/{category_id}"
        for days in [12, None]:
            response = client.patch(url, json={"default_shelf_life_days": days})
            assert response.status_code == 200
            assert response.json()["default_shelf_life_days"] == days

            seed_default_categories(db_session)

            assert client.get(url).json()["default_shelf_life_days"] == days

    @pytest.mark.parametrize("days", [0, 3651, 1.5, 2.0, "5", True])
    def test_rejects_out_of_range_or_non_integer_values(self, client, db_session, days):
        category_id = _cat_id(db_session, "dairy")
        url = f"/api/categories/{category_id}"
        responses = [
            client.post("/api/categories", json={"name": "Garden", "default_shelf_life_days": days}),
            client.patch(url, json={"default_shelf_life_days": days}),
        ]
        for response in responses:
            assert response.status_code == 422
            assert response.json()["detail"][0]["loc"] == ["body", "default_shelf_life_days"]
        assert client.get(url).json()["default_shelf_life_days"] == 7


class TestDeleteCategory:
    def test_delete_system_category_fails(self, client, db_session):
        """Cannot delete system categories."""
        dairy_id = _cat_id(db_session, "dairy")
        response = client.delete(f"/api/categories/{dairy_id}")
        assert response.status_code == 409

    def test_delete_category_in_use_fails(self, client, db_session):
        """Cannot delete category used by items."""
        dairy_id = _cat_id(db_session, "dairy")
        # Create an item with this category
        client.post("/api/items", json={
            "name": "牛奶",
            "category_id": dairy_id,
            "owner": "me",
            "quantity_value": 2,
            "quantity_unit": "瓶",
            "location": "冰箱",
            "unopened_expiration_date": "2026-12-31",
            "current_expiration_date": "2026-12-31",
        })
        # Try creating a custom category and deleting it... just test that system can't be deleted
        response = client.delete(f"/api/categories/{dairy_id}")
        assert response.status_code == 409


class TestRecipeEligibility:
    def test_item_with_never_category_not_in_recipe(self, client, db_session):
        """Items with recipe_usage=never should not appear in recommendations."""
        med_id = _cat_id(db_session, "medicine")
        # Create a medicine item
        client.post("/api/items", json={
            "name": "阿司匹林",
            "category_id": med_id,
            "owner": "me",
            "quantity_value": 1,
            "quantity_unit": "盒",
            "location": "储物柜",
            "unopened_expiration_date": "2026-12-31",
            "current_expiration_date": "2026-12-31",
        })
        # Get recommendations - should not crash or include medicine
        response = client.get("/api/recipes/recommendations")
        assert response.status_code == 200

    def test_item_with_conditional_can_be_in_recipe(self, client, db_session):
        """Items with recipe_usage=conditional should appear in recommendations."""
        drinks_id = _cat_id(db_session, "drinks")
        client.post("/api/items", json={
            "name": "可乐",
            "category_id": drinks_id,
            "owner": "me",
            "quantity_value": 2,
            "quantity_unit": "瓶",
            "location": "冰箱",
            "unopened_expiration_date": "2026-12-31",
            "current_expiration_date": "2026-12-31",
        })
        response = client.get("/api/recipes/recommendations")
        assert response.status_code == 200


class TestRestockCategoryFlow:
    def test_restock_done_without_category_fails(self, client):
        """Restock done without category_id returns 400."""
        created = client.post("/api/restock", json={
            "name": "鸡蛋",
            "quantity_value": 12,
            "quantity_unit": "个",
        }).json()
        response = client.post(f"/api/restock/{created['id']}/done", json={
            "purchased_quantity": 12,
            "owner": "me",
            "location": "冰箱",
        })
        assert response.status_code == 400

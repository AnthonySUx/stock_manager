"""Unified HTTP error envelopes (#100)."""

import pytest


@pytest.mark.parametrize(("method", "path", "kwargs", "status", "code"), [
    ("POST", "/api/items/clean", {"params": {"statuses": "active"}},
     400, "invalid_item_clean_status"),
    ("GET", "/api/items/99999", {}, 404, "item_not_found"),
    ("POST", "/api/items", {"json": {}}, 422, "validation_error"),
    ("PATCH", "/api/items/99999", {"json": {"status": None}}, 422, "item_status_readonly"),
    ("POST", "/api/restock/clean", {"params": {"status": "pending"}},
     400, "invalid_restock_clean_status"),
    ("GET", "/api/restock/99999", {}, 404, "restock_not_found"),
    ("POST", "/api/restock", {"json": {}}, 422, "validation_error"),
    ("POST", "/api/categories", {"json": {"name": "New", "parent_id": 99999}},
     400, "invalid_category"),
    ("GET", "/api/categories/99999", {}, 404, "category_not_found"),
    ("POST", "/api/categories", {"json": {}}, 422, "validation_error"),
    ("POST", "/api/recipes/explore", {
        "json": {"mode": "structured", "structured": {"inventory_item_ids": [99999]}},
    }, 400, "recipe_inventory_invalid"),
    ("GET", "/api/recipes/99999", {}, 404, "recipe_not_found"),
    ("POST", "/api/recipes", {"json": {}}, 422, "validation_error"),
    ("POST", "/api/recipes/explore", {
        "json": {"mode": "natural_language", "natural_language": "Soup"},
    }, 503, "ai_unavailable"),
    ("GET", "/api/nonexistent", {}, 404, "not_found"),
    ("POST", "/api/health", {}, 405, "method_not_allowed"),
])
def test_error_envelope(client, method, path, kwargs, status, code):
    response = client.request(method, path, **kwargs)

    assert response.status_code == status, response.text
    error = response.json()
    assert set(error) == {"code", "params", "detail"}
    assert error["code"] == code
    if code == "validation_error":
        assert error["params"] == {"errors": error["detail"]}
        assert error["detail"]
        assert all(isinstance(issue["loc"], list) and issue["msg"] for issue in error["detail"])
    else:
        assert error["params"] == {}
        assert isinstance(error["detail"], str) and error["detail"]


def test_auth_error_retains_the_bearer_challenge(client):
    response = client.get("/api/items", headers={"Authorization": "Bearer invalid-token"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "unauthorized"
    assert response.json()["params"] == {}
    assert response.json()["detail"]

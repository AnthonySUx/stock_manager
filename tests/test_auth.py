"""Issue #41: shared-token API authentication."""

import pytest
from fastapi.testclient import TestClient

from stock_manager.api.main import app
from tests.conftest import TEST_API_TOKEN

PROTECTED = [
    ("get", "/api/items"),
    ("get", "/api/restock"),
    ("get", "/api/settings"),
    ("get", "/api/recipes"),
    ("get", "/api/categories"),
    ("post", "/api/items/clean"),
]


@pytest.fixture()
def anon(client):
    """Same app and database as `client`, but without the Authorization header."""
    client.headers.pop("Authorization", None)
    return client


class TestTokenRequired:
    @pytest.mark.parametrize("method,path", PROTECTED)
    def test_missing_token_is_401(self, anon, method, path):
        response = getattr(anon, method)(path)
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    def test_wrong_token_is_401(self, anon):
        response = anon.get("/api/items", headers={"Authorization": "Bearer wrong"})
        assert response.status_code == 401

    def test_non_bearer_scheme_is_401(self, anon):
        response = anon.get("/api/items", headers={"Authorization": f"Basic {TEST_API_TOKEN}"})
        assert response.status_code == 401

    def test_correct_token_is_allowed(self, client):
        assert client.get("/api/items").status_code == 200

    def test_health_is_public(self, anon):
        assert anon.get("/api/health").status_code == 200

    def test_openapi_declares_bearer_scheme(self, anon):
        spec = anon.get("/openapi.json").json()
        schemes = spec["components"]["securitySchemes"]
        assert any(s.get("scheme", "").lower() == "bearer" for s in schemes.values())


class TestAuthDisabled:
    def test_disabled_flag_allows_requests_without_token(self, anon, monkeypatch):
        monkeypatch.setenv("API_AUTH_DISABLED", "true")
        assert anon.get("/api/items").status_code == 200


class TestStartupCheck:
    def test_startup_fails_without_token(self, monkeypatch, db_session):
        from tests.conftest import test_engine
        monkeypatch.setattr("stock_manager.api.main.engine", test_engine)
        monkeypatch.delenv("API_TOKEN", raising=False)
        monkeypatch.delenv("API_AUTH_DISABLED", raising=False)
        with pytest.raises(RuntimeError, match="API_TOKEN is not set"):
            with TestClient(app):
                pass

    def test_startup_ok_when_disabled(self, monkeypatch, db_session):
        from tests.conftest import test_engine
        monkeypatch.setattr("stock_manager.api.main.engine", test_engine)
        monkeypatch.delenv("API_TOKEN", raising=False)
        monkeypatch.setenv("API_AUTH_DISABLED", "true")
        with TestClient(app) as c:
            assert c.get("/api/health").status_code == 200

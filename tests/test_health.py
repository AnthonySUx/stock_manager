"""Health check endpoint tests."""

from stock_manager import __version__


def test_health_check(client):
    """GET /api/health should return status ok and current version."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": __version__,
    }

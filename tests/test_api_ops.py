"""API documentation, process startup, and AI rate limits (#103)."""

import json
import os
import subprocess
from contextlib import closing
from pathlib import Path
from shutil import copyfile

import pytest
from fastapi.testclient import TestClient

from stock_manager.api.errors import APIError
from stock_manager.api.main import create_app
from stock_manager.api.rate_limit import AIRateLimiter


DOC_PATHS = ("/docs", "/redoc", "/openapi.json")
EXPLORE = {"mode": "natural_language", "natural_language": "Make soup", "locale": "en"}


def test_api_docs_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
    with closing(TestClient(create_app())) as client:
        for path in DOC_PATHS:
            assert client.get(path).status_code == 404


def test_api_docs_can_be_enabled(docs_client):
    for path in DOC_PATHS:
        assert docs_client.get(path).status_code == 200


def test_thirty_first_ai_request_hits_default_rate_limit(client, fake_ai, monkeypatch):
    monkeypatch.delenv("AI_RATE_LIMIT_PER_WINDOW", raising=False)
    monkeypatch.delenv("AI_RATE_LIMIT_WINDOW_SECONDS", raising=False)
    limiter = AIRateLimiter.from_env()
    monkeypatch.setattr(limiter, "clock", lambda: 100.0)
    monkeypatch.setattr(client.app.state, "ai_rate_limiter", limiter)
    fake_ai.reply = json.dumps({"ideas": [{"title": "Vegetable Soup"}]})
    path = "/api/recipes/explore"

    for _ in range(30):
        response = client.post(path, json=EXPLORE)
        assert response.status_code == 200, response.text

    response = client.post(path, json=EXPLORE)

    assert response.status_code == 429
    assert response.json() == {
        "code": "rate_limited", "params": {"retry_after": 600}, "detail": "Too many AI requests",
    }
    assert len(fake_ai.requests) == 30


def test_ai_quota_is_shared_across_ai_routes_only(client, fake_ai, monkeypatch):
    monkeypatch.setenv("AI_RATE_LIMIT_PER_WINDOW", "1")
    monkeypatch.setenv("AI_RATE_LIMIT_WINDOW_SECONDS", "20")
    limiter = AIRateLimiter.from_env()
    monkeypatch.setattr(limiter, "clock", lambda: 100.0)
    monkeypatch.setattr(client.app.state, "ai_rate_limiter", limiter)
    fake_ai.reply = json.dumps({"ideas": [{"title": "Vegetable Soup"}]})

    unauthorized = client.post(
        "/api/recipes/explore", json=EXPLORE, headers={"Authorization": ""},
    )
    assert unauthorized.status_code == 401

    first = client.post("/api/recipes/explore", json=EXPLORE)
    assert first.status_code == 200, first.text

    for path, kwargs in (
        ("/api/recipes/explore/stream", {"json": EXPLORE}),
        ("/api/recipes/explore/expand", {"json": {"idea": {"title": "Soup"}}}),
        ("/api/intake/parse", {"json": {
            "input": {"type": "text", "text": "Milk"}, "draft": {"items": []},
        }}),
        ("/api/intake/parse", {"files": {"images": ("photo.png", b"image", "image/png")}}),
        ("/api/speech/transcribe", {"files": {"audio": ("clip.wav", b"audio", "audio/wav")}}),
    ):
        limited = client.post(path, **kwargs)
        assert limited.status_code == 429, (path, limited.text)
        assert limited.json()["params"] == {"retry_after": 20}

    for path in ("/api/capabilities", "/api/recipes/recommendations", "/api/items"):
        assert client.get(path).status_code == 200
    assert len(fake_ai.requests) == 1


def test_rate_limit_is_independent_per_token_and_expires_entries_in_order():
    now = 100.0
    limiter = AIRateLimiter(2, 10, clock=lambda: now)
    limiter.check("test-household-a")
    now += 4
    limiter.check("test-household-a")
    limiter.check("test-household-b")
    now = 109.75

    with pytest.raises(APIError) as blocked:
        limiter.check("test-household-a")
    assert blocked.value.params == {"retry_after": 1}

    now = 110
    limiter.check("test-household-a")
    with pytest.raises(APIError) as blocked:
        limiter.check("test-household-a")
    assert blocked.value.params == {"retry_after": 4}
    limiter.check("test-household-b")


@pytest.mark.parametrize("args, expects_reload", [([], False), (["--dev"], True)])
def test_backend_script_only_passes_reload_in_development(tmp_path, args, expects_reload):
    source = Path(__file__).resolve().parents[1] / "scripts" / "start_backend.sh"
    script = tmp_path / "scripts" / source.name
    script.parent.mkdir()
    copyfile(source, script)
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/usr/bin/env bash\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "ARG:%s\\n" "$@"\n')
    python.chmod(0o755)

    result = subprocess.run(
        ["bash", str(script), *args], capture_output=True, text=True,
        env={"PATH": os.defpath},
    )

    assert result.returncode == 0, result.stderr
    assert "ARG:stock_manager.api.main:app" in result.stdout
    assert ("ARG:--reload" in result.stdout) is expects_reload

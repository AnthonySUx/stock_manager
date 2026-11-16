"""Issue #66: the shared AI client, /api/capabilities and the 0002 migration.

The provider is always httpx.MockTransport (`fake_ai` in conftest).
"""

import asyncio
import base64
import logging

import httpx
import pytest

from stock_manager.api import ai_client
from stock_manager.api.ai_client import AIConfig, AIUnavailableError, AIUpstreamError

REQUEST = httpx.Request("POST", "http://ai.invalid/chat/completions")


def _chat(*args, **kwargs):
    return asyncio.run(ai_client.chat_json("system: reply in json", "user", *args, **kwargs))


# ─── Configuration ────────────────────────────────────────────────


class TestConfig:
    def test_defaults(self):
        config = ai_client.load_config({})
        assert config == AIConfig()
        assert (config.model, config.base_url) == ("deepseek-flash", "https://api.deepseek.com")
        assert (config.text_timeout, config.image_timeout) == (30, 60)
        assert (config.text_total_timeout, config.image_total_timeout) == (45, 75)
        assert config.max_retries == 1
        assert not config.available

    def test_reads_environment(self):
        config = ai_client.load_config({
            "AI_RECIPE_ENABLED": "TRUE", "AI_API_KEY": "k", "AI_MODEL": "m1",
            "AI_BASE_URL": "http://x", "AI_TEMPERATURE": "0.5", "AI_TIMEOUT_SECONDS": "9",
            "AI_IMAGE_TIMEOUT_SECONDS": "20", "AI_TOTAL_TIMEOUT_SECONDS": "12",
            "AI_IMAGE_TOTAL_TIMEOUT_SECONDS": "30", "AI_MAX_RETRIES": "0",
        })
        assert config == AIConfig(
            enabled=True, api_key="k", model="m1", base_url="http://x", temperature=0.5,
            text_timeout=9, image_timeout=20, text_total_timeout=12,
            image_total_timeout=30, max_retries=0,
        )
        assert config.available

    @pytest.mark.parametrize("var,value", [
        ("AI_TIMEOUT_SECONDS", "abc"), ("AI_TIMEOUT_SECONDS", "0"), ("AI_TEMPERATURE", "-1"),
        ("AI_MAX_RETRIES", "1.5"), ("AI_MAX_RETRIES", "-1"), ("AI_IMAGE_TOTAL_TIMEOUT_SECONDS", "x"),
    ])
    def test_invalid_value_disables_ai_and_logs(self, caplog, var, value):
        with caplog.at_level(logging.ERROR, logger="stock_manager.api.ai_client"):
            config = ai_client.load_config({"AI_RECIPE_ENABLED": "true", "AI_API_KEY": "k", var: value})
        assert not config.available
        assert var in caplog.text

    def test_enabled_without_key_is_unavailable(self):
        assert not ai_client.load_config({"AI_RECIPE_ENABLED": "true"}).available

    def test_config_is_read_once(self, monkeypatch):
        monkeypatch.setenv("AI_RECIPE_ENABLED", "true")
        monkeypatch.setenv("AI_API_KEY", "k")
        assert ai_client.reload_config().available
        monkeypatch.setenv("AI_RECIPE_ENABLED", "false")
        assert ai_client.is_available()  # unchanged until reloaded
        ai_client.reload_config()
        assert not ai_client.is_available()


def test_invalid_config_is_reported_at_startup(db_session, monkeypatch, caplog):
    """Validated once when the API starts, not on the first AI request."""
    from fastapi.testclient import TestClient

    from stock_manager.api.main import app
    from tests.conftest import test_engine

    monkeypatch.setattr("stock_manager.api.main.engine", test_engine)
    monkeypatch.setenv("API_TOKEN", "t")
    monkeypatch.setenv("AI_RECIPE_ENABLED", "true")
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "soon")
    with caplog.at_level(logging.ERROR, logger="stock_manager.api.ai_client"):
        with TestClient(app):
            pass  # startup only, no request
    assert "AI_TIMEOUT_SECONDS" in caplog.text
    assert ai_client._config is not None and not ai_client._config.available


# ─── chat_json ────────────────────────────────────────────────────


class TestChatJson:
    def test_unavailable_raises_without_a_request(self, fake_ai, monkeypatch):
        monkeypatch.setattr(ai_client, "_config", AIConfig(enabled=False, api_key="k"))
        with pytest.raises(AIUnavailableError):
            _chat()
        assert fake_ai.requests == []

    def test_request_payload(self, fake_ai):
        fake_ai.reply = '{"a": 1}'
        assert _chat() == {"a": 1}
        payload = fake_ai.requests[0]
        assert payload["model"] == "deepseek-flash"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["messages"] == [
            {"role": "system", "content": "system: reply in json"},
            {"role": "user", "content": "user"},
        ]

    @pytest.mark.parametrize("reply,expected", [
        ('{"ideas": []}', {"ideas": []}),
        ("[1, 2]", [1, 2]),
        ('Sure!\n```json\n{"x": 1}\n```', {"x": 1}),
        ('```\n[{"x": 1}]\n```', [{"x": 1}]),
    ])
    def test_parses_json_and_fenced_json(self, fake_ai, reply, expected):
        fake_ai.reply = reply
        assert _chat() == expected

    @pytest.mark.parametrize("reply", ["not json", '"a string"', "42", "null", "", "```json\nnope\n```"])
    def test_unparseable_reply_is_upstream_error(self, fake_ai, reply):
        fake_ai.reply = reply
        with pytest.raises(AIUpstreamError):
            _chat()
        assert len(fake_ai.requests) == 1  # a bad reply is not retried

    @pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {}}]}])
    def test_reply_without_content_is_upstream_error(self, fake_ai, body):
        fake_ai.responses = [httpx.Response(200, json=body)]
        with pytest.raises(AIUpstreamError):
            _chat()

    def test_non_json_http_body_is_upstream_error(self, fake_ai):
        fake_ai.responses = [httpx.Response(200, text="<html>")]
        with pytest.raises(AIUpstreamError):
            _chat()

    # Retries: connection errors, 429 and 5xx once; timeouts and other 4xx never.

    @pytest.mark.parametrize("first", [
        httpx.ConnectError("refused", request=REQUEST),
        httpx.Response(429),
        httpx.Response(500),
        httpx.Response(503),
    ])
    def test_retries_once_then_succeeds(self, fake_ai, first):
        fake_ai.responses = [first, '{"ok": true}']
        assert _chat() == {"ok": True}
        assert len(fake_ai.requests) == 2

    def test_gives_up_after_one_retry(self, fake_ai):
        fake_ai.responses = [httpx.Response(500), httpx.Response(500), '{"never": 1}']
        with pytest.raises(AIUpstreamError):
            _chat()
        assert len(fake_ai.requests) == 2

    def test_connection_error_twice_is_upstream_error(self, fake_ai):
        fake_ai.responses = [httpx.ConnectError("x", request=REQUEST)] * 2
        with pytest.raises(AIUpstreamError):
            _chat()
        assert len(fake_ai.requests) == 2

    @pytest.mark.parametrize("first", [
        httpx.ReadTimeout("slow", request=REQUEST),
        httpx.ConnectTimeout("slow", request=REQUEST),
        httpx.Response(400),
        httpx.Response(401),
    ])
    def test_no_retry(self, fake_ai, first):
        fake_ai.responses = [first, '{"never": 1}']
        with pytest.raises(AIUpstreamError):
            _chat()
        assert len(fake_ai.requests) == 1

    def test_retries_follow_config(self, fake_ai, monkeypatch):
        monkeypatch.setattr(ai_client, "_config", AIConfig(enabled=True, api_key="k", max_retries=0))
        fake_ai.responses = [httpx.Response(500), '{"ok": 1}']
        with pytest.raises(AIUpstreamError):
            _chat()
        assert len(fake_ai.requests) == 1

    def test_total_time_limit(self, monkeypatch):
        async def slow(request):
            await asyncio.sleep(1)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(slow))
        monkeypatch.setattr(ai_client, "_config", AIConfig(
            enabled=True, api_key="k", text_total_timeout=0.05, image_total_timeout=5,
        ))
        with pytest.raises(AIUpstreamError, match="exceeded"):
            _chat()

    def test_per_request_timeouts(self, fake_ai, monkeypatch):
        seen = []
        real_client = httpx.AsyncClient

        def spy(*args, **kwargs):
            seen.append(kwargs["timeout"])
            return real_client(*args, **kwargs)

        monkeypatch.setattr(ai_client.httpx, "AsyncClient", spy)
        fake_ai.reply = "{}"
        _chat()
        _chat(images=[{"data": b"img", "mime": "image/png"}])
        assert seen == [30, 60]

    def test_images_are_sent_as_data_urls(self, fake_ai):
        fake_ai.reply = "{}"
        _chat(images=[
            {"data": b"\x89PNG", "mime": "image/png", "detail": "high"},
            {"data": b"\xff\xd8", "mime": "image/jpeg"},
        ])
        content = fake_ai.requests[0]["messages"][1]["content"]
        assert content[0] == {"type": "text", "text": "user"}
        assert content[1] == {"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode(), "detail": "high",
        }}
        assert content[2]["image_url"]["detail"] == "auto"
        assert content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")


# ─── /api/capabilities ────────────────────────────────────────────


class TestCapabilities:
    def test_ai_on(self, client, fake_ai):
        response = client.get("/api/capabilities")
        assert response.status_code == 200
        assert response.json() == {"ai": {"text": True, "vision": False, "asr": False}}

    def test_ai_off(self, client, monkeypatch):
        monkeypatch.setenv("AI_RECIPE_ENABLED", "false")
        ai_client.reload_config()
        assert client.get("/api/capabilities").json()["ai"]["text"] is False

    def test_needs_the_token(self, client):
        response = client.get("/api/capabilities", headers={"Authorization": ""})
        assert response.status_code == 401


# ─── ai_saved is gone ─────────────────────────────────────────────


def test_ai_saved_filter_is_rejected(client):
    assert client.get("/api/recipes", params={"source_type": "ai_saved"}).status_code == 422
    assert client.get("/api/recipes", params={"source_type": "user"}).status_code == 200


def test_unused_ai_table_is_not_in_the_models():
    from stock_manager.api.models import Base

    assert "ai_recipe_recommendations" not in Base.metadata.tables

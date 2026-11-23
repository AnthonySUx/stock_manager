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
        assert (config.text_total_timeout, config.image_total_timeout) == (50, 110)
        assert (config.first_token_timeout, config.idle_timeout) == (20, 15)
        assert (config.stream, config.max_tokens) == (True, 8192)
        assert config.max_retries == 1
        assert config.image_thinking is False
        assert not config.available

    def test_reads_environment(self):
        config = ai_client.load_config({
            "AI_RECIPE_ENABLED": "TRUE", "AI_API_KEY": "k", "AI_MODEL": "m1",
            "AI_BASE_URL": "http://x", "AI_TEMPERATURE": "0.5", "AI_TIMEOUT_SECONDS": "9",
            "AI_IMAGE_TIMEOUT_SECONDS": "20", "AI_TOTAL_TIMEOUT_SECONDS": "12",
            "AI_IMAGE_TOTAL_TIMEOUT_SECONDS": "30", "AI_MAX_RETRIES": "0",
            "AI_STREAM": " FALSE ", "AI_MAX_TOKENS": "1000", "AI_FIRST_TOKEN_TIMEOUT_SECONDS": "7",
            "AI_IDLE_TIMEOUT_SECONDS": "3",
        })
        assert config == AIConfig(
            enabled=True, api_key="k", model="m1", base_url="http://x", temperature=0.5,
            text_timeout=9, image_timeout=20, text_total_timeout=12,
            image_total_timeout=30, max_retries=0, stream=False, max_tokens=1000,
            first_token_timeout=7, idle_timeout=3,
        )
        assert config.available

    @pytest.mark.parametrize("var,value", [
        ("AI_TIMEOUT_SECONDS", "abc"), ("AI_TIMEOUT_SECONDS", "0"), ("AI_TEMPERATURE", "-1"),
        ("AI_MAX_RETRIES", "1.5"), ("AI_MAX_RETRIES", "-1"), ("AI_IMAGE_TOTAL_TIMEOUT_SECONDS", "x"),
        ("AI_MAX_TOKENS", "0"), ("AI_IDLE_TIMEOUT_SECONDS", "0.5"), ("AI_FIRST_TOKEN_TIMEOUT_SECONDS", "x"),
        ("AI_STREAM", "yes"),
    ])
    def test_invalid_value_disables_ai_and_logs(self, caplog, var, value):
        with caplog.at_level(logging.ERROR, logger="stock_manager.api.ai_client"):
            config = ai_client.load_config({"AI_RECIPE_ENABLED": "true", "AI_API_KEY": "k", var: value})
        assert not config.available
        assert var in caplog.text

    @pytest.mark.parametrize("value,expected", [("", False), (" FALSE ", False), ("True", True)])
    def test_image_thinking_setting(self, value, expected):
        config = ai_client.load_config({
            "AI_RECIPE_ENABLED": "true", "AI_API_KEY": "k", "AI_VISION_ENABLED": "true",
            "AI_IMAGE_THINKING": value,
        })
        assert config.image_thinking is expected
        assert config.vision_available

    def test_invalid_image_thinking_disables_vision_only(self, caplog):
        with caplog.at_level(logging.ERROR, logger="stock_manager.api.ai_client"):
            config = ai_client.load_config({
                "AI_RECIPE_ENABLED": "true", "AI_API_KEY": "k", "AI_VISION_ENABLED": "true",
                "AI_IMAGE_THINKING": "maybe",
            })
        assert config.available and not config.vision_available
        assert "AI_IMAGE_THINKING" in caplog.text

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

    @pytest.mark.parametrize("reply", ["not json", '"a string"', "42", "null", "```json\nnope\n```"])
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

    # Empty replies: DeepSeek documents that JSON mode occasionally returns
    # empty content. A well-formed empty reply is retried once if time allows.

    IMAGE = [{"data": b"img", "mime": "image/png"}]

    @staticmethod
    def _plain(content, finish="stop", reasoning=None):
        message = {"content": content}
        if reasoning is not None:
            message["reasoning_content"] = reasoning
        return httpx.Response(200, json={
            "choices": [{"message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 40},
        })

    @pytest.mark.parametrize("content", ["", "   \n ", None])
    def test_empty_image_reply_is_retried_once(self, fake_ai, content, caplog):
        fake_ai.responses = [self._plain(content), self._plain('{"ok": 1}')]
        with caplog.at_level(logging.INFO, logger="stock_manager.api.ai_client"):
            assert _chat(images=self.IMAGE) == {"ok": 1}
        assert len(fake_ai.requests) == 2
        assert "empty reply" in caplog.text and "retrying once" in caplog.text
        assert "rounds=2" in caplog.text

    def test_empty_streamed_reply_is_retried_once(self, fake_ai):
        fake_ai.responses = ["   ", '{"ok": 1}']
        assert _chat() == {"ok": 1}
        assert len(fake_ai.requests) == 2

    def test_second_empty_reply_fails(self, fake_ai):
        fake_ai.responses = [self._plain(""), self._plain("")]
        with pytest.raises(AIUpstreamError) as error:
            _chat(images=self.IMAGE)
        assert error.value.reason == "no_content"
        assert len(fake_ai.requests) == 2

    def test_empty_reply_at_token_limit_is_truncated_and_not_retried(self, fake_ai):
        fake_ai.responses = [self._plain("", finish="length", reasoning="thinking" * 10)]
        with pytest.raises(AIUpstreamError, match="cut off at max_tokens=8192 before any content") as error:
            _chat(images=self.IMAGE)
        assert error.value.reason == "truncated"
        assert len(fake_ai.requests) == 1

    def test_empty_reply_is_not_retried_without_time_for_another_attempt(self, monkeypatch):
        requests = []

        async def slow_empty(request):
            requests.append(request)
            await asyncio.sleep(0.2)
            return self._plain("")

        monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(slow_empty))
        monkeypatch.setattr(ai_client, "_config", AIConfig(
            enabled=True, api_key="k", image_timeout=5, image_total_timeout=0.3,
        ))
        with pytest.raises(AIUpstreamError) as error:
            _chat(images=self.IMAGE)
        assert error.value.reason == "no_content"
        assert len(requests) == 1

    def test_image_failure_log_has_counters_but_no_content(self, fake_ai, caplog):
        fake_ai.responses = [self._plain("", reasoning="secret label text") for _ in range(2)]
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            with pytest.raises(AIUpstreamError):
                _chat(images=[{"data": b"PRIVATE-IMAGE", "mime": "image/png"}])
        assert "finish=stop tokens=900/40 reasoning_chars=17" in caplog.text
        assert "secret label text" not in caplog.text
        assert base64.b64encode(b"PRIVATE-IMAGE").decode() not in caplog.text

    def test_image_logs_drop_echoed_metadata_on_empty_replies(self, fake_ai, caplog):
        echo = "PRIVATE_UPLOAD_CONTENT"
        fake_ai.responses = [httpx.Response(200, json={
            "choices": [{"message": {"content": ""}, "finish_reason": echo}],
            "usage": {"prompt_tokens": echo, "completion_tokens": {"x": echo}},
        }) for _ in range(2)]
        with caplog.at_level(logging.INFO, logger="stock_manager.api.ai_client"):
            with pytest.raises(AIUpstreamError):
                _chat(images=self.IMAGE)
        assert "retrying once" in caplog.text and "finish=- tokens=?/?" in caplog.text
        assert echo not in caplog.text

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
        _chat()  # streamed: connect 10 s, headers within the first-token limit
        _chat(images=[{"data": b"img", "mime": "image/png"}])  # images are not streamed
        monkeypatch.setenv("AI_STREAM", "false")
        ai_client.reload_config()
        _chat()
        assert seen == [httpx.Timeout(10, read=20), httpx.Timeout(60), httpx.Timeout(30)]
        assert [r.get("stream") for r in fake_ai.requests] == [True, None, None]

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

    def test_image_calls_disable_thinking_and_text_calls_do_not(self, fake_ai):
        fake_ai.reply = "{}"
        _chat(images=[{"data": b"img", "mime": "image/png"}])
        _chat()
        assert fake_ai.requests[0]["thinking"] == {"type": "disabled"}
        assert "thinking" not in fake_ai.requests[1]

    def test_image_thinking_true_sends_no_thinking_setting(self, fake_ai, monkeypatch):
        fake_ai.reply = "{}"
        monkeypatch.setenv("AI_IMAGE_THINKING", "true")
        ai_client.reload_config()
        _chat(images=[{"data": b"img", "mime": "image/png"}])
        assert "thinking" not in fake_ai.requests[0]


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


# ─── ai_saved filtering ─────────────────────────────────────────────


def test_ai_saved_filter_is_accepted(client):
    assert client.get("/api/recipes", params={"source_type": "ai_saved"}).status_code == 200
    assert client.get("/api/recipes", params={"source_type": "user"}).status_code == 200


def test_unused_ai_table_is_not_in_the_models():
    from stock_manager.api.models import Base

    assert "ai_recipe_recommendations" not in Base.metadata.tables


# ─── Diagnostics: why a request ended in 502 ─────────────────────


class TestErrorDetails:
    """The reason for a 502 reaches the server log, never the client."""

    @pytest.mark.parametrize("response,expected", [
        (httpx.Response(400, json={"error": {"message": "Model Not Exist", "type": "invalid_request_error"}}),
         "AI returned HTTP 400: Model Not Exist"),
        (httpx.Response(404, json={"error": "no such route"}), "AI returned HTTP 404: no such route"),
        (httpx.Response(422, text="  bad\n  payload  "), "AI returned HTTP 422: bad payload"),
        (httpx.Response(400, json={"error": {"code": 1}}), 'AI returned HTTP 400: {"error":{"code":1}}'),
        (httpx.Response(400), "AI returned HTTP 400"),
        (httpx.Response(402, text="x" * 300), "AI returned HTTP 402: " + "x" * 200),
    ])
    def test_provider_message_is_in_the_error(self, fake_ai, response, expected):
        fake_ai.responses = [response]
        with pytest.raises(AIUpstreamError) as info:
            _chat()
        assert str(info.value) == expected

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_error_body_is_not_logged(self, fake_ai, status):
        """The provider may echo part of the key in a 401 body."""
        fake_ai.responses = [httpx.Response(status, json={"error": {"message": "key sk-secret is invalid"}})]
        with pytest.raises(AIUpstreamError) as info:
            _chat()
        assert str(info.value) == f"AI returned HTTP {status} (check AI_API_KEY)"
        assert "sk-secret" not in str(info.value)

    def test_handler_logs_the_reason_and_returns_error_envelope(self, client, fake_ai, caplog):
        fake_ai.responses = [httpx.Response(400, json={"error": {"message": "Model Not Exist"}})]
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.main"):
            response = client.post("/api/recipes/explore", json={"mode": "natural_language", "natural_language": "晚饭"})
        assert response.status_code == 502
        assert response.json()["code"] == "ai_upstream_error"
        assert {"params", "detail"} <= response.json().keys()
        assert "POST /api/recipes/explore -> ai_upstream_error [http_error]: AI returned HTTP 400: Model Not Exist" in caplog.text

    def test_no_usable_ideas_logs_the_problems(self, client, fake_ai, caplog):
        fake_ai.reply = '{"ideas": [{"description": "x"}]}'
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.main"):
            response = client.post("/api/recipes/explore", json={"mode": "natural_language", "natural_language": "晚饭"})
        assert response.status_code == 502
        assert "AI reply contained no usable ideas: Idea #1: missing title." in caplog.text

    def test_unusable_draft_logs_the_problems(self, client, fake_ai, caplog):
        fake_ai.reply = '{"title": "番茄炒蛋", "steps": []}'
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.main"):
            response = client.post("/api/recipes/explore/expand", json={"idea": {"title": "番茄炒蛋"}})
        assert response.status_code == 502
        assert "AI draft was unusable: steps is empty" in caplog.text


def test_problem_summary_is_capped():
    from stock_manager.api.explore_services import _summary

    assert _summary([]) == "no details"
    assert _summary(["a", "b"]) == "a | b"
    assert _summary([str(i) for i in range(8)]) == "0 | 1 | 2 | 3 | 4 | (+3 more)"


# ─── Test isolation ──────────────────────────────────────────────


class TestNoRealProvider:
    """Tests must never reach the real provider, whatever the local .env says."""

    def test_ai_is_off_by_default(self):
        assert not ai_client.get_config().available

    def test_an_unmocked_call_fails_the_test(self, monkeypatch):
        monkeypatch.setenv("AI_RECIPE_ENABLED", "true")
        monkeypatch.setenv("AI_API_KEY", "k")
        ai_client.reload_config()
        with pytest.raises(AssertionError, match="real AI provider"):
            _chat()

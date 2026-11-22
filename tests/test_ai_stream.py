"""Streaming from the AI provider, per-round time limits, call logs, and the
streamed Explore endpoint that sends only validated ideas (#65 follow-up).

The provider is always an httpx.MockTransport.
"""
import asyncio
import json
import logging

import httpx
import pytest

from stock_manager.api import ai_client
from stock_manager.api.ai_client import AIConfig, AIUpstreamError
from stock_manager.api.json_stream import ArrayItemStream
from tests.conftest import sse_body


def _data(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _content(text: str) -> str:
    return _data({"choices": [{"index": 0, "delta": {"content": text}}]})


def _finish(reason: str = "stop") -> str:
    return _data({"choices": [{"index": 0, "delta": {}, "finish_reason": reason}]})


DONE = "data: [DONE]\n\n"


def _streaming(*pieces) -> httpx.Response:
    """An SSE response built from text pieces, pauses (seconds), events to wait
    for, and exceptions to raise mid-stream."""
    async def body():
        for piece in pieces:
            if isinstance(piece, (int, float)):
                await asyncio.sleep(piece)
            elif isinstance(piece, asyncio.Event):
                await piece.wait()
            elif isinstance(piece, Exception):
                raise piece
            else:
                yield piece.encode()

    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body())


def _use(monkeypatch, *responses, **config):
    """Answer the next calls with `responses`; optional AIConfig overrides."""
    queue = list(responses)
    requests = []

    async def handler(request):
        requests.append(json.loads(request.content))
        item = queue.pop(0)
        return item() if callable(item) else item

    monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(ai_client, "_config", AIConfig(enabled=True, api_key="k", **config))
    return requests


def _chat(**kwargs):
    return asyncio.run(ai_client.chat_json("system: json", "user", **kwargs))


# ─── chat_json streaming ─────────────────────────────────────────


class TestStreaming:
    def test_reply_is_reassembled_and_request_asks_for_a_stream(self, monkeypatch):
        requests = _use(monkeypatch, _streaming(_content('{"a"'), _content(': [1, '), _content("2]}"),
                                                _finish(), DONE))
        seen = []
        assert _chat(on_text=seen.append) == {"a": [1, 2]}
        assert "".join(seen) == '{"a": [1, 2]}'
        assert requests[0]["stream"] is True
        assert requests[0]["stream_options"] == {"include_usage": True}
        assert requests[0]["max_tokens"] == 8192

    def test_reasoning_is_not_part_of_the_reply(self, monkeypatch, caplog):
        _use(monkeypatch, lambda: httpx.Response(
            200, headers={"content-type": "text/event-stream"},
            content=sse_body('{"ok": 1}', reasoning="let me think about tomatoes",
                             usage={"prompt_tokens": 812, "completion_tokens": 1430}),
        ))
        seen = []
        with caplog.at_level(logging.INFO, logger="stock_manager.api.ai_client"):
            assert _chat(on_text=seen.append, label="explore/first") == {"ok": 1}
        assert "".join(seen) == '{"ok": 1}'
        line = caplog.records[-1]
        assert line.levelno == logging.INFO
        assert line.getMessage().startswith("AI explore/first ok model=deepseek-flash stream ")
        assert "tokens=812/1430 finish=stop" in line.getMessage()
        assert "reasoning=-" not in line.getMessage()

    def test_keep_alive_comments_and_events_are_ignored(self, monkeypatch):
        _use(monkeypatch, _streaming(": keep-alive\n\n", "event: message\n", _content('{"x": 1}'), DONE))
        assert _chat() == {"x": 1}

    def test_stream_without_done_marker_ends_at_eof(self, monkeypatch):
        _use(monkeypatch, _streaming(_content('{"x": 1}'), _finish()))
        assert _chat() == {"x": 1}

    def test_provider_that_ignores_stream_is_read_as_one_body(self, monkeypatch):
        _use(monkeypatch, httpx.Response(200, json={"choices": [{"message": {"content": '{"x": 2}'}}]}))
        seen = []
        assert _chat(on_text=seen.append) == {"x": 2}
        assert seen == ['{"x": 2}']

    def test_ai_stream_false_sends_no_stream_flag(self, monkeypatch):
        requests = _use(monkeypatch, httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]}),
                        stream=False)
        assert _chat() == {}
        assert "stream" not in requests[0] and "stream_options" not in requests[0]

    def test_max_tokens_follows_config(self, monkeypatch):
        requests = _use(monkeypatch, _streaming(_content("{}"), DONE), max_tokens=123)
        _chat()
        assert requests[0]["max_tokens"] == 123


# ─── Why a call failed ───────────────────────────────────────────


def _fails(monkeypatch, caplog, response, reason, **config) -> AIUpstreamError:
    _use(monkeypatch, response, **config)
    with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
        with pytest.raises(AIUpstreamError) as info:
            _chat(label="explore/first")
    assert info.value.reason == reason
    assert f"AI explore/first fail {reason} model=deepseek-flash" in caplog.text
    return info.value


class TestFailureReasons:
    def test_no_first_token(self, monkeypatch, caplog):
        error = _fails(monkeypatch, caplog, _streaming(1.0, _content("{}")), "timeout_first_token",
                       first_token_timeout=0.1)
        assert "first_data=-" in caplog.text
        assert str(error) == "no data from the AI within 0.1s"

    def test_keep_alive_does_not_count_as_a_first_token(self, monkeypatch, caplog):
        pings = [p for _ in range(10) for p in (": keep-alive\n\n", 0.03)]
        _fails(monkeypatch, caplog, _streaming(*pings, _content("{}")), "timeout_first_token",
               first_token_timeout=0.1)

    def test_stream_stalls(self, monkeypatch, caplog):
        _fails(monkeypatch, caplog, _streaming(_content('{"ideas": ['), 1.0, _content("]}")),
               "timeout_idle", idle_timeout=0.1)
        assert "chars=11" in caplog.text

    def test_reasoning_counts_as_data(self, monkeypatch):
        thinking = _data({"choices": [{"index": 0, "delta": {"reasoning_content": "hmm"}}]})
        _use(monkeypatch, _streaming(*[p for _ in range(5) for p in (thinking, 0.05)], _content("{}"), DONE),
             first_token_timeout=0.1, idle_timeout=0.1)
        assert _chat() == {}

    def test_slow_but_steady_stream_is_fine_until_the_round_limit(self, monkeypatch, caplog):
        steady = [p for _ in range(60) for p in (_content(" "), 0.02)]
        _use(monkeypatch, _streaming(_content("{}"), *steady, DONE), idle_timeout=0.6, text_total_timeout=5)
        assert _chat() == {}  # 1.2 s in all, but never idle for 0.6 s
        _fails(monkeypatch, caplog, _streaming(_content("{}"), *steady, DONE), "timeout_round",
               idle_timeout=2, text_total_timeout=0.3)

    def test_round_limit_holds_without_the_outer_wait_for(self, monkeypatch):
        """The stream reader enforces the round limit itself (a cancellation
        from the outer wait_for can be lost on Python 3.11)."""
        steady = [p for _ in range(60) for p in (_content(" "), 0.02)]
        _use(monkeypatch, _streaming(_content("{}"), *steady, DONE), idle_timeout=2)
        config = ai_client.get_config()
        stats, reply = ai_client.CallStats(), ai_client._Reply()
        with pytest.raises(AIUpstreamError) as info:
            asyncio.run(ai_client._request(config, {"stream": True}, True, 30, 0.3, stats, reply, None))
        assert info.value.reason == "timeout_round"
        assert 0.25 < stats.now() < 1.0

    def test_truncated_reply(self, monkeypatch, caplog):
        error = _fails(monkeypatch, caplog, _streaming(_content('{"ideas": [{"ti'), _finish("length"), DONE),
                       "truncated", max_tokens=50)
        assert str(error) == "AI reply was cut off at max_tokens=50"
        assert "finish=length" in caplog.text

    def test_complete_reply_at_the_length_limit_is_used(self, monkeypatch):
        _use(monkeypatch, _streaming(_content('{"a": 1}'), _finish("length"), DONE))
        assert _chat() == {"a": 1}

    def test_not_json(self, monkeypatch, caplog):
        error = _fails(monkeypatch, caplog, _streaming(_content("Sure! Here are ideas"), _finish(), DONE),
                       "not_json")
        assert "Sure! Here are ideas" in str(error)

    def test_empty_reply(self, monkeypatch, caplog):
        # An empty reply is retried once (DeepSeek JSON mode can return empty content).
        requests = _use(monkeypatch, *(_streaming(_content(""), _finish(), DONE) for _ in range(2)))
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            with pytest.raises(AIUpstreamError) as info:
                _chat(label="explore/first")
        assert info.value.reason == "no_content"
        assert "AI explore/first fail no_content model=deepseek-flash" in caplog.text
        assert "rounds=2" in caplog.text
        assert len(requests) == 2

    def test_error_inside_the_stream(self, monkeypatch, caplog):
        error = _fails(monkeypatch, caplog, _streaming(_data({"error": {"message": "server overloaded"}})),
                       "stream_error")
        assert "server overloaded" in str(error)

    @pytest.mark.parametrize("line", ["data: {broken\n\n", "data: [1]\n\n"])
    def test_broken_chunk(self, monkeypatch, caplog, line):
        _fails(monkeypatch, caplog, _streaming(line), "stream_error")

    def test_odd_chunks_are_skipped(self, monkeypatch):
        _use(monkeypatch, _streaming(_data({"choices": []}), _data({"choices": ["x"]}),
                                     _data({"choices": [{"delta": "x"}]}), _content("{}"), DONE))
        assert _chat() == {}

    def test_connection_lost_after_content_is_not_retried(self, monkeypatch, caplog):
        request = httpx.Request("POST", "http://ai.invalid")
        requests = _use(monkeypatch, _streaming(_content('{"a"'), httpx.ReadError("reset", request=request)),
                        _streaming(_content("{}"), DONE))
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            with pytest.raises(AIUpstreamError) as info:
                _chat()
        assert info.value.reason == "connection"
        assert len(requests) == 1

    def test_http_error_after_retry_is_logged_with_attempts(self, monkeypatch, caplog):
        requests = _use(monkeypatch, httpx.Response(503), httpx.Response(503, json={"error": {"message": "busy"}}))
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            with pytest.raises(AIUpstreamError, match="HTTP 503: busy"):
                _chat(label="expand/first")
        assert len(requests) == 2
        assert "AI expand/first fail http_error" in caplog.text and "attempts=2" in caplog.text

    def test_non_streamed_timeout(self, monkeypatch, caplog):
        async def slow(request):
            raise httpx.ReadTimeout("slow", request=request)

        monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(slow))
        monkeypatch.setattr(ai_client, "_config", AIConfig(enabled=True, api_key="k", stream=False))
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            with pytest.raises(AIUpstreamError) as info:
                _chat()
        assert info.value.reason == "timeout"
        assert str(info.value) == "AI request timed out after 30s"

    def test_headers_never_arrive(self, monkeypatch):
        async def slow(request):
            raise httpx.ReadTimeout("no headers", request=request)

        monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(slow))
        monkeypatch.setattr(ai_client, "_config", AIConfig(enabled=True, api_key="k"))
        with pytest.raises(AIUpstreamError) as info:
            _chat()
        assert info.value.reason == "timeout_first_token"


# ─── App logging ─────────────────────────────────────────────────


@pytest.mark.parametrize("value,level", [(None, logging.INFO), ("debug", logging.DEBUG),
                                         ("WARNING", logging.WARNING), ("nonsense", logging.INFO)])
def test_log_level(monkeypatch, value, level):
    from stock_manager.api.main import configure_logging

    app_logger = logging.getLogger("stock_manager")
    if value is None:
        monkeypatch.delenv("LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("LOG_LEVEL", value)
    before = list(app_logger.handlers)
    try:
        configure_logging()
        assert app_logger.level == level
        assert len(app_logger.handlers) == 1  # added once, at import
    finally:
        app_logger.handlers = before
        app_logger.setLevel(logging.INFO)


# ─── ArrayItemStream ─────────────────────────────────────────────


DOC = ('```json\n{"note": "a [x] {y}", "ideas": [{"title": "番茄\\"炒\\"蛋", "m": ["a", "b"], '
       '"n": {"k": [1]}}, 5, "s,]", {"title": "二"}, [1, 2], {bad}], "after": [{"title": "no"}]}\n```')
EXPECTED = [{"title": '番茄"炒"蛋', "m": ["a", "b"], "n": {"k": [1]}}, 5, "s,]", {"title": "二"}, [1, 2], "{bad}"]


class TestArrayItemStream:
    @pytest.mark.parametrize("size", [1, 2, 3, 7, 1000])
    def test_elements_in_any_chunking(self, size):
        parser = ArrayItemStream()
        items = []
        for i in range(0, len(DOC), size):
            items += parser.feed(DOC[i:i + size])
        assert items == EXPECTED
        assert (parser.found, parser.closed, parser.count) == (True, True, 6)

    def test_an_element_is_returned_as_soon_as_it_closes(self):
        parser = ArrayItemStream()
        assert parser.feed('{"ideas": [{"title": "甲"}') == [{"title": "甲"}]
        assert parser.feed(', {"title": "乙", "x": [') == []
        assert parser.feed(']}') == [{"title": "乙", "x": []}]
        assert not parser.closed

    @pytest.mark.parametrize("text,items,found", [
        ('[{"t": 1}, {"t": 2}]', [{"t": 1}, {"t": 2}], True),
        ('{"ideas": []}', [], True),
        ('{"other": [{"a": 1}], "ideas": "none"}', [], False),
        ('{"data": {"ideas": [{"a": 1}]}}', [], False),
        ('{"ideas": [{"t": 1}, {"t": 2', [{"t": 1}], True),
        ('{"ideas": [1 , 2 ]}', [1, 2], True),
        ('no json at all', [], False),
        ('{"a": "\\\\", "ideas": [{"q": "\\\\\\""}]}', [{"q": '\\"'}], True),
    ])
    def test_shapes(self, text, items, found):
        parser = ArrayItemStream()
        assert parser.feed(text) == items
        assert parser.found is found

    @pytest.mark.parametrize("text", [
        'Reply} {"ideas": [{"a": 1}]}',  # stray text before the JSON is skipped
        '{"ideas": [{"a": 1}]} [{"b": 2}]',  # and text after it is ignored
    ])
    def test_text_around_the_json(self, text):
        assert ArrayItemStream().feed(text) == [{"a": 1}]

    def test_nothing_after_a_reply_without_the_array(self):
        parser = ArrayItemStream()
        assert parser.feed('{"x": 1} [{"a": 1}]') == []
        assert not parser.found

    def test_only_the_first_array_counts(self):
        parser = ArrayItemStream()
        assert parser.feed('{"ideas": [{"a": 1}], "ideas": [{"b": 2}]}') == [{"a": 1}]


# ─── Explore: one validated idea at a time ───────────────────────


def _idea(title, **extra):
    return {"title": title, "description": f"{title}的做法", "matched_ingredients": [], **extra}


def _events(text: str) -> list[tuple[str, object]]:
    """(event, data) pairs from an SSE body; comments become ("ping", None)."""
    result = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        if block.startswith(":"):
            result.append(("ping", None))
            continue
        fields = dict(line.split(": ", 1) for line in block.split("\n"))
        result.append((fields["event"], json.loads(fields["data"])))
    return result


def _stream(client, **body):
    body.setdefault("mode", "natural_language")
    body.setdefault("natural_language", "晚饭吃什么")
    return client.post("/api/recipes/explore/stream", json=body)


class TestExploreStreamEndpoint:
    def test_events(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [
            _idea("番茄炒蛋", cooking_method="stir_fry"), _idea("Tomato soup"), _idea("红烧肉"),
            _idea("番茄炒蛋"), _idea("清蒸鱼"),
        ]}, ensure_ascii=False)
        response = _stream(client)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = _events(response.text)
        assert [e for e, _ in events] == ["idea", "idea", "idea", "done"]
        ideas = [d for e, d in events if e == "idea"]
        assert [i["title"] for i in ideas] == ["番茄炒蛋", "红烧肉", "清蒸鱼"]  # wrong language + duplicate left out
        assert all(len(i["idea_id"]) == 8 and i["source_type"] == "ai_idea" for i in ideas)
        assert ideas[0]["cooking_method"] == "stir_fry"
        done = events[-1][1]
        assert done["count"] == 3 and done["locale"] == "zh-CN" and done["input_mode"] == "natural_language"
        assert {"code": "idea_dropped_wrong_language", "params": {"title": "Tomato soup"}} in done["warnings"]
        assert len(fake_ai.requests) == 1  # three good ideas: no repair

    def test_matches_the_plain_endpoint(self, client, fake_ai):
        fake_ai.reply = json.dumps({"ideas": [_idea("甲"), _idea("乙"), _idea("丙")]}, ensure_ascii=False)
        streamed = [d for e, d in _events(_stream(client).text) if e == "idea"]
        plain = client.post("/api/recipes/explore",
                            json={"mode": "natural_language", "natural_language": "晚饭吃什么"}).json()
        strip = lambda ideas: [{k: v for k, v in i.items() if k != "idea_id"} for i in ideas]  # noqa: E731
        assert strip(streamed) == strip(plain["ideas"])
        assert plain["warnings"] == [] and "count" not in plain

    def test_repair_round_ideas_follow(self, client, fake_ai):
        fake_ai.responses = [
            json.dumps({"ideas": [_idea("甲"), _idea("Egg")]}, ensure_ascii=False),
            json.dumps({"ideas": [_idea("乙"), _idea("甲")]}, ensure_ascii=False),
        ]
        events = _events(_stream(client).text)
        assert [d["title"] for e, d in events if e == "idea"] == ["甲", "乙"]
        assert events[-1][1]["warnings"] == []  # drop warnings come from the repair round
        assert len(fake_ai.requests) == 2

    def test_no_usable_idea_is_an_error_event(self, client, fake_ai, caplog):
        fake_ai.reply = json.dumps({"ideas": [_idea("Egg")]})
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            response = _stream(client)
        assert response.status_code == 200
        assert _events(response.text) == [("error", {"code": "ai_upstream_error"})]
        assert "POST /api/recipes/explore/stream -> ai_upstream_error [no_usable_ideas]" in caplog.text

    def test_provider_error_is_an_error_event(self, client, fake_ai, caplog):
        fake_ai.responses = [httpx.Response(400, json={"error": {"message": "Model Not Exist"}})]
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            response = _stream(client)
        assert _events(response.text) == [("error", {"code": "ai_upstream_error"})]
        assert "[http_error]: AI returned HTTP 400: Model Not Exist" in caplog.text

    def test_unexpected_failure_is_an_internal_error_event(self, client, fake_ai, monkeypatch, caplog):
        from stock_manager.api import explore_services

        def boom(*args, **kwargs):
            raise RuntimeError("bug")

        monkeypatch.setattr(explore_services, "clean_idea", boom)
        with caplog.at_level(logging.ERROR, logger="stock_manager.api.routers.recipes"):
            response = _stream(client)
        assert _events(response.text) == [("error", {"code": "internal_error"})]
        assert "POST /api/recipes/explore/stream failed" in caplog.text

    def test_heartbeat_while_the_ai_works(self, client, fake_ai, monkeypatch):
        from stock_manager.api.routers import recipes

        monkeypatch.setattr(recipes, "SSE_HEARTBEAT_SECONDS", 0.05)
        reply = json.dumps({"ideas": [_idea("甲")]}, ensure_ascii=False)

        async def slow(request):
            await asyncio.sleep(0.3)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse_body(reply))

        monkeypatch.setattr(ai_client, "_transport", httpx.MockTransport(slow))
        kinds = [e for e, _ in _events(_stream(client).text)]
        assert kinds[0] == "ping" and kinds[-2:] == ["idea", "done"]

    def test_ai_off_is_503_before_the_stream(self, client):
        response = _stream(client)
        assert response.status_code == 503
        assert response.json() == {"code": "ai_unavailable"}

    def test_bad_inventory_ids_are_400(self, client, fake_ai):
        response = _stream(client, mode="structured", natural_language=None,
                           structured={"inventory_item_ids": [99999]})
        assert response.status_code == 400
        assert fake_ai.requests == []

    def test_bad_body_is_422(self, client, fake_ai):
        assert client.post("/api/recipes/explore/stream", json={"mode": "natural_language"}).status_code == 422


class TestExploreStreamService:
    """explore_stream itself: timing and partial replies."""

    def _run(self, consume):
        return asyncio.run(consume())

    def test_first_idea_is_yielded_before_the_reply_ends(self, fake_ai, monkeypatch):
        from stock_manager.api.explore_services import explore_stream

        gate = asyncio.Event()
        first = json.dumps(_idea("甲"), ensure_ascii=False)
        second = json.dumps(_idea("乙"), ensure_ascii=False)
        _use(monkeypatch, _streaming(_content('{"ideas": [' + first), gate,
                                     _content(", " + second + "]}"), DONE),
             first_token_timeout=2, idle_timeout=2, text_total_timeout=2)

        async def consume():
            seen = []
            async for kind, value in explore_stream([], natural_language="晚饭"):
                seen.append((kind, value.get("title")))
                if kind == "idea":
                    gate.set()  # the provider only continues once the first idea arrived
            return seen

        # MIN_IDEAS is not reached and nothing is wrong: no repair round.
        assert self._run(consume) == [("idea", "甲"), ("idea", "乙"), ("done", None)]

    def test_partial_idea_is_never_yielded(self, fake_ai, monkeypatch, caplog):
        from stock_manager.api.explore_services import explore_stream

        requests = _use(monkeypatch, _streaming(
            _content('{"ideas": [' + json.dumps(_idea("甲"), ensure_ascii=False) + ', {"title": "Egg"}'
                     + ', {"title": "乙", "desc'),
            _finish("length"), DONE,
        ))

        async def consume():
            return [(kind, value) async for kind, value in explore_stream([], natural_language="晚饭")]

        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            events = self._run(consume)
        assert [(k, v.get("title")) for k, v in events] == [("idea", "甲"), ("done", None)]
        assert len(requests) == 1  # a broken first round is not repaired, even with problems
        assert "fail truncated" in caplog.text

    def test_broken_first_round_without_ideas_raises_its_own_reason(self, fake_ai, monkeypatch):
        from stock_manager.api.explore_services import explore_ideas

        _use(monkeypatch, _streaming(_content('{"ideas": [{"title": "甲"'), 1.0), idle_timeout=0.1)
        with pytest.raises(AIUpstreamError) as info:
            asyncio.run(explore_ideas([], natural_language="晚饭"))
        assert info.value.reason == "timeout_idle"

    def test_failed_repair_keeps_ideas_already_sent(self, fake_ai, monkeypatch):
        from stock_manager.api.explore_services import explore_ideas

        first = json.dumps({"ideas": [_idea("甲"), _idea("Egg")]}, ensure_ascii=False)
        _use(monkeypatch,
             _streaming(_content(first), DONE),
             _streaming(_content('{"ideas": [' + json.dumps(_idea("乙"), ensure_ascii=False)
                                 + ', {"title": "x", "matched_ingredients": "y"}, {"t'), 1.0),
             idle_timeout=0.2)
        result = asyncio.run(explore_ideas([], natural_language="晚饭"))
        assert [i["title"] for i in result["ideas"]] == ["甲", "乙"]
        codes = [w["code"] for w in result["warnings"]]
        # The first round's drop warning stays (the repair failed); the
        # repair's own drop warnings are not added.
        assert codes == ["idea_dropped_wrong_language"]

    def test_unexpected_shape_is_validated_as_a_whole(self, fake_ai):
        from stock_manager.api.explore_services import explore_ideas

        fake_ai.reply = json.dumps({"ideas": {"a": 1}})
        with pytest.raises(AIUpstreamError) as info:
            asyncio.run(explore_ideas([], natural_language="晚饭"))
        assert info.value.reason == "no_usable_ideas"
        assert 'must be {"ideas": [...]}' in fake_ai.requests[1]["messages"][-1]["content"]

    def test_plain_mode_gives_the_same_ideas(self, fake_ai, monkeypatch):
        from stock_manager.api.explore_services import explore_ideas

        monkeypatch.setenv("AI_STREAM", "false")
        ai_client.reload_config()
        fake_ai.reply = json.dumps({"ideas": [_idea("甲"), _idea("乙"), _idea("丙")]}, ensure_ascii=False)
        result = asyncio.run(explore_ideas([], natural_language="晚饭"))
        assert [i["title"] for i in result["ideas"]] == ["甲", "乙", "丙"]
        assert "stream" not in fake_ai.requests[0]

    def test_repair_sees_the_raw_first_reply(self, fake_ai):
        from stock_manager.api.explore_services import explore_ideas

        first = '{"ideas": [{"title": "甲", "description": "x"}, {"title": "Egg"}]}'
        fake_ai.responses = [first, json.dumps({"ideas": [_idea("乙")]}, ensure_ascii=False)]
        asyncio.run(explore_ideas([], natural_language="晚饭"))
        assistant = fake_ai.requests[1]["messages"][2]
        assert assistant == {"role": "assistant", "content": first}


class TestExpandLogs:
    def test_rounds_are_labelled(self, client, fake_ai, caplog):
        fake_ai.responses = [
            json.dumps({"title": "Tomato Egg", "steps": ["Cook"]}),
            json.dumps({"title": "番茄炒蛋", "steps": ["炒"]}, ensure_ascii=False),
        ]
        with caplog.at_level(logging.INFO, logger="stock_manager.api.ai_client"):
            response = client.post("/api/recipes/explore/expand", json={"idea": {"title": "番茄炒蛋"}})
        assert response.status_code == 200
        labels = [r.getMessage().split(" ")[1] for r in caplog.records if r.getMessage().startswith("AI ")]
        assert labels == ["expand/first", "expand/repair"]

    def test_unusable_draft_reason(self, client, fake_ai, caplog):
        fake_ai.reply = json.dumps({"title": "番茄炒蛋", "steps": []}, ensure_ascii=False)
        with caplog.at_level(logging.WARNING, logger="stock_manager.api.ai_client"):
            response = client.post("/api/recipes/explore/expand", json={"idea": {"title": "番茄炒蛋"}})
        assert response.status_code == 502
        assert "[draft_unusable]: AI draft was unusable: steps is empty" in caplog.text


class TestEdges:
    def test_reply_that_never_streamed_is_validated_at_the_end(self, fake_ai, monkeypatch):
        """A chat_json that does not report text (e.g. a stub) still yields
        validated ideas, and the repair sees the reply as JSON."""
        from stock_manager.api import explore_services

        calls = []
        replies = [{"ideas": [_idea("甲"), _idea("Egg")]}, {"ideas": [_idea("乙")]}]

        async def stub(system, user, **kwargs):
            calls.append(kwargs)
            return replies[len(calls) - 1]

        monkeypatch.setattr(explore_services, "chat_json", stub)
        result = asyncio.run(explore_services.explore_ideas([], natural_language="晚饭"))
        assert [i["title"] for i in result["ideas"]] == ["甲", "乙"]
        assert json.loads(calls[1]["followup"][0]["content"]) == replies[0]

    def test_client_disconnect_stops_the_ai_work(self):
        from stock_manager.api.routers import recipes

        state = {"closed": False}

        async def events():
            try:
                yield "idea", {"title": "甲"}
                await asyncio.sleep(10)
            finally:
                state["closed"] = True

        async def run():
            stream = recipes._explore_events(events(), "/x")
            first = await stream.__anext__()
            await stream.aclose()  # what Starlette does when the client goes away
            return first

        assert asyncio.run(run()).startswith("event: idea\n")
        assert state["closed"]

    @pytest.mark.parametrize("response", [
        httpx.Response(400, json=["odd"]),
        httpx.Response(400, json={"error": {"message": "  "}}),
    ])
    def test_odd_error_bodies(self, monkeypatch, response):
        _use(monkeypatch, response)
        with pytest.raises(AIUpstreamError) as info:
            _chat()
        assert str(info.value).startswith("AI returned HTTP 400")

    def test_empty_plain_reply(self, monkeypatch):
        _use(monkeypatch, *(httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}) for _ in range(2)),
             stream=False)
        with pytest.raises(AIUpstreamError) as info:
            _chat()
        assert info.value.reason == "no_content"

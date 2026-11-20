"""Speech API and DeepSeek transport contract, with generated audio only."""

import asyncio
import logging
from email.parser import BytesParser
from email.policy import default
from struct import pack

import httpx
import pytest

from stock_manager.api import ai_client, asr_client

_TRANSCRIBE = "/api/speech/transcribe"
_CAPABILITIES = "/api/capabilities"
_SUCCESS = {"request_id": "request-42", "text": "Two bottles of milk", "duration_ms": 5230}


def _chunk(kind, payload):
    return kind + pack("<I", len(payload)) + payload + b"\x00" * (len(payload) % 2)


def _riff(*chunks):
    contents = b"WAVE" + b"".join(chunks)
    return b"RIFF" + pack("<I", len(contents)) + contents


def _wav(samples=40, *, rate=16000, channels=1, bits=16, encoding=1, **overrides):
    frame_size = channels * (bits // 8)
    fmt = pack(
        "<HHIIHH", encoding, channels, rate, overrides.get("byte_rate", rate * frame_size),
        overrides.get("frame_size", frame_size), bits,
    )
    return _riff(_chunk(b"fmt ", fmt), _chunk(b"JUNK", b"metadata!"), _chunk(b"data", b"\x00" * samples * frame_size))


def _page(flags, granule, packet, *, seq, stream=101):
    assert len(packet) < 255
    return (
        b"OggS\x00" + pack("<BQIII", flags, granule, stream, seq, 0)
        + bytes((1, len(packet))) + packet
    )


def _ogg(samples=48000, pre_skip=312, *, head=b"OpusHead", serial=101, end_flags=4):
    identification = head + pack("<BBHIhB", 1, 1, pre_skip, 48000, 0, 0)
    tags = b"OpusTags" + pack("<II", 0, 0)
    return (
        _page(2, 0, identification, seq=0)
        + _page(0, 0, tags, seq=1)
        + _page(end_flags, samples + pre_skip, b"\xf8\xff\xfe", seq=2, stream=serial)
    )


def _post(client, audio, feature=None):
    files = {"audio": ("untrusted-name.mp3", audio, "audio/mpeg")}
    if feature is not None:
        files["feature"] = (None, feature)
    return client.post(_TRANSCRIBE, files=files)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("AI_ASR_PROVIDER", "deepseek")
    monkeypatch.setenv("AI_BASE_URL", "https://asr.example.test/")
    monkeypatch.setenv("AI_API_KEY", "dummy-test-key")
    ai_client.reload_config()

    def install(*replies):
        calls = []

        def dispatch(request):
            index = len(calls)
            calls.append(request)
            reply = replies[index]
            if isinstance(reply, type) and issubclass(reply, httpx.RequestError):
                raise reply("private request details", request=request)
            return reply

        monkeypatch.setattr(asr_client, "_transport", httpx.MockTransport(dispatch))
        return calls

    return install


@pytest.mark.parametrize(("audio", "filename", "mime"), [
    (_wav(), "audio.wav", "audio/wav"),
    (_ogg(), "audio.ogg", "audio/ogg"),
])
def test_transcribes_with_exact_deepseek_contract(client, provider, caplog, audio, filename, mime):
    calls = provider(httpx.Response(200, json=_SUCCESS))
    with caplog.at_level(logging.INFO, logger=asr_client.__name__):
        response = _post(client, audio, feature="recipe_explore")
    assert response.status_code == 200
    assert response.json() == {"transcript": _SUCCESS["text"], "duration_ms": 5230}
    request, = calls
    assert request.method == "POST"
    assert str(request.url) == "https://asr.example.test/v1/tools/asr"
    assert request.headers["authorization"] == "Bearer dummy-test-key"
    ctype = request.headers["content-type"].encode("ascii")
    form = BytesParser(policy=default).parsebytes(b"Content-Type: " + ctype + b"\r\n\r\n" + request.content)
    part, = form.iter_parts()
    assert part.get_param("name", header="Content-Disposition") == "file"
    assert part.get_filename() == filename
    assert part.get_content_type() == mime
    assert part.get_payload(decode=True) == audio
    assert "feature=recipe_explore ok duration_ms=5230" in caplog.text
    assert _SUCCESS["text"] not in caplog.text
    assert "dummy-test-key" not in caplog.text


def test_wav_stereo_returns_warning(client, provider):
    calls = provider(httpx.Response(200, json=_SUCCESS))
    response = _post(client, _wav(channels=2))
    assert response.status_code == 200
    assert response.json() == {
        "transcript": _SUCCESS["text"], "duration_ms": 5230,
        "warnings": [{"code": "audio_stereo_left_only"}],
    }
    assert len(calls) == 1


@pytest.mark.parametrize("rate", [8000, 16000, 22050, 24000, 32000, 44100, 48000])
def test_wav_accepts_each_supported_rate(client, provider, rate):
    provider(httpx.Response(200, json=_SUCCESS))
    assert _post(client, _wav(rate=rate)).status_code == 200


@pytest.mark.parametrize("audio", [
    pytest.param(_wav(encoding=3), id="float-wav"),
    pytest.param(_wav(bits=8), id="pcm8"),
    pytest.param(_wav(bits=8, frame_size=2, byte_rate=32000), id="pcm8-with-pcm16-layout"),
    pytest.param(_wav(rate=12000), id="unsupported-rate"),
    pytest.param(_wav(channels=3), id="unsupported-channels"),
    pytest.param(_wav(byte_rate=1), id="inconsistent-byte-rate"),
    pytest.param(_wav(frame_size=1), id="inconsistent-frame-size"),
    pytest.param(_wav()[:-1], id="bad-riff-length"),
    pytest.param(_riff(b"fmt " + pack("<I", 256)), id="truncated-wav-chunk"),
    pytest.param(_riff(_chunk(b"fmt ", b"too short")), id="short-wav-format"),
    pytest.param(_riff(_chunk(b"data", b"12"), _chunk(b"data", b"34")), id="duplicate-wav-data"),
    pytest.param(_riff(_chunk(b"data", b"12")), id="missing-wav-format"),
    pytest.param(_wav(0), id="empty-wav-data"),
    pytest.param(_ogg(head=b"\x01vorbis!"), id="non-opus-ogg"),
    pytest.param(_ogg()[:26], id="truncated-ogg-header"),
    pytest.param(_ogg()[:-1], id="truncated-ogg-page"),
    pytest.param(_ogg(serial=102), id="multiple-ogg-streams"),
    pytest.param(_ogg(end_flags=0), id="missing-ogg-end"),
    pytest.param(_ogg() + b"tail", id="ogg-trailing-bytes"),
    pytest.param(_ogg(samples=-1), id="granule-before-pre-skip"),
    pytest.param(_ogg(samples=2**64 - 1 - 312), id="unknown-final-granule"),
    pytest.param(b"\x00\x00\x00\x18ftypM4A ", id="m4a"),
    pytest.param(b"\x1a\x45\xdf\xa3\x01\x02\x03\x04", id="webm"),
    pytest.param(b"ID3\x04\x00\x00\x00\x00\x00\x0f", id="mp3"),
])
def test_rejects_formats_before_upload(client, provider, audio):
    calls = provider()
    response = _post(client, audio)
    assert response.status_code == 422
    assert response.json()["code"] == "audio_format_unsupported"
    assert response.json()["params"] == {"accepted": ["wav_pcm16", "ogg_opus"]}
    assert calls == []


@pytest.mark.parametrize(("audio", "too_long"), [
    pytest.param(_wav(120 * 16000), False, id="wav-exact-limit"),
    pytest.param(_wav(120 * 16000 + 1), True, id="wav-one-frame-over"),
    pytest.param(_ogg(120 * 48000), False, id="ogg-exact-limit-after-pre-skip"),
    pytest.param(_ogg(120 * 48000 + 1), True, id="ogg-one-sample-over"),
])
def test_duration_boundary(client, provider, audio, too_long):
    replies = () if too_long else (httpx.Response(200, json=_SUCCESS),)
    calls = provider(*replies)
    response = _post(client, audio)
    if too_long:
        assert response.status_code == 422
        assert response.json()["code"] == "audio_too_long"
        assert response.json()["params"] == {"max_seconds": 120}
        assert calls == []
    else:
        assert response.status_code == 200
        assert len(calls) == 1


def test_post_rejects_missing_audio_locale_and_oversized_file(client, provider):
    calls = provider()
    missing = client.post(_TRANSCRIBE, files={"feature": (None, "stock_intake")})
    locale = client.post(_TRANSCRIBE, files={
        "audio": ("clip.wav", _wav()), "locale": (None, "stock_intake"),
    })
    oversized = _post(client, b"x" * 8_388_609)
    for response in (missing, locale):
        assert response.status_code == 422
        assert response.json()["code"] == "audio_upload_invalid"
    assert oversized.status_code == 413
    assert oversized.json()["code"] == "audio_too_large"
    assert calls == []


@pytest.mark.parametrize(("status", "out_status", "code", "count"), [
    (400, 422, "audio_format_unsupported", 1),
    (408, 502, "asr_upstream_error", 1),
    (413, 413, "audio_too_large", 1),
    (429, 502, "asr_upstream_error", 2),
    (500, 502, "asr_upstream_error", 1),
    (503, 502, "asr_upstream_error", 2),
    (504, 502, "asr_upstream_error", 1),
])
def test_maps_provider_status_codes(client, provider, status, out_status, code, count):
    calls = provider(*(httpx.Response(status) for _ in range(count)))
    response = _post(client, _wav())
    assert response.status_code == out_status
    assert response.json()["code"] == code
    assert len(calls) == count


@pytest.mark.parametrize("status", [429, 503])
def test_retry_can_succeed(client, provider, status):
    calls = provider(httpx.Response(status), httpx.Response(200, json=_SUCCESS))
    assert _post(client, _wav()).status_code == 200
    assert len(calls) == 2


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_does_not_retry_transport_errors(client, provider, caplog, failure):
    calls = provider(failure)
    response = _post(client, _wav())
    assert response.status_code == 502
    assert response.json()["code"] == "asr_upstream_error"
    assert len(calls) == 1
    assert "private request details" not in caplog.text


def test_enforces_asr_deadline(client, provider, monkeypatch):
    async def stalled(request):
        await asyncio.sleep(1)
        pytest.fail("speech transcription timeout was not applied")

    monkeypatch.setenv("AI_ASR_TIMEOUT_SECONDS", "0.01")
    ai_client.reload_config()
    monkeypatch.setattr(asr_client, "_transport", httpx.MockTransport(stalled))
    response = _post(client, _wav())
    assert response.status_code == 502
    assert response.json()["code"] == "asr_upstream_error"


@pytest.mark.parametrize("reply", [
    httpx.Response(200, text="not-json"),
    httpx.Response(200, json=[]),
    httpx.Response(200, json={"text": 7, "duration_ms": 5000}),
    httpx.Response(200, json={"text": "private transcript", "duration_ms": True}),
    httpx.Response(200, json={"text": "private transcript", "duration_ms": -1}),
])
def test_rejects_malformed_success_without_logging_provider_body(client, provider, caplog, reply):
    calls = provider(reply)
    response = _post(client, _wav())
    assert response.status_code == 502
    assert response.json()["code"] == "asr_upstream_error"
    assert len(calls) == 1
    assert "private transcript" not in caplog.text
    assert "not-json" not in caplog.text


def test_logs_provider_diagnostic_without_upload_or_transcript(client, provider, caplog):
    encoded = "aB9+" * 40
    diagnostic = "cannot read audio: data:audio/wav;base64," + encoded + " " + "x " * 200 + "truncated marker"
    provider(httpx.Response(400, json={"error": {"message": diagnostic}, "text": "private transcript"}))
    response = _post(client, _wav(), feature="stock_intake")
    assert response.status_code == 422
    assert "provider HTTP 400: cannot read audio: [redacted]" in caplog.text
    assert "feature=stock_intake" in caplog.text
    assert "truncated marker" not in caplog.text
    assert encoded not in caplog.text
    assert "private transcript" not in caplog.text
    error_line, = [r.getMessage() for r in caplog.records if r.name == asr_client.__name__]
    assert len(error_line.split("HTTP 400: ", 1)[1]) == 200


def test_provider_error_without_diagnostic_does_not_log_body(client, provider, caplog):
    provider(httpx.Response(500, json={"text": "private transcript"}))
    assert _post(client, _wav()).status_code == 502
    assert "provider HTTP 500" in caplog.text
    assert "private transcript" not in caplog.text


@pytest.mark.parametrize(("vendor", "key", "available"), [
    ("none", "dummy-test-key", False),
    ("deepseek", "", False),
    ("unknown", "dummy-test-key", False),
    ("deepseek", "dummy-test-key", True),
])
def test_capability_requires_enabled_provider_and_key(client, monkeypatch, vendor, key, available):
    monkeypatch.setenv("AI_ASR_PROVIDER", vendor)
    monkeypatch.setenv("AI_API_KEY", key)
    ai_client.reload_config()
    assert client.get(_CAPABILITIES).json()["ai"] == {"text": False, "vision": False, "asr": available}
    if not available:
        response = client.post(_TRANSCRIBE)
        assert response.status_code == 503
        assert response.json()["code"] == "asr_unavailable"


@pytest.mark.parametrize("timeout", ["nan", "inf", "-5", "oops"])
def test_invalid_timeout_disables_asr_only(timeout):
    config = ai_client.load_config({
        "AI_ASR_PROVIDER": "deepseek", "AI_ASR_TIMEOUT_SECONDS": timeout,
        "AI_RECIPE_ENABLED": "true", "AI_API_KEY": "dummy-test-key",
    })
    assert not config.asr_available
    assert config.available


def test_default_asr_is_disabled_and_route_requires_token(client):
    assert client.get(_CAPABILITIES).json()["ai"]["asr"] is False
    assert client.post(_TRANSCRIBE, headers={"Authorization": ""}).status_code == 401


def test_openapi_describes_only_supported_fields(client):
    operation = client.get("/openapi.json").json()["paths"][_TRANSCRIBE]["post"]
    form = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert form["required"] == ["audio"]
    assert set(form["properties"]) == {"audio", "feature"}
    assert form["additionalProperties"] is False

"""The speech upload is bounded before any provider receives it."""

import asyncio
import tempfile

import pytest
from starlette.requests import Request

from stock_manager.api.errors import APIError
from stock_manager.api.uploads import read_audio_upload

_START = b'--speech\r\nContent-Disposition: form-data; name="audio"; filename="clip.wav"\r\n\r\n'
_END = b"\r\n--speech--\r\n"
_LIMIT = 8_388_608


def _read(*chunks, more_body=False, extra_headers=()):
    pending = iter(chunks)

    async def receive():
        try:
            chunk = next(pending)
        except StopIteration:
            if more_body:
                pytest.fail("the server read beyond the rejected chunk")
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.request", "body": chunk, "more_body": True}

    scope = {
        "type": "http",
        "headers": [(b"content-type", b"multipart/form-data; boundary=speech"), *extra_headers],
    }
    return asyncio.run(read_audio_upload(Request(scope, receive)))


def test_audio_accepts_exact_size_limit_in_memory(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("audio upload opened a temporary file")

    for name in ("TemporaryFile", "NamedTemporaryFile", "SpooledTemporaryFile", "mkstemp"):
        monkeypatch.setattr(tempfile, name, forbidden)
    audio = b"x" * _LIMIT
    upload = _read(_START[:20], _START[20:], audio, _END)
    assert upload.data == audio
    assert upload.feature is None


def test_audio_rejects_extra_byte_without_reading_next_chunk():
    with pytest.raises(APIError) as error:
        _read(_START, b"x" * (_LIMIT + 1), more_body=True)
    assert error.value.status_code == 413
    assert error.value.code == "audio_too_large"
    assert error.value.params == {"max_bytes": _LIMIT}


def test_audio_rejects_oversized_content_length_before_reading():
    with pytest.raises(APIError) as error:
        _read(more_body=True, extra_headers=[(b"content-length", b"8454145")])
    assert error.value.status_code == 413
    assert error.value.code == "audio_too_large"


def test_audio_caps_total_streamed_request():
    with pytest.raises(APIError) as error:
        _read(_START, b"x" * _LIMIT, _END, b"x" * (64 * 1024), more_body=True)
    assert error.value.status_code == 413
    assert error.value.code == "audio_too_large"


@pytest.mark.parametrize("body", [
    _END,
    _START + _END,
    _START + b"truncated",
    _START + b"audio\r\n" + _START + b"duplicate" + _END,
    _START + b'audio\r\n--speech\r\nContent-Disposition: form-data; name="feature"\r\n\r\nunknown' + _END,
    _START + b'audio\r\n--speech\r\nContent-Disposition: form-data; name="locale"\r\n\r\nen' + _END,
    _START + b'audio\r\n--speech\r\nContent-Disposition: form-data; name="feature"\r\n\r\n\xff' + _END,
    _START + b'audio\r\n--speech\r\nContent-Disposition: form-data; name="feature"\r\n\r\n' + b"x" * 257 + _END,
])
def test_audio_rejects_malformed_multipart(body):
    with pytest.raises(APIError) as error:
        _read(body)
    assert error.value.status_code == 422
    assert error.value.code == "audio_upload_invalid"


def test_audio_reads_optional_form_fields():
    upload = _read(
        _START, b"audio",
        b'\r\n--speech\r\nContent-Disposition: form-data; name="feature"\r\n\r\nstock_intake',
        _END,
    )
    assert upload.data == b"audio"
    assert upload.feature == "stock_intake"

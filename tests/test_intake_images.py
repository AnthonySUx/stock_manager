"""Image intake tests with synthetic uploads and a mocked AI provider."""

import asyncio
import base64
import json
import logging
from datetime import date, timedelta

import httpx
import pytest

from stock_manager.api import ai_client, intake_services, uploads
from stock_manager.api.category_services import get_category_by_slug
from stock_manager.api.errors import APIError
from stock_manager.api.intake_schemas import ParseDraftRequest
from stock_manager.api.uploads import image_mime

JPEG = b"\xff\xd8\xffsynthetic-image"
PNG = b"\x89PNG\r\n\x1a\nsynthetic-image"
WEBP = b"RIFF\x01\x02\x03\x04WEBPsynthetic-image"
PARSE = "/api/intake/parse"


@pytest.fixture
def fake_vision(fake_ai, monkeypatch):
    monkeypatch.setenv("AI_VISION_ENABLED", "true")
    ai_client.reload_config()
    return fake_ai


@pytest.mark.parametrize("detail", ["low", "high", "auto"])
def test_vision_config_reads_detail(detail):
    config = ai_client.load_config({
        "AI_RECIPE_ENABLED": "true", "AI_API_KEY": "test-key",
        "AI_VISION_ENABLED": " TRUE ", "AI_IMAGE_DETAIL": detail,
    })
    assert config.vision_available and config.image_detail == detail


def test_invalid_image_detail_disables_only_vision():
    config = ai_client.load_config({
        "AI_RECIPE_ENABLED": "true", "AI_API_KEY": "test-key",
        "AI_VISION_ENABLED": "true", "AI_IMAGE_DETAIL": "invalid",
    })
    assert config.available
    assert not config.vision_available
    assert config.image_detail == "high"


def test_capabilities_require_vision_flag_and_working_ai(client, fake_ai, monkeypatch):
    url = "/api/capabilities"
    assert client.get(url).json()["ai"] == {"text": True, "vision": False, "asr": False}

    monkeypatch.setenv("AI_VISION_ENABLED", "true")
    ai_client.reload_config()
    assert client.get(url).json()["ai"] == {"text": True, "vision": True, "asr": False}

    monkeypatch.setenv("AI_API_KEY", "")
    ai_client.reload_config()
    assert client.get(url).json()["ai"] == {"text": False, "vision": False, "asr": False}


@pytest.mark.parametrize(("data", "mime"), [
    (JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"),
])
def test_image_mime_uses_valid_file_signatures(data, mime):
    assert image_mime(data, 0) == mime


@pytest.mark.parametrize("data", [b"", b"GIF89a", b"RIFFxxxxWAVE", b"xxxx1234WEBP", b"RIFFWEBP"])
def test_image_mime_rejects_unsupported_signatures(data):
    with pytest.raises(APIError) as raised:
        image_mime(data, 3)
    assert raised.value.status_code == 422
    assert raised.value.code == "intake_image_type_unsupported"
    assert raised.value.params == {"index": 3}


def test_openapi_exposes_json_and_multipart_parse(client):
    api = client.get("/openapi.json").json()
    content = api["paths"][PARSE]["post"]["requestBody"]["content"]
    assert set(content) == {"application/json", "multipart/form-data"}
    text = content["application/json"]["schema"]
    assert set(text["required"]) == {"input", "draft"}
    image = content["multipart/form-data"]["schema"]
    assert set(image["required"]) == {"payload", "images"}
    files = image["properties"]["images"]
    assert files["items"] == {"type": "string", "format": "binary"}
    assert (files["minItems"], files["maxItems"]) == (1, 8)
    payload = image["properties"]["payload"]
    assert payload["type"] == "string"
    assert payload["contentMediaType"] == "application/json"
    assert set(payload["contentSchema"]["properties"]) == {"draft", "context"}
    assert "IntakeCandidate" in api["components"]["schemas"]


@pytest.mark.parametrize("content_type", [None, "application/json; charset=utf-8", "application/vnd.app+json"])
def test_text_parse_still_accepts_existing_json_media_types(client, fake_ai, content_type):
    fake_ai.reply = '{"operations": [{"op": "add", "candidate": {"name": "Milk"}}]}'
    response = client.post(
        PARSE,
        content=json.dumps({
            "input": {"type": "text", "text": "Milk"},
            "draft": {"items": []},
            "context": {"locale": "en"},
        }),
        headers={"Content-Type": content_type} if content_type else None,
    )
    assert response.status_code == 200, response.text
    operation = response.json()["operations"][0]
    assert "source" not in operation
    assert operation["candidate"]["source"] == {"input_kind": "text", "image_index": None, "span": None}


@pytest.mark.parametrize(("body", "error_type", "loc"), [
    (b"", "missing", ["body"]),
    (b"null", "missing", ["body"]),
    (b"{", "json_invalid", ["body", 1]),
    (b"{}", "missing", ["body", "draft"]),
])
def test_text_parse_retains_request_validation_errors(client, fake_ai, body, error_type, loc):
    response = client.post(PARSE, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert any(error["type"] == error_type and error["loc"] == loc for error in response.json()["detail"])
    assert fake_ai.requests == []


def _source(kind="receipt", index=0, **fields):
    return {"input_kind": kind, "image_index": index, **fields}


def _image_add(*, name="Milk", source=None, **fields):
    op = {"op": "add", "candidate": {"name": name, **fields}}
    if source is not None:
        op["source"] = source
    return op


def test_image_prompt_and_operations_use_validated_source(db_session, fake_vision):
    raw = {
        "draft": {"items": [{
            "temporary_id": "cand_12345678", "name": "Milk", "confidence": 1,
            "source": {"input_kind": "text"}, "notes": "not sent",
        }, {
            "temporary_id": "cand_87654321", "name": "Eggs", "confidence": 1,
            "source": {"input_kind": "text"},
        }]},
        "context": {"locale": "en", "purchase_date": "2026-11-20"},
    }
    request = ParseDraftRequest.model_validate(raw)
    prepared = intake_services.prepare_parse(db_session, request, None)
    key = "cand_12345678"
    fake_vision.reply = json.dumps({"operations": [
        _image_add(name="Eggs", source=_source(span="original", extra="ignored")),
        {"op": "update", "temporary_id": key, "changes": {"notes": "Updated"},
         "source": _source("product_closeup", 1)},
        {"op": "clarify", "temporary_ids": [key], "question_code": "ambiguous_target",
         "question": "Which milk?", "source": _source("product_overview", 2)},
        {"op": "delete", "temporary_id": "cand_87654321", "reason_code": "duplicate",
         "source": _source("receipt", 0)},
    ]})
    images = [{"data": image, "mime": mime, "detail": "low"} for image, mime in (
        (JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"),
    )]
    result = asyncio.run(intake_services.parse_images(db_session, request, prepared, images))

    assert [op["op"] for op in result["operations"]] == ["add", "update", "clarify", "delete"]
    assert [op["source"]["image_index"] for op in result["operations"]] == [0, 1, 2, 0]
    assert result["operations"][0]["candidate"]["source"] == _source(span="original")
    assert result["operations"][2]["source"]["input_kind"] == "product_overview"
    payload = fake_vision.requests[0]
    assert payload["response_format"] == {"type": "json_object"}
    assert not payload.get("stream")
    system, user = payload["messages"]
    assert "classify each image" in system["content"]
    assert "overlap" in system["content"]
    assert "one long receipt" in system["content"]
    assert "Write item names and questions in English" in system["content"]
    assert "Keep brand names exactly as printed on the packaging" in system["content"]
    assert "Mark dates read from an image as printed. Never use stated for image dates." in system["content"]
    prompt, *parts = user["content"]
    context = json.loads(prompt["text"])
    assert context["image_count"] == 3 and context["purchase_date"] == "2026-11-20"
    assert "notes" not in context["draft"][0]
    assert len(context["calendar"]) == 21
    assert parts == [
        {"type": "image_url", "image_url": {
            "url": f"data:{image['mime']};base64,{base64.b64encode(image['data']).decode()}",
            "detail": "low",
        }}
        for image in images
    ]


@pytest.mark.parametrize("source", [
    None, {}, {"input_kind": "receipt"}, _source(index=-1), _source(index=1), _source(index=True),
    _source(index="0"), _source("text"), _source(["receipt"]),
])
def test_invalid_image_source_drops_operation(db_session, fake_vision, source):
    request = ParseDraftRequest.model_validate({"draft": {"items": []}})
    prepared = intake_services.prepare_parse(db_session, request, None)
    fake_vision.reply = json.dumps({"operations": [_image_add(source=source)]})
    result = asyncio.run(intake_services.parse_images(
        db_session, request, prepared, [{"data": JPEG, "mime": "image/jpeg"}],
    ))
    assert result["operations"] == []
    assert result["warnings"] == [
        {"code": "op_invalid", "params": {"index": "0"}},
        {"code": "ops_dropped", "params": {"count": "1"}},
    ]


@pytest.mark.parametrize("provider_reply", ["invalid_json", "metadata", "transport"])
def test_image_call_excludes_provider_echoes_from_logs(fake_vision, caplog, provider_reply):
    echo = "PRIVATE_UPLOAD_CONTENT"
    if provider_reply == "invalid_json":
        fake_vision.reply = echo
    elif provider_reply == "transport":
        fake_vision.responses = [httpx.ConnectError(echo), httpx.ConnectError(echo)]
    else:
        fake_vision.responses = [httpx.Response(200, json={
            "choices": [{"message": {"content": '{"operations": []}'}, "finish_reason": echo}],
            "usage": {"prompt_tokens": echo},
        })]

    async def call():
        return await ai_client.chat_json(
            "Return json", "Draft", images=[{"data": echo.encode(), "mime": "image/jpeg"}],
            label="intake/images",
        )

    with caplog.at_level(logging.INFO):
        if provider_reply == "metadata":
            assert asyncio.run(call()) == {"operations": []}
        else:
            with pytest.raises(ai_client.AIUpstreamError) as raised:
                asyncio.run(call())
            assert echo not in str(raised.value)
    assert "AI intake/images" in caplog.text
    assert echo not in caplog.text
    assert base64.b64encode(echo.encode()).decode() not in caplog.text


def _multipart(*images, payload='{"draft":{"items":[]},"context":{"locale":"en"}}'):
    fields = [("payload", (None, payload))] if payload is not None else []
    return fields + [
        ("images", (f"image-{index}.bin", image, "application/octet-stream"))
        for index, image in enumerate(images)
    ]


def test_image_http_error_logs_provider_reason(client, fake_vision, caplog):
    fake_vision.responses = [httpx.Response(400, json={
        "error": {"message": "image_url is not supported"},
    })]

    response = client.post(PARSE, files=_multipart(JPEG))

    assert response.status_code == 502
    assert response.json() == {"code": "ai_upstream_error"}
    assert "AI returned HTTP 400: image_url is not supported" in caplog.text


def test_image_http_error_strips_data_uris_before_truncating(client, fake_vision, caplog):
    encoded = "/9j/" + "ABCD" * 70
    fake_vision.responses = [httpx.Response(400, json={
        "error": {"message": f"data:image/jpeg;base64,{encoded} was rejected. DATA:text/plain,secret"},
    })]

    response = client.post(PARSE, files=_multipart(JPEG))

    assert response.status_code == 502
    assert "was rejected" in caplog.text
    assert "data:image" not in caplog.text
    assert "DATA:text" not in caplog.text
    assert "secret" not in caplog.text
    assert encoded[:40] not in caplog.text


def test_image_http_error_redacts_bare_base64_and_limits_message(client, fake_vision, caplog):
    encoded = "aB+/0123" * 12 + "qR-_"
    explanation = "Could not process this image. " * 12
    fake_vision.responses = [httpx.Response(400, json={
        "error": {"message": f"{encoded} {explanation.strip()}"},
    })]

    response = client.post(PARSE, files=_multipart(JPEG))

    assert response.status_code == 502
    assert "aB+/0123" not in caplog.text
    details = [
        record.getMessage().split("AI returned HTTP 400: ", 1)[1]
        for record in caplog.records if "AI returned HTTP 400: " in record.getMessage()
    ]
    assert details
    assert all(len(detail) == 200 and detail.startswith("[redacted] Could not process") for detail in details)


@pytest.mark.parametrize("source", ["stated", "printed"])
def test_image_add_and_update_treat_model_dates_as_suggestions(client, fake_vision, db_session, source):
    purchase = date.today()
    model_date = (purchase + timedelta(days=12)).isoformat()
    dairy = get_category_by_slug(db_session, "dairy")
    payload = {
        "draft": {"items": [{
            "temporary_id": "cand_12345678", "name": "Milk", "confidence": 1,
            "category_id": dairy.id, "source": {"input_kind": "text"},
        }]},
        "context": {"locale": "en", "purchase_date": purchase.isoformat()},
    }
    dates = {"unopened_expiration_date": model_date, "expiration_source": source}
    image_source = _source("product_closeup")
    fake_vision.reply = json.dumps({"operations": [
        _image_add(source=image_source, **dates),
        {"op": "update", "temporary_id": "cand_12345678", "source": image_source, "changes": dates},
    ]})

    response = client.post(PARSE, files=_multipart(JPEG, payload=json.dumps(payload)))

    assert response.status_code == 200, response.text
    body = response.json()
    add, update = body["operations"]
    assert add["candidate"]["unopened_expiration_date"] is None
    assert add["candidate"]["suggested_unopened_expiration_date"] == model_date
    assert add["candidate"]["expiration_source"] == "estimated"
    assert add["candidate"]["warnings"] == [{"code": "expiration_moved_to_suggested", "params": {}}]
    assert update["changes"] == {
        "unopened_expiration_date": None,
        "suggested_unopened_expiration_date": (purchase + timedelta(days=7)).isoformat(),
        "expiration_source": "estimated",
    }
    assert body["warnings"] == [
        {"code": "expiration_date_inferred", "params": {"basis": "category_default"}},
        {"code": "ai_expiration_ignored", "params": {"date": model_date}},
    ]


def test_image_cannot_replace_previously_stated_date(client, fake_vision):
    purchase = date.today()
    existing_date = (purchase + timedelta(days=3)).isoformat()
    model_date = (purchase + timedelta(days=9)).isoformat()
    payload = {"draft": {"items": [{
        "temporary_id": "cand_12345678", "name": "Milk", "confidence": 1,
        "source": {"input_kind": "text"}, "unopened_expiration_date": existing_date,
        "expiration_source": "stated",
    }]}}
    fake_vision.reply = json.dumps({"operations": [{
        "op": "update", "temporary_id": "cand_12345678", "source": _source(),
        "changes": {"unopened_expiration_date": model_date, "expiration_source": "stated"},
    }]})

    response = client.post(PARSE, files=_multipart(JPEG, payload=json.dumps(payload)))

    assert response.status_code == 200, response.text
    assert response.json()["operations"][0]["changes"] == {
        "unopened_expiration_date": existing_date, "expiration_source": "stated",
    }
    assert response.json()["warnings"] == [
        {"code": "ai_expiration_ignored", "params": {"date": model_date}},
    ]


def test_multipart_uses_signatures_and_configured_detail(client, fake_vision, monkeypatch):
    monkeypatch.setenv("AI_IMAGE_DETAIL", "auto")
    ai_client.reload_config()
    fake_vision.reply = json.dumps({"operations": [
        _image_add(source=_source("product_overview", 2)),
    ]})

    response = client.post(PARSE, files=_multipart(JPEG, PNG, WEBP))

    assert response.status_code == 200, response.text
    operation = response.json()["operations"][0]
    expected = {"input_kind": "product_overview", "image_index": 2, "span": None}
    assert operation["source"] == operation["candidate"]["source"] == expected
    assert operation["candidate"]["name"] == "Milk"
    payload = fake_vision.requests[0]
    assert payload["response_format"] == {"type": "json_object"} and not payload.get("stream")
    images = payload["messages"][1]["content"][1:]
    assert [part["image_url"]["detail"] for part in images] == ["auto"] * 3
    assert [part["image_url"]["url"].split(";", 1)[0] for part in images] == [
        "data:image/jpeg", "data:image/png", "data:image/webp",
    ]


def test_accepts_eight_images_at_maximum_per_file_size(client, fake_vision):
    fake_vision.reply = '{"operations":[]}'
    # One file uses the exact per-file limit. The request also uses all eight slots.
    last = JPEG.ljust(uploads.MAX_IMAGE_BYTES, b"x")
    response = client.post(PARSE, files=_multipart(*([JPEG] * 7), last))
    assert response.status_code == 200, response.text
    prompt, *images = fake_vision.requests[0]["messages"][1]["content"]
    assert json.loads(prompt["text"])["image_count"] == len(images) == 8
    assert {part["image_url"]["detail"] for part in images} == {"high"}


@pytest.mark.parametrize(("images", "code", "params"), [
    ([], "intake_images_missing", {}),
    ([JPEG] * 9, "intake_images_too_many", {"max": 8}),
    ([JPEG, b"GIF89a"], "intake_image_type_unsupported", {"index": 1}),
])
def test_image_limits_and_type_are_checked_before_ai(client, fake_vision, images, code, params):
    response = client.post(PARSE, files=_multipart(*images))
    assert response.status_code == 422
    assert response.json()["code"] == code
    assert response.json()["params"] == params
    assert fake_vision.requests == []


def test_ignores_claimed_mime_when_signature_is_unsupported(client, fake_vision):
    response = client.post(PARSE, files=[
        ("payload", (None, '{"draft":{"items":[]}}')),
        ("images", ("looks-valid.png", b"not a PNG image", "image/png")),
    ])
    assert response.status_code == 422
    assert response.json()["code"] == "intake_image_type_unsupported"
    assert response.json()["params"] == {"index": 0}
    assert fake_vision.requests == []


@pytest.mark.parametrize("files", [
    _multipart(JPEG, payload=None),
    _multipart(JPEG, payload='{"draft":'),
    _multipart(JPEG, payload="[]"),
    _multipart(JPEG, payload="x" * (256 * 1024 + 1)),
    _multipart(JPEG) + [("payload", (None, "{}"))],
    _multipart(JPEG) + [("unexpected", (None, ""))],
    _multipart(JPEG) + [("unexpected", ("file.jpg", JPEG))],
    _multipart(JPEG) + [("images", (None, "not a file"))],
])
def test_malformed_multipart_fields_return_422(client, fake_vision, files):
    response = client.post(PARSE, files=files)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "intake_multipart_invalid"
    assert fake_vision.requests == []


@pytest.mark.parametrize(("content_type", "body"), [
    ("multipart/form-data", b""),
    ("multipart/form-data; boundary=example", b"--not-the-boundary\r\n"),
    ("multipart/form-data; boundary=example", b"--example\r\nContent-Dispos"),
    ("multipart/form-data; boundary=example",
     b'--example\r\nContent-Disposition: form-data; name="images"; filename="file.jpg"\r\n\r\n'
     + JPEG + b"\r\n--example-"),
    ("multipart/form-data; boundary=example", b"--example\r\nContent-Type: image/jpeg\r\n\r\n"),
])
def test_malformed_multipart_framing_returns_422(client, fake_vision, content_type, body):
    response = client.post(PARSE, content=body, headers={"Content-Type": content_type})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "intake_multipart_invalid"
    assert fake_vision.requests == []


def test_multipart_uses_shared_draft_and_context_validation(client, fake_vision):
    response = client.post(PARSE, files=_multipart(JPEG, payload='{"draft":{"items":[{}]}}'))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][:4] == ["body", "payload", "draft", "items"]

    response = client.post(PARSE, files=_multipart(
        JPEG, payload='{"draft":{"items":[]},"context":{"timezone":"Not/AZone"}}',
    ))
    assert response.status_code == 422
    assert response.json()["code"] == "intake_timezone_invalid"
    assert fake_vision.requests == []


def test_image_reply_without_operations_is_502(client, fake_vision):
    fake_vision.reply = '{"unparsed_fragments":[]}'
    response = client.post(PARSE, files=_multipart(JPEG))
    assert response.status_code == 502
    assert response.json() == {"code": "ai_upstream_error"}


def test_large_image_never_creates_temp_files_or_writes_db(client, db_session, fake_vision, monkeypatch, caplog):
    import tempfile
    from starlette import formparsers

    from stock_manager.api.models import Category, Item, RestockItem

    models = (Category, Item, RestockItem)
    before = [db_session.query(model).count() for model in models]

    def forbidden(*args, **kwargs):
        pytest.fail("image parsing must not persist bytes or commit")

    for name in ("SpooledTemporaryFile", "TemporaryFile", "NamedTemporaryFile"):
        monkeypatch.setattr(tempfile, name, forbidden)
    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", forbidden)
    monkeypatch.setattr(db_session, "commit", forbidden)
    fake_vision.reply = '{"operations":[]}'
    filename = "PRIVATE_FILENAME.jpg"
    image = JPEG + b"PRIVATE_IMAGE_MARKER".ljust(1024 * 1024, b"x")

    with caplog.at_level(logging.INFO):
        response = client.post(PARSE, files=[
            ("payload", (None, '{"draft":{"items":[]}}')),
            ("images", (filename, image)),
        ])
    assert response.status_code == 200, response.text
    assert before == [db_session.query(model).count() for model in models]
    assert f"count=1 total_bytes={len(image)}" in caplog.text
    assert filename not in caplog.text and "PRIVATE_IMAGE_MARKER" not in caplog.text
    assert base64.b64encode(image[:60]).decode() not in caplog.text


def _stream_post(app_client, chunks, **headers):
    seen = []

    async def content():
        for index, chunk in enumerate(chunks):
            seen.append(index)
            yield chunk

    async def post():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_client.app),
            base_url="http://testserver", headers=app_client.headers,
        ) as client:
            return await client.post(PARSE, content=content(), headers={
                "Content-Type": 'multipart/form-data; boundary="example"', **headers,
            })

    return asyncio.run(post()), seen


def _part_header(name, filename=None):
    suffix = f'; filename="{filename}"' if filename is not None else ""
    return f'--example\r\nContent-Disposition: form-data; name="{name}"{suffix}\r\n\r\n'.encode()


def test_vision_off_does_not_read_the_body(client, fake_ai):
    response, seen = _stream_post(client, [b"unread body"])
    assert response.status_code == 503
    assert response.json() == {"code": "ai_vision_unavailable"}
    assert not seen and not fake_ai.requests


def test_content_length_over_total_limit_rejects_before_body(client, fake_vision):
    response, seen = _stream_post(
        client, [b"unread body"], **{"Content-Length": str(42_270_720 + 1)},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "intake_request_too_large"
    assert response.json()["params"] == {"max_bytes": 42_270_720}
    assert not seen and not fake_vision.requests


def test_invalid_content_length_is_rejected_without_reading_body(client, fake_vision):
    response, seen = _stream_post(client, [b"unread body"], **{"Content-Length": "-1"})
    assert response.status_code == 422
    assert response.json()["code"] == "intake_multipart_invalid"
    assert not seen and not fake_vision.requests


def test_duplicate_content_disposition_rejects_part_before_reading_file(client, fake_vision):
    payload = _part_header("payload") + b'{"draft":{"items":[]}}\r\n'
    header = (
        b'--example\r\nContent-Disposition: form-data; name="images"; filename="test.jpg"\r\n'
        b'content-disposition: form-data; name="images"; filename="test.jpg"\r\n\r\n'
    )
    response, seen = _stream_post(client, [payload + header, JPEG + b"\r\n--example--\r\n"])
    assert response.status_code == 422
    assert response.json()["code"] == "intake_multipart_invalid"
    assert seen == [0] and not fake_vision.requests


@pytest.mark.parametrize("claimed_length", [None, "1"])
def test_actual_total_limit_stops_reading_even_with_missing_or_false_length(
    client, fake_vision, monkeypatch, claimed_length,
):
    first = _part_header("images", "test.jpg") + JPEG
    maximum = len(first) + 5
    monkeypatch.setattr(uploads, "MAX_REQUEST_BYTES", maximum)
    headers = {"Content-Length": claimed_length} if claimed_length is not None else {}
    response, seen = _stream_post(client, [first, b"123456", b"unread tail"], **headers)
    assert response.status_code == 413
    assert response.json()["code"] == "intake_request_too_large"
    assert response.json()["params"] == {"max_bytes": maximum}
    assert seen == [0, 1] and not fake_vision.requests


def test_file_size_limit_stops_reading_after_offending_chunk(client, fake_vision, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_IMAGE_BYTES", 128)
    first = _part_header("images", "test.jpg") + JPEG.ljust(128, b"x")
    response, seen = _stream_post(client, [first, b"x", b"unread tail"])
    assert response.status_code == 422
    assert response.json()["code"] == "intake_image_too_large"
    assert response.json()["params"] == {"index": 0, "max_bytes": 128}
    assert seen == [0, 1] and not fake_vision.requests


def test_bad_signature_rejects_after_first_twelve_bytes(client, fake_vision):
    first = _part_header("images", "fake.jpg") + b"0123456"
    response, seen = _stream_post(client, [first, b"789ab", b"unread tail"])
    assert response.status_code == 422
    assert response.json()["code"] == "intake_image_type_unsupported"
    assert response.json()["params"] == {"index": 0}
    assert seen == [0, 1] and not fake_vision.requests


def test_ninth_image_is_rejected_before_its_body(client, fake_vision):
    before = (_part_header("images", "test.jpg") + JPEG + b"\r\n") * 8
    response, seen = _stream_post(client, [before, _part_header("images", "ninth.jpg"), b"unread file"])
    assert response.status_code == 422
    assert response.json()["code"] == "intake_images_too_many"
    assert response.json()["params"] == {"max": 8}
    assert seen == [0, 1] and not fake_vision.requests


def test_payload_size_limit_stops_reading_after_offending_chunk(client, fake_vision, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_PAYLOAD_BYTES", 32)
    first = _part_header("payload") + b"{" + b" " * 31
    response, seen = _stream_post(client, [
        first, b" ", b"}\r\n" + _part_header("images", "test.jpg") + JPEG + b"\r\n--example--\r\n",
    ])
    assert response.status_code == 422
    assert response.json()["code"] == "intake_multipart_invalid"
    assert seen == [0, 1] and not fake_vision.requests


def test_complete_parts_do_not_allow_a_truncated_final_boundary(client, fake_vision):
    body = (
        _part_header("payload") + b'{"draft":{"items":[]}}\r\n'
        + _part_header("images", "test.jpg") + JPEG
        + b"\r\n--example\r\nContent-Dispos"
    )
    response, seen = _stream_post(client, [body])
    assert response.status_code == 422
    assert response.json()["code"] == "intake_multipart_invalid"
    assert seen == [0] and not fake_vision.requests


def test_valid_body_can_split_headers_and_webp_signature_across_chunks(client, fake_vision):
    fake_vision.reply = '{"operations":[]}'
    body = (
        _part_header("payload") + b'{"draft":{"items":[]}}\r\n'
        + _part_header("images", "test.webp") + WEBP + b"\r\n--example--\r\n"
    )
    chunks = [body[start:start + 5] for start in range(0, len(body), 5)]
    response, seen = _stream_post(client, chunks)
    assert response.status_code == 200, response.text
    assert seen == list(range(len(chunks)))
    image = fake_vision.requests[0]["messages"][1]["content"][1]["image_url"]["url"]
    assert image == f"data:image/webp;base64,{base64.b64encode(WEBP).decode()}"

"""Drafting and confirmation endpoints for stock intake."""

from email.message import Message
from json import JSONDecodeError

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from stock_manager.api import ai_client
from stock_manager.api.rate_limit import require_ai_quota
from stock_manager.api.db import get_session
from stock_manager.api.intake_schemas import (
    MAX_IMAGES,
    ConfirmRequest,
    ConfirmResponse,
    IntakeContext,
    ParseDraftRequest,
    ParseRequest,
    ParseResponse,
    TextInput,
)
from stock_manager.api.intake_services import confirm_intake, parse_images, parse_intake, prepare_parse
from stock_manager.api.uploads import read_image_upload

router = APIRouter()

_DRAFT_PROPERTIES = {
    "draft": {
        "type": "object",
        "required": ["items"],
        "properties": {"items": {
            "type": "array",
            "items": {"$ref": "#/components/schemas/IntakeCandidate"},
        }},
    },
    "context": IntakeContext.model_json_schema(),
}
_PARSE_REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": {
                "type": "object",
                "required": ["input", "draft"],
                "properties": {"input": TextInput.model_json_schema(), **_DRAFT_PROPERTIES},
            }},
            "multipart/form-data": {"schema": {
                "type": "object",
                "required": ["payload", "images"],
                "properties": {
                    "payload": {
                        "type": "string",
                        "contentMediaType": "application/json",
                        "contentSchema": {
                            "type": "object",
                            "required": ["draft"],
                            "properties": _DRAFT_PROPERTIES,
                        },
                    },
                    "images": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_IMAGES,
                        "items": {"type": "string", "format": "binary"},
                    },
                },
            }},
        },
    },
}


def _invalid_json(error: JSONDecodeError, location: tuple) -> RequestValidationError:
    return RequestValidationError([{
        "type": "json_invalid", "loc": (*location, error.pos),
        "msg": "JSON decode error", "input": {}, "ctx": {"error": error.msg},
    }], body=error.doc)


def _validate_payload(model, data, location: tuple):
    # Match FastAPI's body errors after selecting a request shape by media type.
    if data is None:
        raise RequestValidationError([{
            "type": "missing", "loc": location, "msg": "Field required", "input": None,
        }])
    try:
        return model.model_validate(data, from_attributes=True)
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        for error in errors:
            error["loc"] = (*location, *error["loc"])
        raise RequestValidationError(errors, body=data) from None


async def _read_text_request(request: Request) -> ParseRequest:
    body = None
    try:
        raw = await request.body()
        if raw:
            content_type = request.headers.get("content-type")
            message = Message()
            if content_type:
                message["content-type"] = content_type
            subtype = message.get_content_subtype()
            as_json = not content_type or (
                message.get_content_maintype() == "application" and (subtype == "json" or subtype.endswith("+json"))
            )
            body = await request.json() if as_json else raw
    except JSONDecodeError as exc:
        raise _invalid_json(exc, ("body",)) from None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="There was an error parsing the body") from exc
    return _validate_payload(ParseRequest, body, ("body",))


@router.post(
    "/parse", response_model=ParseResponse, openapi_extra=_PARSE_REQUEST_BODY,
    dependencies=[Depends(require_ai_quota)],
)
async def parse(
    request: Request,
    db: Session = Depends(get_session),
    accept_language: str | None = Header(None),
):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type == "multipart/form-data":
        config = ai_client.get_config()
        if not config.vision_available:
            raise ai_client.AIVisionUnavailableError("AI vision is not configured")
        data, images = await read_image_upload(request)
        payload = _validate_payload(ParseDraftRequest, data, ("body", "payload"))
        prepared = await run_in_threadpool(prepare_parse, db, payload, accept_language)
        return await parse_images(
            db, payload, prepared, [{**image, "detail": config.image_detail} for image in images],
        )

    payload = await _read_text_request(request)
    prepared = await run_in_threadpool(prepare_parse, db, payload, accept_language)
    return await parse_intake(db, payload, prepared)


@router.post("/confirm", response_model=ConfirmResponse, status_code=201)
async def confirm(payload: ConfirmRequest, db: Session = Depends(get_session)):
    return await run_in_threadpool(confirm_intake, db, payload)

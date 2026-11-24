"""Transcribe one uploaded recording."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from stock_manager.api import ai_client, asr_client
from stock_manager.api.rate_limit import require_ai_quota
from stock_manager.api.errors import APIError
from stock_manager.api.speech_audio import check_audio
from stock_manager.api.uploads import read_audio_upload

router = APIRouter()


class AudioWarning(BaseModel):
    code: Literal["audio_stereo_left_only"]


class TranscriptionResponse(BaseModel):
    transcript: str
    duration_ms: int
    warnings: list[AudioWarning] | None = None


_REQUEST_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["audio"],
                    "additionalProperties": False,
                    "properties": {
                        "audio": {"type": "string", "format": "binary"},
                        "feature": {"type": "string", "enum": ["stock_intake", "recipe_explore"]},
                    },
                },
            },
        },
    },
}


@router.post(
    "/transcribe", dependencies=[Depends(require_ai_quota)], response_model=TranscriptionResponse, response_model_exclude_none=True,
    openapi_extra=_REQUEST_BODY,
)
async def transcribe(request: Request) -> TranscriptionResponse:
    config = ai_client.get_config()
    if not config.asr_available:
        raise APIError(503, "asr_unavailable", "Speech transcription is not configured")
    upload = await read_audio_upload(request)
    audio_format = check_audio(upload.data)
    text, duration = await asr_client.transcribe(upload.data, audio_format, upload.feature, config)
    warnings = [AudioWarning(code="audio_stereo_left_only")] if audio_format.stereo_wav else None
    return TranscriptionResponse(transcript=text, duration_ms=duration, warnings=warnings)

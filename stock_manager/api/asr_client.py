"""DeepSeek speech-to-text transport and provider error mapping."""

import asyncio
import logging

import httpx

from stock_manager.api.ai_client import AIConfig, provider_error_detail
from stock_manager.api.errors import APIError
from stock_manager.api.speech_audio import AudioFormat, unsupported_audio
from stock_manager.api.uploads import audio_too_large

logger = logging.getLogger(__name__)
_transport: httpx.AsyncBaseTransport | None = None


def _upstream_error() -> APIError:
    return APIError(502, "asr_upstream_error", "Speech transcription provider failed")


async def transcribe(
    data: bytes, audio_format: AudioFormat, feature: str | None, config: AIConfig,
) -> tuple[str, int]:
    """Send the validated clip with only the file field required by DeepSeek."""
    url = f"{config.base_url.rstrip('/')}/v1/tools/asr"
    headers = {"Authorization": f"Bearer {config.api_key}"}
    files = {"file": (audio_format.filename, data, audio_format.mime)}
    async with httpx.AsyncClient(transport=_transport, timeout=config.asr_timeout) as client:
        for attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    client.post(url, headers=headers, files=files), timeout=config.asr_timeout,
                )
            except (httpx.TimeoutException, asyncio.TimeoutError):
                logger.warning("ASR feature=%s timeout", feature)
                raise _upstream_error() from None
            except httpx.RequestError:
                logger.warning("ASR feature=%s connection error", feature)
                raise _upstream_error() from None

            if response.is_success:
                break
            status = response.status_code
            detail = provider_error_detail(response, protect_content=True, structured_only=True)
            logger.warning("ASR feature=%s provider HTTP %d%s", feature, status, detail)
            if status == 400:
                raise unsupported_audio()
            if status == 413:
                raise audio_too_large()
            if attempt == 1 or status not in (429, 503):
                raise _upstream_error()

    try:
        body = response.json()
    except ValueError:
        body = None
    transcript = body.get("text") if isinstance(body, dict) else None
    duration = body.get("duration_ms") if isinstance(body, dict) else None
    if not isinstance(transcript, str) or type(duration) is not int or duration < 0:
        logger.warning("ASR feature=%s invalid provider response", feature)
        raise _upstream_error()
    logger.info("ASR feature=%s ok duration_ms=%d", feature, duration)
    return transcript, duration

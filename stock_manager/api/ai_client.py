"""Shared client for the AI provider (#66).

Every AI feature (Explore, Expand, and later intake) calls `chat_json`, so
model, timeouts, retries and reply parsing live in one place.

Configuration comes from the environment and is read and validated once
(`reload_config()` at startup). An invalid value is logged and disables AI,
instead of failing at request time.

Errors:
- AIUnavailableError (`ai_unavailable`, HTTP 503): AI is not configured or
  disabled. Retrying does not help.
- AIUpstreamError (`ai_upstream_error`, HTTP 502): the provider timed out,
  failed, or returned something that cannot be parsed. The user may retry.
"""
import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional, Union

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"  # deepseek-chat is retired (#66)

# Tests replace this with an httpx.MockTransport; None means real network.
_transport: Optional[httpx.AsyncBaseTransport] = None


class AIError(Exception):
    """Base class; `code` is the machine-readable error code (#65)."""
    code = "ai_error"
    status_code = 500


class AIUnavailableError(AIError):
    code = "ai_unavailable"
    status_code = 503


class AIUpstreamError(AIError):
    code = "ai_upstream_error"
    status_code = 502


@dataclass(frozen=True)
class AIConfig:
    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_MODEL
    temperature: float = 0.2
    # Per-request timeouts. Timeouts are not retried.
    text_timeout: float = 30.0
    image_timeout: float = 60.0
    # Upper bound for one chat_json call, retries included.
    text_total_timeout: float = 45.0
    image_total_timeout: float = 75.0
    # Retries after a connection error, 429 or 5xx.
    max_retries: int = 1

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_key)


# (env var, field, type, minimum)
_NUMERIC_SETTINGS = [
    ("AI_TEMPERATURE", "temperature", float, 0.0),
    ("AI_TIMEOUT_SECONDS", "text_timeout", float, 1.0),
    ("AI_IMAGE_TIMEOUT_SECONDS", "image_timeout", float, 1.0),
    ("AI_TOTAL_TIMEOUT_SECONDS", "text_total_timeout", float, 1.0),
    ("AI_IMAGE_TOTAL_TIMEOUT_SECONDS", "image_total_timeout", float, 1.0),
    ("AI_MAX_RETRIES", "max_retries", int, 0),
]


def load_config(environ=None) -> AIConfig:
    """Read the AI settings from the environment.

    An invalid number is logged and turns AI off rather than raising.
    """
    env = os.environ if environ is None else environ
    values: dict[str, Any] = {
        "enabled": env.get("AI_RECIPE_ENABLED", "false").strip().lower() == "true",
        "base_url": env.get("AI_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        "api_key": env.get("AI_API_KEY", "").strip(),
        "model": env.get("AI_MODEL", "").strip() or DEFAULT_MODEL,
    }
    for var, field, kind, minimum in _NUMERIC_SETTINGS:
        raw = env.get(var, "").strip()
        if not raw:
            continue
        try:
            value = kind(raw)
        except ValueError:
            value = None
        if value is None or value < minimum:
            logger.error("Invalid %s=%r; AI features are disabled until it is fixed.", var, raw)
            values["enabled"] = False
            continue
        values[field] = value
    return AIConfig(**values)


_config: Optional[AIConfig] = None


def reload_config() -> AIConfig:
    """Read the environment again (called at startup)."""
    global _config
    _config = load_config()
    if _config.enabled and not _config.api_key:
        logger.warning("AI_RECIPE_ENABLED is true but AI_API_KEY is empty; AI features are off.")
    return _config


def get_config() -> AIConfig:
    return _config if _config is not None else reload_config()


def is_available() -> bool:
    return get_config().available


# ─── Calling the provider ────────────────────────────────────────


JsonValue = Union[dict, list]


def parse_json_reply(text: str) -> Optional[JsonValue]:
    """A JSON object or list from the reply, or None.

    JSON output mode normally returns plain JSON; a ```json fenced block is
    accepted as a fallback.
    """
    candidates = [text]
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text or "")
    if match:
        candidates.append(match.group(1))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(value, (dict, list)):
            return value
    return None


def _user_content(user: str, images: Optional[list[dict]]):
    if not images:
        return user
    parts: list[dict] = [{"type": "text", "text": user}]
    for image in images:
        encoded = base64.b64encode(image["data"]).decode("ascii")
        parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{image['mime']};base64,{encoded}",
                "detail": image.get("detail", "auto"),
            },
        })
    return parts


def _is_retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


async def _post_with_retries(config: AIConfig, payload: dict, timeout: float) -> dict:
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
    attempts = 1 + config.max_retries
    async with httpx.AsyncClient(timeout=timeout, transport=_transport) as client:
        for attempt in range(1, attempts + 1):
            last = attempt == attempts
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                # A timeout is not retried: a second try would likely time out too.
                raise AIUpstreamError("AI request timed out") from exc
            except httpx.TransportError as exc:
                if last:
                    raise AIUpstreamError(f"AI connection failed: {exc}") from exc
                logger.warning("AI connection failed (attempt %d), retrying: %s", attempt, exc)
                continue
            if response.status_code < 400:
                try:
                    return response.json()
                except ValueError as exc:
                    raise AIUpstreamError("AI response is not JSON") from exc
            if _is_retryable_status(response.status_code) and not last:
                logger.warning("AI returned HTTP %d (attempt %d), retrying", response.status_code, attempt)
                continue
            raise AIUpstreamError(f"AI returned HTTP {response.status_code}")
    raise AIUpstreamError("AI request failed")  # pragma: no cover - loop always returns or raises


async def chat_json(
    system: str,
    user: str,
    *,
    images: Optional[list[dict]] = None,
    max_tokens: int = 4096,
    followup: Optional[list[dict]] = None,
) -> JsonValue:
    """Send one chat request and return the reply as parsed JSON.

    `images` (for intake, #63): dicts with `data` (bytes), `mime`, and an
    optional `detail` ("auto" / "low" / "high").

    `followup` (#65): more chat messages after the first user message, e.g. the
    model's previous reply and a list of problems to fix.

    Raises AIUnavailableError or AIUpstreamError; never returns None.
    """
    config = get_config()
    if not config.available:
        raise AIUnavailableError("AI is not configured")

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_content(user, images)},
            *(followup or []),
        ],
        "temperature": config.temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    timeout = config.image_timeout if images else config.text_timeout
    total = config.image_total_timeout if images else config.text_total_timeout
    try:
        result = await asyncio.wait_for(_post_with_retries(config, payload, timeout), total)
    except asyncio.TimeoutError as exc:
        raise AIUpstreamError(f"AI call exceeded {total:g}s") from exc

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIUpstreamError("AI response has no message content") from exc
    parsed = parse_json_reply(content)
    if parsed is None:
        logger.warning("AI reply is not JSON: %.200r", content)
        raise AIUpstreamError("AI reply could not be parsed")
    return parsed

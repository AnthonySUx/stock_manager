"""Shared client for the AI provider (#66).

Every AI feature (Explore, Expand, and later intake) calls `chat_json`, so
model, timeouts, retries, logging and reply parsing live in one place.

Configuration comes from the environment and is read and validated once
(`reload_config()` at startup). An invalid value is logged and disables AI,
instead of failing at request time.

Text requests are streamed from the provider (`AI_STREAM`, on by default).
Streaming changes what a timeout means: the call fails when the provider
sends nothing for too long, not when a long reply is still arriving.
- first data within `AI_FIRST_TOKEN_TIMEOUT_SECONDS` (reasoning counts);
- then no gap longer than `AI_IDLE_TIMEOUT_SECONDS`;
- the whole call (one round, retry included) within `AI_TOTAL_TIMEOUT_SECONDS`.
Image requests are not streamed and use the per-request timeouts.

Every call logs one line: `AI <label> ok ...` (INFO) or `AI <label> fail
<reason> ...` (WARNING), with timings, token usage and finish reason.

Errors:
- AIUnavailableError (`ai_unavailable`, HTTP 503): AI is not configured or
  disabled. Retrying does not help.
- AIUpstreamError (`ai_upstream_error`, HTTP 502): the provider timed out,
  failed, or returned something that cannot be used. The user may retry.
  `reason` says which (see REASONS); it goes to the log, not the client.
"""
import asyncio
import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

import httpx

logger = logging.getLogger(__name__)

_DATA_URI = re.compile(r"""\bdata:[^\s"'<>\x60]+""", re.IGNORECASE)
_LONG_BASE64 = re.compile(r"[A-Za-z0-9+/_-]{100,}={0,2}")

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"  # deepseek-chat is retired (#66)

# Tests replace this with an httpx.MockTransport; None means real network.
_transport: Optional[httpx.AsyncBaseTransport] = None

# Why a call failed, as written in the log.
REASONS = (
    "timeout_first_token",  # nothing arrived within the first-token limit
    "timeout_idle",         # the stream stalled
    "timeout_round",        # the round took longer than the total limit
    "timeout",              # a non-streamed request timed out
    "connection",           # could not reach the provider
    "http_error",           # the provider answered with an HTTP error (see message)
    "stream_error",         # the stream carried an error or a broken chunk
    "no_content",           # the reply had no message content
    "truncated",            # the reply hit max_tokens and is not valid JSON
    "not_json",             # the reply is not JSON
    "no_usable_ideas",      # Explore: nothing passed validation
    "draft_unusable",       # Expand: no draft passed validation
)


class AIError(Exception):
    """Base class; `code` is the machine-readable error code (#65)."""
    code = "ai_error"
    status_code = 500
    reason = ""


class AIUnavailableError(AIError):
    code = "ai_unavailable"
    status_code = 503
    reason = "not_configured"


class AIVisionUnavailableError(AIUnavailableError):
    code = "ai_vision_unavailable"


class AIUpstreamError(AIError):
    code = "ai_upstream_error"
    status_code = 502

    def __init__(self, message: str = "", reason: str = "http_error"):
        super().__init__(message)
        self.reason = reason


def log_ai_error(method: str, path: str, exc: AIError) -> None:
    """One log line for a request that ended in an AI error."""
    logger.warning("%s %s -> %s [%s]: %s", method, path, exc.code, exc.reason, exc)


@dataclass(frozen=True)
class AIConfig:
    enabled: bool = False
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    model: str = DEFAULT_MODEL
    temperature: float = 0.2
    stream: bool = True
    vision_enabled: bool = False
    image_detail: str = "high"
    max_tokens: int = 8192
    # Streamed text calls: first data, then the longest gap between chunks.
    first_token_timeout: float = 20.0
    idle_timeout: float = 15.0
    # Non-streamed requests (images, or AI_STREAM=false). Not retried.
    text_timeout: float = 30.0
    image_timeout: float = 60.0
    # Upper bound for one call (one round), retries included.
    text_total_timeout: float = 50.0
    image_total_timeout: float = 75.0
    # Retries after a connection error, 429 or 5xx, before any content arrived.
    max_retries: int = 1

    @property
    def available(self) -> bool:
        return self.enabled and bool(self.api_key)

    @property
    def vision_available(self) -> bool:
        return self.available and self.vision_enabled


# (env var, field, type, minimum)
_NUMERIC_SETTINGS = [
    ("AI_TEMPERATURE", "temperature", float, 0.0),
    ("AI_MAX_TOKENS", "max_tokens", int, 1),
    ("AI_FIRST_TOKEN_TIMEOUT_SECONDS", "first_token_timeout", float, 1.0),
    ("AI_IDLE_TIMEOUT_SECONDS", "idle_timeout", float, 1.0),
    ("AI_TIMEOUT_SECONDS", "text_timeout", float, 1.0),
    ("AI_IMAGE_TIMEOUT_SECONDS", "image_timeout", float, 1.0),
    ("AI_TOTAL_TIMEOUT_SECONDS", "text_total_timeout", float, 1.0),
    ("AI_IMAGE_TOTAL_TIMEOUT_SECONDS", "image_total_timeout", float, 1.0),
    ("AI_MAX_RETRIES", "max_retries", int, 0),
]


def load_config(environ=None) -> AIConfig:
    """Read the AI settings from the environment.

    An invalid value is logged and turns AI off rather than raising.
    """
    env = os.environ if environ is None else environ
    values: dict[str, Any] = {
        "enabled": env.get("AI_RECIPE_ENABLED", "false").strip().lower() == "true",
        "base_url": env.get("AI_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        "api_key": env.get("AI_API_KEY", "").strip(),
        "model": env.get("AI_MODEL", "").strip() or DEFAULT_MODEL,
        "vision_enabled": env.get("AI_VISION_ENABLED", "").strip().lower() == "true",
    }
    image_detail = env.get("AI_IMAGE_DETAIL", "").strip().lower() or "high"
    if image_detail in ("low", "high", "auto"):
        values["image_detail"] = image_detail
    else:
        logger.error("Invalid AI_IMAGE_DETAIL (use low, high or auto); AI vision is disabled.")
        values["vision_enabled"] = False
    stream = env.get("AI_STREAM", "").strip().lower()
    if stream in ("", "true"):
        values["stream"] = True
    elif stream == "false":
        values["stream"] = False
    else:
        logger.error("Invalid AI_STREAM=%r (use true or false); AI features are disabled.", stream)
        values["enabled"] = False
    for var, name, kind, minimum in _NUMERIC_SETTINGS:
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
        values[name] = value
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
TextCallback = Callable[[str], None]


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


def _short(text: str, limit: int = 200) -> str:
    return " ".join((text or "").split())[:limit]


def _error_message(body: Any) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    message = error.get("message") if isinstance(error, dict) else error
    return message if isinstance(message, str) and message.strip() else None


def _error_detail(response: httpx.Response, *, protect_content: bool = False) -> str:
    """The provider's error message, for the server log.

    401 / 403 only say to check the key: their body may echo part of it.
    """
    if response.status_code in (401, 403):
        return " (check AI_API_KEY)"
    try:
        message = _error_message(response.json())
    except ValueError:
        message = None
    message = message or response.text
    if protect_content:
        # Redact first so an embedded upload cannot consume the diagnostic budget.
        message = _DATA_URI.sub("[redacted]", message)
        message = _LONG_BASE64.sub("[redacted]", message)
    message = _short(message)
    return f": {message}" if message else ""


def _is_retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


@dataclass
class CallStats:
    """What one call did, for the log line. Times are seconds from the start."""
    start: float = field(default_factory=time.monotonic)
    first_data: Optional[float] = None
    first_reasoning: Optional[float] = None
    first_content: Optional[float] = None
    reasoning_chars: int = 0
    content_chars: int = 0
    finish_reason: Optional[str] = None
    usage: Optional[dict] = None
    attempts: int = 0

    def now(self) -> float:
        return time.monotonic() - self.start

    def mark_data(self) -> None:
        if self.first_data is None:
            self.first_data = self.now()

    def describe(self) -> str:
        def seconds(value: Optional[float]) -> str:
            return "-" if value is None else f"{value:.1f}s"

        reasoning = "-"
        if self.first_reasoning is not None:
            end = self.first_content if self.first_content is not None else self.now()
            reasoning = f"{end - self.first_reasoning:.1f}s"
        usage = self.usage or {}
        tokens = f"{usage.get('prompt_tokens', '?')}/{usage.get('completion_tokens', '?')}"
        return (
            f"{self.now():.1f}s first_data={seconds(self.first_data)} reasoning={reasoning} "
            f"chars={self.content_chars} tokens={tokens} finish={self.finish_reason or '-'}"
            + (f" attempts={self.attempts}" if self.attempts > 1 else "")
        )


@dataclass
class _Reply:
    parts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(self.parts)


def _add_content(text: str, stats: CallStats, reply: _Reply, on_text: Optional[TextCallback]) -> None:
    if not text:
        return
    if stats.first_content is None:
        stats.first_content = stats.now()
    stats.content_chars += len(text)
    reply.parts.append(text)
    if on_text is not None:
        on_text(text)


def _read_completion(body: Any, stats: CallStats, reply: _Reply, on_text: Optional[TextCallback]) -> None:
    """A whole (non-streamed) chat completion."""
    try:
        choice = body["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIUpstreamError("AI response has no message content", "no_content") from exc
    stats.finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
    stats.usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
    if not isinstance(content, str) or not content:
        raise AIUpstreamError("AI response has no message content", "no_content")
    _add_content(content, stats, reply, on_text)


def _read_chunk(data: str, stats: CallStats, reply: _Reply, on_text: Optional[TextCallback]) -> None:
    """One `data:` line of a streamed completion."""
    try:
        chunk = json.loads(data)
    except ValueError as exc:
        raise AIUpstreamError(f"AI stream chunk is not JSON: {_short(data, 80)}", "stream_error") from exc
    if not isinstance(chunk, dict):
        raise AIUpstreamError("AI stream chunk is not an object", "stream_error")
    message = _error_message(chunk)
    if message:
        raise AIUpstreamError(f"AI stream error: {_short(message)}", "stream_error")
    if isinstance(chunk.get("usage"), dict):
        stats.usage = chunk["usage"]
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return
    choice = choices[0]
    if choice.get("finish_reason"):
        stats.finish_reason = choice["finish_reason"]
    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
    reasoning = delta.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        if stats.first_reasoning is None:
            stats.first_reasoning = stats.now()
        stats.reasoning_chars += len(reasoning)
    content = delta.get("content")
    if isinstance(content, str):
        _add_content(content, stats, reply, on_text)


def _round_error(total: float) -> AIUpstreamError:
    return AIUpstreamError(f"AI call exceeded {total:g}s", "timeout_round")


async def _read_stream(
    response: httpx.Response, config: AIConfig, stats: CallStats, reply: _Reply,
    on_text: Optional[TextCallback], total: float,
) -> None:
    """Read server-sent events until [DONE], enforcing the first-token, idle
    and round limits. Keep-alive comments do not count as data.

    The round limit is checked here too, not only by the caller's wait_for:
    on Python 3.11 a cancellation that races with a chunk arriving in the
    inner wait_for can be lost, and the stream would then run on.
    """
    lines = response.aiter_lines()
    last_data = stats.now()
    while True:
        if stats.first_data is None:
            stall_left = config.first_token_timeout - stats.now()
        else:
            stall_left = last_data + config.idle_timeout - stats.now()
        round_left = total - stats.now()
        try:
            line = await asyncio.wait_for(lines.__anext__(), max(min(stall_left, round_left), 0.001))
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError as exc:
            if round_left <= stall_left:
                raise _round_error(total) from exc
            raise _stall_error(stats, config) from exc
        if not line.startswith("data:"):
            continue  # blank separators, comments (": keep-alive"), event names
        data = line[5:].strip()
        if data == "[DONE]":
            return
        stats.mark_data()
        last_data = stats.now()
        _read_chunk(data, stats, reply, on_text)


def _stall_error(stats: CallStats, config: AIConfig) -> AIUpstreamError:
    if stats.first_data is None:
        return AIUpstreamError(
            f"no data from the AI within {config.first_token_timeout:g}s", "timeout_first_token"
        )
    return AIUpstreamError(f"AI stream stalled for {config.idle_timeout:g}s", "timeout_idle")


async def _request(
    config: AIConfig, payload: dict, stream: bool, timeout: float, total: float,
    stats: CallStats, reply: _Reply, on_text: Optional[TextCallback], *, protect_content: bool = False,
) -> None:
    """Send the request, retrying connection errors, 429 and 5xx once (by
    default) while no content has arrived. Timeouts are not retried."""
    url = f"{config.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
    if stream:
        # Reads are bounded by the first-token / idle checks in _read_stream;
        # this is a backstop for the wait for the response headers.
        client_timeout = httpx.Timeout(10.0, read=config.first_token_timeout)
    else:
        client_timeout = httpx.Timeout(timeout)
    attempts = 1 + config.max_retries
    async with httpx.AsyncClient(timeout=client_timeout, transport=_transport) as client:
        for attempt in range(1, attempts + 1):
            stats.attempts = attempt
            last = attempt == attempts
            try:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code >= 400:
                        if not protect_content:
                            await response.aread()
                        if _is_retryable_status(response.status_code) and not last:
                            logger.warning(
                                "AI returned HTTP %d (attempt %d), retrying", response.status_code, attempt
                            )
                            continue
                        if protect_content and response.status_code not in (401, 403):
                            await response.aread()
                        detail = _error_detail(response, protect_content=protect_content)
                        raise AIUpstreamError(
                            f"AI returned HTTP {response.status_code}{detail}", "http_error"
                        )
                    if stream and "text/event-stream" in response.headers.get("content-type", ""):
                        await _read_stream(response, config, stats, reply, on_text, total)
                        return
                    # Not streamed (images, AI_STREAM=false, or a provider that
                    # ignores `stream`): one JSON body.
                    await response.aread()
                    stats.mark_data()
                    try:
                        body = response.json()
                    except ValueError as exc:
                        raise AIUpstreamError("AI response is not JSON", "not_json") from exc
                    _read_completion(body, stats, reply, on_text)
                    return
            except httpx.TimeoutException as exc:
                if stream:
                    raise _stall_error(stats, config) from exc
                raise AIUpstreamError(f"AI request timed out after {timeout:g}s", "timeout") from exc
            except httpx.TransportError as exc:
                detail = "" if protect_content else f": {exc}"
                if last or reply.parts:
                    error = AIUpstreamError(f"AI connection failed{detail}", "connection")
                    if protect_content:
                        raise error from None
                    raise error from exc
                logger.warning("AI connection failed (attempt %d), retrying%s", attempt, detail)
    raise AIUpstreamError("AI request failed")  # pragma: no cover - loop always returns or raises


async def chat_json(
    system: str,
    user: str,
    *,
    images: Optional[list[dict]] = None,
    max_tokens: Optional[int] = None,
    followup: Optional[list[dict]] = None,
    label: str = "ai",
    on_text: Optional[TextCallback] = None,
) -> JsonValue:
    """Send one chat request and return the reply as parsed JSON.

    `images` (for intake, #63): dicts with `data` (bytes), `mime`, and an
    optional `detail` ("auto" / "low" / "high"). Image calls are not streamed.

    `followup` (#65): more chat messages after the first user message, e.g. the
    model's previous reply and a list of problems to fix.

    `label` names the call in the log ("explore/first", "expand/repair").

    `on_text` receives the reply text as it arrives (Explore validates each
    idea as soon as it is complete). It sees raw, unvalidated text.

    Raises AIUnavailableError or AIUpstreamError; never returns None.
    """
    config = get_config()
    if not config.available:
        raise AIUnavailableError("AI is not configured")

    stream = config.stream and not images
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": _user_content(user, images)},
            *(followup or []),
        ],
        "temperature": config.temperature,
        "max_tokens": max_tokens or config.max_tokens,
        "response_format": {"type": "json_object"},
    }
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    timeout = config.image_timeout if images else config.text_timeout
    total = config.image_total_timeout if images else config.text_total_timeout
    stats = CallStats()
    reply = _Reply()
    mode = "stream" if stream else "plain"

    def diagnostics() -> str:
        # Providers can echo image input in response metadata and error bodies.
        return f"{stats.now():.1f}s attempts={stats.attempts}" if images else stats.describe()

    def fail(error: AIUpstreamError) -> AIUpstreamError:
        logger.warning("AI %s fail %s model=%s %s %s: %s",
                       label, error.reason, config.model, mode, diagnostics(), error)
        return error

    try:
        await asyncio.wait_for(
            _request(config, payload, stream, timeout, total, stats, reply, on_text, protect_content=bool(images)),
            total,
        )
    except asyncio.TimeoutError as exc:
        raise fail(_round_error(total)) from exc
    except AIUpstreamError as exc:
        raise fail(exc)

    if not reply.text:
        raise fail(AIUpstreamError("AI response has no message content", "no_content"))
    parsed = parse_json_reply(reply.text)
    if parsed is None:
        if stats.finish_reason == "length":
            raise fail(AIUpstreamError(
                f"AI reply was cut off at max_tokens={payload['max_tokens']}", "truncated"
            ))
        detail = "" if images else f": {_short(reply.text, 120)!r}"
        raise fail(AIUpstreamError(f"AI reply is not JSON{detail}", "not_json"))
    logger.info("AI %s ok model=%s %s %s", label, config.model, mode, diagnostics())
    return parsed

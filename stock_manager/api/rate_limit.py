"""Per-token sliding-window limits for AI requests."""

import os
from collections import deque
from collections.abc import Callable
from hashlib import sha256
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import Depends, Request

from stock_manager.api.auth import require_api_token
from stock_manager.api.errors import APIError


def _positive_setting(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        if value > 0:
            return value
    except ValueError:
        pass
    raise RuntimeError(f"{name} must be a positive integer")


class AIRateLimiter:
    """Track accepted requests within one time window for each token."""

    def __init__(
        self, per_window: int, window_seconds: int, *, clock: Callable[[], float] = monotonic,
    ) -> None:
        self.per_window = per_window
        self.window_seconds = window_seconds
        self.clock = clock
        self._requests: dict[bytes | None, deque[float]] = {}
        self._lock = Lock()

    @classmethod
    def from_env(cls) -> "AIRateLimiter":
        return cls(
            _positive_setting("AI_RATE_LIMIT_PER_WINDOW", 30),
            _positive_setting("AI_RATE_LIMIT_WINDOW_SECONDS", 600),
        )

    def check(self, token: str | None) -> None:
        # Authentication-disabled development shares a single anonymous bucket.
        key = sha256(token.encode()).digest() if token is not None else None
        with self._lock:
            now = self.clock()
            timestamps = self._requests.setdefault(key, deque())
            cutoff = now - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= self.per_window:
                raise APIError(
                    429, "rate_limited", "Too many AI requests",
                    retry_after=max(1, ceil(timestamps[0] + self.window_seconds - now)),
                )
            timestamps.append(now)


def require_ai_quota(request: Request, token: str | None = Depends(require_api_token)) -> None:
    request.app.state.ai_rate_limiter.check(token)

"""Shared-token API authentication (issue #41).

All `/api/*` routes except `/api/health` require `Authorization: Bearer <API_TOKEN>`.
There is one token per installation (one household). Per-member accounts are
not planned; a later step may issue this token from a household login instead
of reading it from the environment.

For local development without a token, set `API_AUTH_DISABLED=true`.
"""

import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False, description="Shared household API token (API_TOKEN)")


def auth_disabled() -> bool:
    return os.getenv("API_AUTH_DISABLED", "false").strip().lower() == "true"


def configured_token() -> str:
    return os.getenv("API_TOKEN", "").strip()


def check_auth_config() -> None:
    """Fail fast at startup when no token is configured and auth is not disabled."""
    if not auth_disabled() and not configured_token():
        raise RuntimeError(
            "API_TOKEN is not set. Generate one with "
            "`python3 -c \"import secrets; print(secrets.token_urlsafe(32))\"` and put it in .env, "
            "or set API_AUTH_DISABLED=true for local development only."
        )


def require_api_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    """FastAPI dependency: reject requests without the shared token."""
    if auth_disabled():
        return
    expected = configured_token()
    provided = credentials.credentials if credentials else ""
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

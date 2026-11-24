"""FastAPI application entry point for Stock Manager."""

import logging
import os
from contextlib import asynccontextmanager
from math import isfinite
from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException

from stock_manager import __version__
from stock_manager.api import ai_client, media
from stock_manager.api.auth import check_auth_config, require_api_token
from stock_manager.api.schema_version import check_schema_current
from stock_manager.api.db import engine
from stock_manager.api.errors import APIError
from stock_manager.api.rate_limit import AIRateLimiter
from stock_manager.api.routers import capabilities, categories, intake, items, photos, recipes, restock, settings, speech


def configure_logging() -> None:
    """Show the app's own log lines (AI calls, AI errors) next to uvicorn's.

    uvicorn only configures its own loggers; without a handler here, INFO
    lines from `stock_manager.*` would be dropped. Level: LOG_LEVEL (INFO).
    """
    app_logger = logging.getLogger("stock_manager")
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        app_logger.addHandler(handler)
    level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    value = logging.getLevelName(level)  # an int for a known level name
    app_logger.setLevel(value if isinstance(value, int) else logging.INFO)


configure_logging()

description = """
Stock Manager API — manage family stock, expiration reminders, and restocking lists.

* [Stock Items](/docs#/items) — CRUD, search, consume, delete
* [Restock List](/docs#/restock) — manage pending and done restock items
* [Settings](/docs#/settings) — configure global options
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Check auth config and the schema version, then seed default categories.

    Tables are created and upgraded by Alembic (`alembic upgrade head`), not
    here (#49).
    """
    check_auth_config()
    check_schema_current(engine)
    ai_client.reload_config()  # read and validate AI settings once (#66)
    media.reload_config()
    app.state.ai_rate_limiter = AIRateLimiter.from_env()
    from sqlalchemy.orm import sessionmaker
    from stock_manager.api.category_services import seed_default_categories
    SeedSession = sessionmaker(bind=engine)
    with SeedSession() as session:
        seed_default_categories(session)
    yield

# CORS — only browser clients (e.g. Expo web) are affected; native iOS/Android
# requests do not use CORS. Origins come from CORS_ALLOW_ORIGINS (comma-separated).
DEFAULT_CORS_ORIGINS = "http://localhost:8081,http://127.0.0.1:8081,http://localhost:19006"


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "unprocessable_entity",
    429: "too_many_requests",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}

AI_ERROR_DETAILS = {
    "ai_unavailable": "AI is not configured",
    "ai_vision_unavailable": "AI vision is not configured",
    "ai_upstream_error": "AI provider request failed",
}


def _error_response(status_code, code, params, detail, *, headers=None):
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "params": params, "detail": detail},
        headers=headers,
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException):
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=exc.headers)
    code = HTTP_ERROR_CODES.get(exc.status_code, "http_error")
    return _error_response(exc.status_code, code, {}, exc.detail, headers=exc.headers)


async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    # Invalid numeric input may contain a non-finite float that JSON cannot echo.
    errors = jsonable_encoder(
        exc.errors(), custom_encoder={float: lambda value: value if isfinite(value) else str(value)}
    )
    return _error_response(422, "validation_error", {"errors": errors}, errors)


async def api_error_handler(request: Request, exc: APIError):
    return _error_response(exc.status_code, exc.code, exc.params, exc.detail)


async def ai_error_handler(request: Request, exc: ai_client.AIError):
    """Return a public message while keeping the provider diagnostic in the server log."""
    ai_client.log_ai_error(request.method, request.url.path, exc)
    detail = AI_ERROR_DETAILS.get(exc.code, "AI request failed")
    return _error_response(exc.status_code, exc.code, {}, detail)


def health():
    """Health check endpoint."""
    return {"status": "ok", "version": __version__}


def create_app() -> FastAPI:
    docs_enabled = os.getenv("API_DOCS_ENABLED", "false").strip().lower() == "true"
    app = FastAPI(
        title="Stock Manager API",
        description=description,
        version=__version__,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers — all require the shared API token (issue #41); /api/health stays public.
    _auth = [Depends(require_api_token)]
    app.include_router(items.router, prefix="/api/items", tags=["Stock Items"], dependencies=_auth)
    app.include_router(restock.router, prefix="/api/restock", tags=["Restock Items"], dependencies=_auth)
    app.include_router(settings.router, prefix="/api/settings", tags=["Settings"], dependencies=_auth)
    app.include_router(photos.router, prefix="/api", dependencies=_auth)
    app.include_router(recipes.router, prefix="/api/recipes", tags=["Recipes"], dependencies=_auth)
    app.include_router(categories.router, prefix="/api/categories", tags=["Categories"], dependencies=_auth)
    app.include_router(capabilities.router, prefix="/api/capabilities", tags=["Capabilities"], dependencies=_auth)
    app.include_router(intake.router, prefix="/api/intake", tags=["Intake"], dependencies=_auth)
    app.include_router(speech.router, prefix="/api/speech", tags=["Speech"], dependencies=_auth)

    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(ai_client.AIError, ai_error_handler)
    app.add_api_route("/api/health", health, methods=["GET"], tags=["Health"])
    return app


app = create_app()

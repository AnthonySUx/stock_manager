"""FastAPI application entry point for Stock Manager."""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from stock_manager import __version__
from stock_manager.api import ai_client
from stock_manager.api.auth import check_auth_config, require_api_token
from stock_manager.api.schema_version import check_schema_current
from stock_manager.api.db import engine
from stock_manager.api.errors import APIError
from stock_manager.api.routers import capabilities, categories, intake, items, recipes, restock, settings, speech


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
    from sqlalchemy.orm import sessionmaker
    from stock_manager.api.category_services import seed_default_categories
    SeedSession = sessionmaker(bind=engine)
    with SeedSession() as session:
        seed_default_categories(session)
    yield

app = FastAPI(
    title="Stock Manager API",
    description=description,
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — only browser clients (e.g. Expo web) are affected; native iOS/Android
# requests do not use CORS. Origins come from CORS_ALLOW_ORIGINS (comma-separated).
DEFAULT_CORS_ORIGINS = "http://localhost:8081,http://127.0.0.1:8081,http://localhost:19006"


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


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
app.include_router(recipes.router, prefix="/api/recipes", tags=["Recipes"], dependencies=_auth)
app.include_router(categories.router, prefix="/api/categories", tags=["Categories"], dependencies=_auth)
app.include_router(capabilities.router, prefix="/api/capabilities", tags=["Capabilities"], dependencies=_auth)
app.include_router(intake.router, prefix="/api/intake", tags=["Intake"], dependencies=_auth)
app.include_router(speech.router, prefix="/api/speech", tags=["Speech"], dependencies=_auth)


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    body = {"code": exc.code, "params": exc.params}
    if exc.detail:
        body["detail"] = exc.detail
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(ai_client.AIError)
async def ai_error_handler(request: Request, exc: ai_client.AIError):
    """AI failures: 503 `ai_unavailable` (not configured) or 502
    `ai_upstream_error` (provider failed; the client may retry) (#66).

    The reason goes to the server log only; the client gets the code."""
    ai_client.log_ai_error(request.method, request.url.path, exc)
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code})



@app.get("/api/health", tags=["Health"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": __version__}

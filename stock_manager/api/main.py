"""FastAPI application entry point for Stock Manager."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stock_manager import __version__
from stock_manager.api.db import engine
from stock_manager.api.models import Base
from stock_manager.api.routers import items, restock, settings, recipes, categories

description = """
Stock Manager API — manage family stock, expiration reminders, and restocking lists.

* [Stock Items](/docs#/items) — CRUD, search, consume, delete
* [Restock List](/docs#/restock) — manage pending and done restock items
* [Settings](/docs#/settings) — configure global options
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup if they do not exist."""
    Base.metadata.create_all(bind=engine)
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

# Routers
app.include_router(items.router, prefix="/api/items", tags=["Stock Items"])
app.include_router(restock.router, prefix="/api/restock", tags=["Restock Items"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["Recipes"])
app.include_router(categories.router, prefix="/api/categories", tags=["Categories"])



@app.get("/api/health", tags=["Health"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": __version__}

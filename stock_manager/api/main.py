"""FastAPI application entry point for Stock Manager."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from stock_manager import __version__
from stock_manager.api.db import engine
from stock_manager.api.models import Base
from stock_manager.api.routers import items, restock, settings, recipes

description = """
Stock Manager API — manage family stock, expiration reminders, and restocking lists.

* [Stock Items](/docs#/items) — CRUD, search, consume, delete
* [Restock List](/docs#/restock) — manage pending and done restock items
* [Settings](/docs#/settings) — configure global options
"""

app = FastAPI(
    title="Stock Manager API",
    description=description,
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow Expo development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(items.router, prefix="/api/items", tags=["Stock Items"])
app.include_router(restock.router, prefix="/api/restock", tags=["Restock Items"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["Recipes"])


@app.on_event("startup")
def on_startup():
    """Create tables on startup if they do not exist."""
    Base.metadata.create_all(bind=engine)


@app.get("/api/health", tags=["Health"])
def health():
    """Health check endpoint."""
    return {"status": "ok", "version": __version__}

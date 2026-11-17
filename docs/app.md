# Stock Manager App

Stock Manager App is a mobile-first inventory management application with a FastAPI backend and MySQL database.

This page is the entry point for the App documentation.

## Sections

- [Setup](app/setup.md) — Prerequisites, database, backend, frontend, environment variables
- [Features](app/features.md) — Inventory management, restock list, expiration reminders, cleanup
- [Recipes](app/recipes.md) — Recipe library, favorites, Today Recommendations, Explore Recipes
- [Troubleshooting](app/troubleshooting.md) — Common issues and solutions

## Quick Links

| Resource | URL |
|---|---|
| API Docs (Swagger) | http://localhost:8000/docs |
| Frontend | Native SwiftUI for iOS 17+ (see [Setup](app/setup.md)) |
| Backend | http://localhost:8000 |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌───────┐
│ SwiftUI App │────▶│ FastAPI      │────▶│ MySQL │
│ (iOS 17+)   │     │ (uvicorn)    │     │       │
└─────────────┘     └──────────────┘     └───────┘
```

- **Frontend**: Native SwiftUI (iOS 17+, iPhone and iPad)
- **Backend**: FastAPI (Python 3.10+)
- **Database**: MySQL 8 (via Docker or Homebrew)
- **AI**: Optional provider integration (DeepSeek by default) — only used for Explore Recipes now

> The legacy CLI uses **SQLite** and is documented separately in [CLI Docs](cli.md).

## Database

The App/API uses **MySQL**. The legacy CLI uses **SQLite**. They are separate data sources.

## Project Structure

```
stock_manager/
  api/                    # FastAPI backend
    main.py               # App entry point
    db.py                 # Database session
    models.py             # SQLAlchemy ORM models
    schemas.py            # Pydantic schemas (stock, restock)
    services.py           # Business logic (stock, restock)
    ai_recipe_service.py  # AI recipe integration
    recipe_services.py    # Recipe business logic
    recipe_schemas.py     # Recipe Pydantic schemas
    explore_services.py   # Explore Recipes service
    routers/
      items.py            # Stock CRUD endpoints
      restock.py          # Restock endpoints
      recipes.py          # Recipe + Recommendations + Explore endpoints
      settings.py         # Settings endpoints
ios/                      # Native SwiftUI app
  StockManager/           # App, features, models, and API client
  StockManagerTests/      # Unit and API-contract tests
  StockManagerUITests/    # End-to-end UI tests
scripts/                  # Helper scripts
docker-compose.yml        # MySQL 8
```

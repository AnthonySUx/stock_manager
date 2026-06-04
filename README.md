# Stock Manager

This is a family inventory management application with a mobile frontend, FastAPI backend, MySQL database, and legacy local CLI support. It helps users track household stock, owners, locations, quantities, purchase dates, expiration dates, and consumption status. The app supports restocking workflows, reminders for expiring items, cleanup of outdated records, and settings for user-level preferences. It also includes recipe management, stock-based recipe recommendations, AI-assisted recipe exploration, and cooking flows that can optionally deduct used ingredients from inventory.

| Interface | Status | Database | Docs |
|---|---|---|---|
| Mobile App + API | **Primary** | MySQL | [docs/app.md](docs/app.md) |
| CLI | Legacy / optional | SQLite | [docs/cli.md](docs/cli.md) |

---

## Quick Start (App)

```bash
# 1. Start MySQL
docker compose up -d

# 2. Backend
source .venv/bin/activate
uvicorn stock_manager.api.main:app --reload --host 0.0.0.0 --port 8000

# 3. Frontend
cd frontend
npx expo start -c
```

Full setup guide: [docs/app/setup.md](docs/app/setup.md)

---

## Main App Features

- **Stock Management** — Add, edit, search, filter, consume and delete stock items
- **Expiration Reminders** — Track and review expiring items
- **Restock List** — Plan and track restock purchases
- **Recipe Library** — Browse, search, favorite, create, fork recipes
- **Today Recommendations** — Daily recipe suggestions based on current inventory
- **Explore Recipes** — AI-powered creative recipe ideas based structured or nature language requirements

See [docs/app.md](docs/app.md) for the full App documentation.

---

## Legacy CLI

The original CLI is still available and uses **SQLite**. It does not require Docker or a running API server.

```bash
python3 -m stock_manager --help
```

See [docs/cli.md](docs/cli.md) for the full CLI documentation.

> **Note**: The CLI and App use different databases. CLI uses local SQLite files; the App uses MySQL via the API. They are not automatically synced.

---

## Docs Overview

```
README.md               ← You are here
docs/
  app.md                App documentation index
  app/setup.md          Prerequisites, database, backend, frontend setup
  app/features.md       Core app features (inventory, restock, reminders)
  app/recipes.md        Recipe library, recommendations, explore
  app/troubleshooting.md Common issues
  cli.md                Legacy CLI documentation
```

---



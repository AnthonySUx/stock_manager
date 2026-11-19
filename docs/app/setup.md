# Setup

Prerequisites, database configuration, and steps to run the backend and native iOS app.

---

## 1. Prerequisites

### 1.1 Homebrew (macOS)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1.2 Python 3.10+

```bash
brew install python@3.13
python3 --version
```

### 1.3 Xcode

Install Xcode from the Mac App Store, open it once, and allow it to install its additional components. The app requires iOS 17 or later.

### 1.4 MySQL

Choose one of the following:

#### Option A: Docker MySQL (recommended)

Install Docker Desktop from https://www.docker.com/products/docker-desktop/

```bash
docker --version
docker compose version
```

#### Option B: Homebrew MySQL (alternative)

```bash
brew install mysql
brew services start mysql
```

Then create the database and user:

```bash
mysql -u root
```

```sql
CREATE DATABASE stock_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'stock_user'@'localhost' IDENTIFIED BY 'stock_password';
GRANT ALL PRIVILEGES ON stock_manager.* TO 'stock_user'@'localhost';
FLUSH PRIVILEGES;
```

Homebrew MySQL normally listens on port 3306. If you choose this alternative,
set `DATABASE_URL` explicitly to port 3306. The checked-in Docker configuration
uses port 3307 so the two deployments cannot be mistaken for one another.

---

## 2. Project Setup

### 2.1 Clone

```bash
git clone <your-repo-url>
cd stock_manager
```

### 2.2 Environment Variables

Create `.env` in the project root:

```env
MYSQL_HOST_PORT=3307
DATABASE_URL=mysql+pymysql://stock_user:stock_password@127.0.0.1:3307/stock_manager

# Docker MySQL passwords (used when the volume is first created).
# If you change MYSQL_HOST_PORT or MYSQL_PASSWORD, change DATABASE_URL too.
MYSQL_ROOT_PASSWORD=root_password
MYSQL_PASSWORD=stock_password

# Shared API token (required). See 3.7.
API_TOKEN=paste-a-generated-token-here
# API_AUTH_DISABLED=true   # local development only

# 127.0.0.1 = only this machine. See 3.6 for testing on a real phone.
API_HOST=127.0.0.1
API_PORT=8000

# Browser origins allowed by CORS. Native apps are not affected.
# CORS_ALLOW_ORIGINS=http://localhost:8081,http://127.0.0.1:8081,http://localhost:19006

# AI recipe recommendations (optional, for Explore Recipes)
# AI_RECIPE_ENABLED=false
# AI_BASE_URL=https://api.deepseek.com
# AI_API_KEY=
# AI_MODEL=deepseek-flash
# Image intake is opt-in after checking that the provider supports images with JSON mode.
# AI_VISION_ENABLED=false
# AI_IMAGE_DETAIL=high
# First-seen receipt products use the AI's built-in knowledge.
# RECEIPT_PRODUCT_LOOKUP_PROVIDER=none
# AI_TEMPERATURE=0.2
# Text replies are streamed from the provider; set false for one JSON body per request.
# AI_STREAM=true
# AI_MAX_TOKENS=8192
# Streamed text: first data within, then no gap longer than (seconds).
# AI_FIRST_TOKEN_TIMEOUT_SECONDS=20
# AI_IDLE_TIMEOUT_SECONDS=15
# Non-streamed requests (AI_STREAM=false / images), seconds per request.
# AI_TIMEOUT_SECONDS=30
# AI_IMAGE_TIMEOUT_SECONDS=60
# Upper bound per round (retry included); the repair round gets its own.
# AI_TOTAL_TIMEOUT_SECONDS=50
# AI_IMAGE_TOTAL_TIMEOUT_SECONDS=75
# Retries after a connection error, 429 or 5xx (timeouts are not retried).
# AI_MAX_RETRIES=1
# Level of the backend's own log lines (AI calls and errors).
# LOG_LEVEL=INFO
```

`DATABASE_URL` is mandatory. The backend has no localhost fallback. When
`MYSQL_HOST_PORT` is present, the backend verifies that the URL uses the same
port and exits with a configuration error if they differ.

`AI_VISION_ENABLED` defaults to `false`. Image intake also requires the
backend's AI feature and key to be configured. `AI_IMAGE_DETAIL` accepts
`low`, `high` (default), or `auto`. An invalid detail disables image intake.
Restart the backend after changing either setting.

### 2.3 Start MySQL

**Docker**:

```bash
docker compose up -d
```

**Homebrew**:

```bash
brew services start mysql
```

---

## 3. Backend (FastAPI)

### 3.1 Install Python Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3.2 Create the Tables, Then Start the API Server

Tables are created and upgraded by [Alembic](https://alembic.sqlalchemy.org/) migrations
(see 3.5). Run this once now, and again whenever you pull a change that adds a migration:

```bash
alembic upgrade head
```

It uses `DATABASE_URL` from `.env`, the same database as the API. Then start the server:

```bash
uvicorn stock_manager.api.main:app --reload --host 127.0.0.1 --port 8000
```

On startup the API checks that the database is at the newest migration. If it is not, it
refuses to start and says to run `alembic upgrade head`. It seeds the default inventory
categories on every start.

### 3.3 Verify

```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok","version":"0.9.0"}`

`/api/health` is public. Every other endpoint needs the token (see 3.7):

```bash
curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/api/items
```

### 3.4 API Documentation

Open http://localhost:8000/docs in your browser. Click **Authorize** and paste the API token to try protected endpoints.

### 3.5 Database Migrations (Alembic)

Schema changes are Alembic migrations in `migrations/versions/`. The API never creates or alters
tables itself.

**Upgrade an existing database** (after pulling a change with a new migration). Existing data
is kept:

```bash
alembic upgrade head
alembic current        # shows the database's revision, e.g. "0001 (head)"
```

**Databases created before Alembic** (by older versions, which ran `create_all` at startup) have
the tables but no revision. Run `alembic upgrade head` once: the baseline migration `0001`
skips tables that already exist and records the revision, without touching the data. This only
works for databases with the current schema (anything created after the structured categories
change, issue #33); older ones had to be rebuilt already.

**Changing the schema** (for developers): edit `stock_manager/api/models.py`, then generate and
review a migration, and commit it with the model change:

```bash
alembic revision --autogenerate -m "add items.barcode"
# review the new file in migrations/versions/, then:
alembic upgrade head
```

`tests/test_migrations.py` fails if the migrations do not produce exactly the schema in
`models.py`, so a model change without a migration is caught in CI. To preview the SQL without
running it: `alembic upgrade head --sql`.

**Starting over** (deletes all stock, restock, settings, recipe and favorite data):

```bash
mysql -u root -e "DROP DATABASE stock_manager; CREATE DATABASE stock_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
# Docker: docker exec -it stock_manager_mysql mysql -u root -p -e "<same SQL>"
alembic upgrade head
```

Then start the backend and re-import HowToCook recipes if you need them:

```bash
python3 scripts/import_howtocook.py /path/to/HowToCook
```

Running the import again on an existing database is safe: recipes already imported are skipped,
and their `category` is corrected to the `dishes/` directory (older versions stored the dish
folder name, e.g. `口水鸡` instead of `meat_dish`). Their ingredient and step lists are re-parsed
from the markdown, so rows from older imports become the same as a fresh import: `500克` stored as
the quantity, names like `番茄（）` or `鲤鱼（约 ，…）`, duplicated ingredients, and preview images,
headings or HTML stored as steps. HowToCook recipes cannot be edited in the app, so nothing
user-made is overwritten. The summary line reports how many were fixed.

Parsing rules: ingredient names drop bracketed notes (`鲤鱼（约 1.5 斤，…）` → `鲤鱼`, with quantity
`1.5 斤`). In steps and ingredients, images, sub-headings and table rows are skipped, links and
quotes keep their text, and HTML tags are removed. The full text stays in the recipe's markdown.

Only `dishes/**/*.md` is imported (`dishes/template/` is skipped). Older versions also imported
`tips/` and `.github/` files; the import lists any such rows. They are never recommended, and
you can delete them (with their favorites and history) by adding `--prune-non-recipes`:

```bash
python scripts/import_howtocook.py /path/to/HowToCook --prune-non-recipes
```

### 3.6 Network Exposure and Testing on a Real Phone

By default the API listens on `127.0.0.1`, so only this machine can reach it:

- iOS Simulator uses `http://localhost:8000/api`.
- Docker MySQL is published on the project-specific `127.0.0.1:3307` only.

Requests still need the API token (3.7), but anyone on the network can try to reach the API. To test on a real phone, start the backend on the LAN only while you need it:

```bash
API_HOST=0.0.0.0 ./scripts/start_backend.sh
```

In the iOS connection screen, use `http://YOUR_MAC_IP:8000/api`. Anyone on the same network can reach the API while it runs this way.

Bulk cleanup endpoints only delete finished records: `POST /api/items/clean` accepts `consumed` and `expired`, and `POST /api/restock/clean` accepts `done`. Other statuses return `400`.

### 3.7 API Authentication

All endpoints under `/api/` except `/api/health` require a shared token:

```
Authorization: Bearer <API_TOKEN>
```

There is one token per installation (one household). There are no per-member accounts.

1. Generate a token and put it in `.env` as `API_TOKEN`:

   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Restart the backend. If `API_TOKEN` is empty, the backend refuses to start with an explanatory error.
3. Enter the same token in the iOS app's connection screen.

Missing or wrong tokens return `401` with `WWW-Authenticate: Bearer`.

For local development only, `API_AUTH_DISABLED=true` skips the check. Do not combine it with `API_HOST=0.0.0.0`.

### 3.8 Tests and Checks

CI runs the same checks on every pull request:

```bash
python3 -m pip install -e ".[dev]"
python3 -m ruff check stock_manager scripts tests
python3 -m pytest -q --cov --cov-report=term-missing
```

Tests use in-memory SQLite and never touch your MySQL data. They do not read `.env`, AI is
off unless a test turns it on, and an AI request that a test did not mock fails that test
instead of reaching the provider. Coverage counts the API only
(the legacy CLI is excluded); the run fails if it drops below `fail_under` in `pyproject.toml`.
To run the suite on MySQL instead, point `TEST_DATABASE_URL` at an empty, throwaway database
(all its tables are dropped after each test):

```bash
TEST_DATABASE_URL="mysql+pymysql://root@localhost/stock_manager_test?unix_socket=/tmp/mysql.sock" python3 -m pytest -q
```

---

## 4. Native iOS App

### 4.1 Open the Project

```bash
open ios/StockManager.xcodeproj
```

In Xcode, select the `StockManager` scheme and an iPhone or iPad Simulator running iOS 17 or later, then press `Command-R`.

### 4.2 Connect

| Environment | Value |
|---|---|
| iOS Simulator | `http://localhost:8000/api` |
| Real device | `http://YOUR_MAC_IP:8000/api` |

Enter the shared `API_TOKEN` from `.env`, then tap **测试并连接**. The app stores the token in Keychain. Find the Mac IP for a real device with:

```bash
ipconfig getifaddr en0
```

### 4.3 Build and Test from Terminal

```bash
./ios/scripts/build.sh build
./ios/scripts/build.sh test
```

See the root [README](../../README.md#native-ios-deployment-step-by-step) for the complete first-time walkthrough, device signing, and troubleshooting.

---

## 5. Daily Startup

```bash
# Terminal 1: MySQL
docker compose up -d

# Terminal 2: Backend
cd /path/to/stock_manager
source .venv/bin/activate
alembic upgrade head   # no-op unless you pulled a new migration
uvicorn stock_manager.api.main:app --reload --host 127.0.0.1 --port 8000

# Then launch StockManager from Xcode or the installed iOS app.
```

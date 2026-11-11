# Setup

Prerequisites, database configuration, and steps to run the backend and frontend.

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

### 1.3 Node.js + npm

```bash
brew install node
node --version
npm --version
```

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

### 1.5 Expo Go

Install from App Store / Google Play.

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
DATABASE_URL=mysql+pymysql://stock_user:stock_password@127.0.0.1:3306/stock_manager

# Docker MySQL passwords (used when the volume is first created).
# If you change MYSQL_PASSWORD, change it in DATABASE_URL too.
MYSQL_ROOT_PASSWORD=root_password
MYSQL_PASSWORD=stock_password

# Shared API token (required). See 3.7.
API_TOKEN=paste-a-generated-token-here
# API_AUTH_DISABLED=true   # local development only

# 127.0.0.1 = only this machine. See 3.6 for testing on a real phone.
API_HOST=127.0.0.1
API_PORT=8000

# Browser origins allowed by CORS (Expo web). Native apps are not affected.
# CORS_ALLOW_ORIGINS=http://localhost:8081,http://127.0.0.1:8081,http://localhost:19006

# AI recipe recommendations (optional, for Explore Recipes)
# AI_RECIPE_ENABLED=false
# AI_BASE_URL=https://api.deepseek.com
# AI_API_KEY=
# AI_MODEL=deepseek-chat
# AI_TIMEOUT_SECONDS=60
# AI_TEMPERATURE=0.2
```

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
folder name, e.g. `口水鸡` instead of `meat_dish`). Their ingredient lists are re-parsed from the
markdown, so rows from older imports (`500克` stored as the quantity, names like `番茄（）` or
`鲤鱼（约 ，…）`, duplicated ingredients) become the same as a fresh import. HowToCook recipes
cannot be edited in the app, so nothing user-made is overwritten. The summary line reports how
many were fixed.

Ingredient names drop bracketed notes (`鲤鱼（约 1.5 斤，…）` → `鲤鱼`, with quantity `1.5 斤`);
the full text is kept in the recipe's markdown.

Only `dishes/**/*.md` is imported (`dishes/template/` is skipped). Older versions also imported
`tips/` and `.github/` files; the import lists any such rows. They are never recommended, and
you can delete them (with their favorites and history) by adding `--prune-non-recipes`:

```bash
python scripts/import_howtocook.py /path/to/HowToCook --prune-non-recipes
```

### 3.6 Network Exposure and Testing on a Real Phone

By default the API listens on `127.0.0.1`, so only this machine can reach it:

- iOS Simulator (`http://localhost:8000/api`) and Android Emulator (`http://10.0.2.2:8000/api`) work as usual.
- Docker MySQL is published on `127.0.0.1:3306` only.

Requests still need the API token (3.7), but anyone on the network can try to reach the API. To test on a real phone, start the backend on the LAN only while you need it:

```bash
API_HOST=0.0.0.0 ./scripts/start_backend.sh
```

Then set `frontend/app.json` → `expo.extra.apiBaseUrl` to `http://YOUR_MAC_IP:8000/api`. Anyone on the same network can reach the API while it runs this way.

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
3. Give the same token to the app (see the frontend notes in issue #41).

Missing or wrong tokens return `401` with `WWW-Authenticate: Bearer`.

For local development only, `API_AUTH_DISABLED=true` skips the check. Do not combine it with `API_HOST=0.0.0.0`.

### 3.8 Tests and Checks

CI runs the same checks on every pull request:

```bash
python3 -m pip install -e ".[dev]"
python3 -m ruff check stock_manager scripts tests
python3 -m pytest -q --cov --cov-report=term-missing
```

Tests use in-memory SQLite and never touch your MySQL data. Coverage counts the API only
(the legacy CLI is excluded); the run fails if it drops below `fail_under` in `pyproject.toml`.
To run the suite on MySQL instead, point `TEST_DATABASE_URL` at an empty, throwaway database
(all its tables are dropped after each test):

```bash
TEST_DATABASE_URL="mysql+pymysql://root@localhost/stock_manager_test?unix_socket=/tmp/mysql.sock" python3 -m pytest -q
```

---

## 4. Frontend (Expo + React Native)

### 4.1 Install Dependencies

```bash
cd frontend
npm install --legacy-peer-deps
```

### 4.2 Configure API URL

Edit `frontend/app.json` → `expo.extra.apiBaseUrl`:

| Environment | Value |
|---|---|
| iOS Simulator | `http://localhost:8000/api` |
| Real device | `http://YOUR_MAC_IP:8000/api` |

Find your Mac IP:

```bash
ipconfig getifaddr en0
```

### 4.3 Start Expo

```bash
npx expo start -c
```

### 4.4 Open in Expo Go

- iOS Simulator: Press `i` in the terminal
- Real device: Scan the QR code

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

# Terminal 3: Frontend
cd /path/to/stock_manager/frontend
npx expo start -c
```

# Stock Manager

This is a family inventory management application with a native iOS app (SwiftUI), FastAPI backend, MySQL database, and legacy local CLI support. It helps users track household stock, owners, locations, quantities, purchase dates, expiration dates, and consumption status. The app supports restocking workflows, reminders for expiring items, cleanup of outdated records, and settings for user-level preferences. It also includes recipe management, stock-based recipe recommendations, AI-assisted recipe exploration, and cooking flows that can optionally deduct used ingredients from inventory.

| Interface | Status | Database | Docs |
|---|---|---|---|
| iOS App + API | **Primary** | MySQL | [docs/app.md](docs/app.md) |
| CLI | Legacy / optional | SQLite | [docs/cli.md](docs/cli.md) |

---

## Native iOS Deployment: Step by Step

This walkthrough deploys the complete application on a Mac: MySQL runs in Docker, FastAPI runs on the Mac, and the SwiftUI client runs in an iOS Simulator or on an iPhone/iPad. No previous Python, Docker, or Xcode project knowledge is assumed.

### 0. What You Will Start

The application has three parts:

1. **MySQL** stores inventory, restock items, settings, and recipes.
2. **FastAPI** reads and writes MySQL and exposes the `/api` endpoints.
3. **Stock Manager for iOS** connects to FastAPI with a shared household token.

Keep MySQL and FastAPI running whenever the iOS app is in use. The iOS app does not contain an offline database.

### 1. Install the Prerequisites

Install the following on the Mac:

- **macOS with Xcode** capable of building iOS 17 or later. Install Xcode from the App Store, open it once, and allow it to install its additional components.
- **Command Line Tools**:

  ```bash
  xcode-select --install
  ```

- **Python 3.10 or later**. Check the installed version:

  ```bash
  python3 --version
  ```

- **Docker Desktop** from <https://www.docker.com/products/docker-desktop/>. Open Docker Desktop and wait until it reports that the engine is running.
- **Git**. It is normally installed with the Command Line Tools:

  ```bash
  git --version
  ```

Confirm Docker is ready before continuing:

```bash
docker --version
docker compose version
docker info
```

If `docker info` says it cannot connect to the daemon, start Docker Desktop and retry.

### 2. Get the Project and Enter Its Directory

For a new checkout:

```bash
git clone <your-stock-manager-repository-url>
cd stock_manager
```

If the repository is already on the Mac, open Terminal and change into its root directory. The following command should show `README.md`, `docker-compose.yml`, `ios/`, and `stock_manager/`:

```bash
ls
```

Run all backend commands below from this root directory unless a step says otherwise.

### 3. Create the Environment Configuration

Copy the checked-in template. `.env` is local configuration and must not be committed:

```bash
cp .env.example .env
```

Generate a strong shared API token:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Open `.env` in a text editor and paste the generated value after `API_TOKEN=`. A minimal local configuration looks like this:

```dotenv
DATABASE_URL=mysql+pymysql://stock_user:stock_password@127.0.0.1:3306/stock_manager
MYSQL_ROOT_PASSWORD=root_password
MYSQL_PASSWORD=stock_password
API_TOKEN=paste-the-generated-token-here
API_HOST=127.0.0.1
API_PORT=8000
```

Important details:

- `MYSQL_PASSWORD` and the password inside `DATABASE_URL` must match.
- Docker applies its MySQL passwords only when it creates the database volume for the first time. Changing `.env` later does not change users in an existing MySQL volume.
- Keep `API_TOKEN` private. The same value is entered into the iOS app on first launch.
- `API_AUTH_DISABLED=true` is only for isolated local development. Do not use it while exposing the API to a phone or another computer.

AI exploration is optional. Ordinary recipe browsing and stock-based recommendations work without an AI key. To enable AI exploration later, set `AI_RECIPE_ENABLED=true` and `AI_API_KEY` (plus the optional `AI_*` settings documented in [`.env.example`](.env.example)), then restart FastAPI: AI settings are read once at startup. The app checks `GET /api/capabilities` to decide whether to show Explore.

### 4. Start MySQL

Start the database container:

```bash
docker compose up -d
```

Confirm that it is running:

```bash
docker compose ps
```

The `stock_manager_mysql` row should say `Up`. MySQL may need several seconds on its first start. To inspect startup problems:

```bash
docker compose logs mysql
```

The database is published only on `127.0.0.1:3306`, so it is not directly exposed to the local network.

Using Homebrew MySQL instead of Docker also works: see [docs/app/setup.md](docs/app/setup.md) §1.4 (Option B) and §2.3. Create the database and user to match `DATABASE_URL`, then continue with step 5.

### 5. Create the Python Environment

Create an isolated virtual environment and install the backend plus development tools:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The shell prompt normally shows `(.venv)` while the environment is active. In every new Terminal window used for backend commands, return to the repository and reactivate it:

```bash
cd /path/to/stock_manager
source .venv/bin/activate
```

### 6. Create or Upgrade the Database Tables

Apply all Alembic migrations:

```bash
alembic upgrade head
alembic current
```

`alembic current` should show the current revision followed by `(head)`. This step keeps existing application data; it does not recreate the database.

### 7. Import the HowToCook Recipe Library

The migrations create empty recipe tables. Recommendations have no candidates until recipes are imported or created manually in the app.

Download the official HowToCook repository next to this project:

```bash
git clone --depth 1 https://github.com/Anduin2017/HowToCook.git ../HowToCook
```

Import its `dishes/` recipes:

```bash
python scripts/import_howtocook.py ../HowToCook
```

A successful run ends with a summary similar to:

```text
Import complete: 373 imported, 0 existing (...), 0 errors
```

The exact recipe count can change as HowToCook evolves. Re-running the same command is safe: existing source paths are recognized, and user-created recipes are not overwritten.

Do not add `--prune-non-recipes` during normal installation. That option intentionally deletes obsolete imported rows and should only be used after reviewing its effect.

To update the imported library later:

```bash
git -C ../HowToCook pull --ff-only
python scripts/import_howtocook.py ../HowToCook
```

Imported content retains its HowToCook source and license attribution in the API and app.

### 8. Start FastAPI

With the virtual environment active, start the backend:

```bash
./scripts/start_backend.sh
```

Leave this Terminal window open. For a Simulator-only setup the API listens on `127.0.0.1:8000` by default.

Alternatively, the equivalent direct command is:

```bash
uvicorn stock_manager.api.main:app --reload --host 127.0.0.1 --port 8000
```

The backend checks the database revision and API token during startup. Fix any reported error before opening the app.

### 9. Verify the Backend Before Opening Xcode

Open a second Terminal window. The public health endpoint should respond without a token:

```bash
curl http://127.0.0.1:8000/api/health
```

Expected shape:

```json
{"status":"ok","version":"0.9.0"}
```

Verify authentication and the recipe import by replacing the placeholder with the token from `.env`:

```bash
curl -H "Authorization: Bearer <YOUR_API_TOKEN>" \
  "http://127.0.0.1:8000/api/recipes?limit=1"
```

The response should be a non-empty JSON array. Then verify that the recommendation service has candidates:

```bash
curl -H "Authorization: Bearer <YOUR_API_TOKEN>" \
  "http://127.0.0.1:8000/api/recipes/recommendations?scene=all&limit=10"
```

Interactive API documentation is available at <http://127.0.0.1:8000/docs>. Use **Authorize** to supply the same bearer token.

### 10. Build and Run the Native iOS App

Open the Xcode project—not the repository root:

```bash
open ios/StockManager.xcodeproj
```

In Xcode:

1. Select the **StockManager** scheme in the toolbar.
2. Select an iPhone or iPad Simulator with iOS 17 or later.
3. Press **Run** or use `Command-R`.
4. On the welcome screen, enter:
   - Server address: `http://localhost:8000/api`
   - Shared API token: the exact `API_TOKEN` value from `.env`
5. Tap **测试并连接**.

The app first checks the public health endpoint and then uses the protected settings endpoint to verify the token. The address is stored in `UserDefaults`; the token is stored in the iOS Keychain and is not written to normal configuration files.

If `/api` is omitted from the server address, the app adds it automatically.

You can also build or test from Terminal:

```bash
./ios/scripts/build.sh build
./ios/scripts/build.sh test
```

The test command needs a matching installed Simulator. If `iPhone 17` is unavailable, specify one shown by Xcode, for example:

```bash
IOS_TEST_DESTINATION='platform=iOS Simulator,name=iPad Pro 13-inch (M5)' \
  ./ios/scripts/build.sh test
```

### 11. Connect a Physical iPhone or iPad

`localhost` on a physical device means the device itself, not the Mac. The Mac and device must be on the same trusted Wi-Fi network.

Find the Mac's Wi-Fi address:

```bash
ipconfig getifaddr en0
```

If that prints nothing, check **System Settings → Wi-Fi → Details → IP Address**.

Stop the Simulator-only backend with `Control-C`, then restart it on the local network:

```bash
API_HOST=0.0.0.0 ./scripts/start_backend.sh
```

In the iOS app, enter the Mac address, for example:

```text
http://192.168.1.25:8000/api
```

Then enter the same API token. Keep the backend Terminal open and allow incoming connections if macOS Firewall asks.

For Xcode device deployment, select the connected device as the run destination. Xcode may require choosing your Apple Development team under **Signing & Capabilities**. The device must trust the development certificate and have Developer Mode enabled when prompted.

Binding to `0.0.0.0` makes FastAPI reachable by other devices on that network. Keep token authentication enabled, use this only on a trusted LAN, and stop the backend when it is not needed. Do not expose this development server directly to the public internet. A permanent remote deployment should use HTTPS, a production ASGI process manager or container, firewall rules, and a private VPN or authenticated reverse proxy.

### 12. Daily Start and Stop

After the first installation, the normal start sequence is short:

```bash
docker compose up -d
source .venv/bin/activate
./scripts/start_backend.sh
```

Then launch the app. It restores and revalidates the saved connection automatically.

Stop FastAPI with `Control-C`. Stop MySQL without deleting its data:

```bash
docker compose stop
```

Start it again with `docker compose up -d`. Avoid `docker compose down -v`: the `-v` option deletes the MySQL data volume.

### 13. Updating an Existing Deployment

Before updating, make sure local work is committed or otherwise backed up. Then:

```bash
git pull --ff-only
source .venv/bin/activate
python -m pip install -e ".[dev]"
docker compose up -d
alembic upgrade head
git -C ../HowToCook pull --ff-only
python scripts/import_howtocook.py ../HowToCook
```

Restart FastAPI and rebuild the iOS app after the update. Migrations and the normal HowToCook import preserve existing inventory, settings, favorites, and user-created recipes.

### 14. Common Problems

#### Docker says it cannot connect to the daemon

Open Docker Desktop, wait until the engine is running, then retry `docker compose up -d`.

#### MySQL reports access denied

Check that `MYSQL_PASSWORD` matches the password in `DATABASE_URL`. If the Docker volume already existed before the password was changed, restore the original value or deliberately migrate/reset the MySQL user. Do not delete the volume unless its data has been backed up and a full reset is intended.

#### FastAPI says `API_TOKEN is not set`

Confirm that `.env` exists in the repository root, contains a non-empty `API_TOKEN=...`, and has no placeholder angle brackets. Restart FastAPI after changing it.

#### The app reports an invalid token or HTTP 401

Re-enter the exact `.env` token in the app. Tokens are case-sensitive. Restart the backend if `.env` changed, then use the Settings screen to replace the saved token.

#### The Simulator cannot connect

Verify `curl http://127.0.0.1:8000/api/health` on the Mac. Use `http://localhost:8000/api` in the Simulator and make sure FastAPI is still running.

#### A physical device cannot connect

Do not use `localhost`. Use the Mac's LAN IP, start FastAPI with `API_HOST=0.0.0.0`, keep both devices on the same Wi-Fi network, and check macOS Firewall or guest-network isolation.

#### The recipe library or recommendations are empty

Run the HowToCook import from step 7. Database migrations create tables but do not seed recipes. After import, verify `/api/recipes?limit=1`. Inventory improves recommendation scoring, but the system cannot recommend anything when the recipe table itself is empty.

#### Xcode reports an unavailable Simulator or CoreSimulator mismatch

Install a compatible iOS Simulator runtime from Xcode settings and make sure macOS, Xcode, and CoreSimulator are mutually compatible. Do not work around a toolchain mismatch by weakening the project deployment target.

#### Port 8000 is already in use

Stop the existing server, or set a different `API_PORT` in `.env` and use the same port in the iOS server address.

For more detail, see [the backend setup guide](docs/app/setup.md), [iOS-specific notes](ios/README.md), and [troubleshooting](docs/app/troubleshooting.md).

---

## Main App Features

- **Stock Management** — Add, edit, search, filter, consume and delete stock items
- **Expiration Reminders** — Track and review expiring items
- **Restock List** — Plan and track restock purchases
- **Recipe Library** — Browse, search, favorite, create, fork recipes
- **Today Recommendations** — Daily recipe suggestions based on current inventory
- **Explore Recipes** — AI-powered recipe ideas from structured preferences or a natural-language request

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
  app/setup.md          Prerequisites, database, and backend reference
  app/features.md       Core app features (inventory, restock, reminders)
  app/recipes.md        Recipe library, recommendations, explore
  app/troubleshooting.md Common issues
  cli.md                Legacy CLI documentation
ios/
  README.md             iOS app: running, signing, build and test
  STATE_MACHINES.md     iOS state conventions for async, navigation and forms
```

---



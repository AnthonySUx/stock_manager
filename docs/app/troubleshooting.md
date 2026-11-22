# Troubleshooting

Common issues and solutions.

---

### `zsh: command not found: docker`

Docker is not installed. Install Docker Desktop or use Homebrew MySQL as an alternative.

### Xcode cannot find a compatible Simulator

Install an iOS 17 or later Simulator runtime from Xcode settings. Make sure the installed Xcode and macOS/CoreSimulator versions are compatible.

### Xcode asks for a development team

Simulator builds do not need a paid Apple Developer account. For a physical device, select your own team under the StockManager target's **Signing & Capabilities** settings.

Do not commit a personal signing certificate or provisioning profile. A shared Team ID is not required for Simulator builds.

### `failed to load items`

Check:

1. Backend is running: `curl http://localhost:8000/api/health`
2. MySQL is running
3. If on real device, use your Mac IP instead of `localhost`
4. The app sends the API token (a `401` response means the token is missing or wrong)

### `401 Missing or invalid API token`

The request did not carry `Authorization: Bearer <API_TOKEN>`, or the token does not match `.env`. See [Setup §3.7](setup.md#37-api-authentication).

### `422 Unprocessable Entity`

The request body failed validation, for example a date that is not `YYYY-MM-DD`
(or does not exist, such as `2026-02-30`), or `null` sent for a required field.
The response `detail` is a list; each entry names the field (`loc`) and the reason (`msg`).

### Backend fails to start: `API_TOKEN is not set`

Set `API_TOKEN` in `.env` (see [Setup §3.7](setup.md#37-api-authentication)), or set `API_AUTH_DISABLED=true` for local development only.

### Backend fails to start: `... Run `alembic upgrade head` ...`

The database is not at the newest schema revision: it is empty, was created before migrations
were added, or you pulled a change with a new migration. Run `.venv/bin/python -m alembic upgrade head` in the
project directory, then start the backend again. Existing data is kept
(see [Setup §3.5](setup.md#35-database-migrations-alembic)).

If `.venv/bin/python` does not exist or a module is missing, run `./scripts/setup.sh`.
This creates the project environment and installs the complete dependency set.

### Connection refused

Backend not running. Start it with `./scripts/start_backend.sh`.

### Python module not found

```bash
./scripts/setup.sh
```

### SwiftUI app does not build

```bash
./ios/scripts/build.sh build
```

Read the first Xcode compiler error rather than later cascading errors. If the error mentions an unavailable Simulator or CoreSimulator mismatch, update the Xcode runtime instead of changing the app's deployment target.

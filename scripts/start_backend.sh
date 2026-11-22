#!/usr/bin/env bash
# Start the Stock Manager API backend server.
# Prerequisites: explicitly configured MySQL and Python dependencies installed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  echo "ERROR: .venv is missing. Create the project environment first:" >&2
  echo "  python3 -m venv .venv" >&2
  echo "  .venv/bin/python -m pip install --upgrade pip" >&2
  echo "  .venv/bin/python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

if ! "$VENV_PYTHON" -c 'import fastapi, python_multipart, sqlalchemy, uvicorn' >/dev/null 2>&1; then
  echo "ERROR: backend dependencies are incomplete. Install them with:" >&2
  echo "  .venv/bin/python -m pip install -e \".[dev]\"" >&2
  exit 1
fi

echo "Starting Stock Manager API..."
echo "Make sure the configured database is running (Docker: docker compose up -d)."
echo "DATABASE_URL is required; the Docker template uses project port 3307."
echo "After pulling schema changes, run: .venv/bin/python -m alembic upgrade head"
echo ""

# Default: only this machine can reach the API (iOS Simulator and Android
# Emulator still work). For a real phone on the LAN: API_HOST=0.0.0.0
HOST="${API_HOST:-127.0.0.1}"
if [ "$HOST" = "0.0.0.0" ]; then
  echo "WARNING: API is reachable from your local network (API_HOST=0.0.0.0)."
  echo ""
fi

exec "$VENV_PYTHON" -m uvicorn stock_manager.api.main:app --host "$HOST" --port "${API_PORT:-8000}" --reload

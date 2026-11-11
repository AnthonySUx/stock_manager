#!/usr/bin/env bash
# Start the Stock Manager API backend server.
# Prerequisites: MySQL running (Docker or Homebrew), Python deps installed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting Stock Manager API..."
echo "Make sure MySQL is running (docs/app/setup.md 2.3):"
echo "  Docker:   docker compose up -d"
echo "  Homebrew: brew services start mysql"
echo "After pulling schema changes, run: python3 -m alembic upgrade head"
echo ""

# Default: only this machine can reach the API (iOS Simulator and Android
# Emulator still work). For a real phone on the LAN: API_HOST=0.0.0.0
HOST="${API_HOST:-127.0.0.1}"
if [ "$HOST" = "0.0.0.0" ]; then
  echo "WARNING: API is reachable from your local network (API_HOST=0.0.0.0)."
  echo ""
fi

uvicorn stock_manager.api.main:app --host "$HOST" --port "${API_PORT:-8000}" --reload

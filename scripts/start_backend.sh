#!/usr/bin/env bash
# Start the Stock Manager API backend server.
# Prerequisites: Docker MySQL running, Python deps installed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting Stock Manager API..."
echo "Make sure Docker MySQL is running: docker compose up -d"
echo ""

# Default: only this machine can reach the API (iOS Simulator and Android
# Emulator still work). For a real phone on the LAN: API_HOST=0.0.0.0
HOST="${API_HOST:-127.0.0.1}"
if [ "$HOST" = "0.0.0.0" ]; then
  echo "WARNING: API is reachable from your local network (API_HOST=0.0.0.0)."
  echo ""
fi

uvicorn stock_manager.api.main:app --host "$HOST" --port "${API_PORT:-8000}" --reload

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

uvicorn stock_manager.api.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}" --reload

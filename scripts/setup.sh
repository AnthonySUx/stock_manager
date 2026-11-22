#!/usr/bin/env bash
# Setup script for the Stock Manager backend.
# The iOS app is built with Xcode; see docs/app/setup.md §4.

set -euo pipefail

echo "=== Stock Manager Setup ==="
echo ""

# --- Python Backend ---
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [ ! -x ".venv/bin/python" ]; then
  echo ">>> Creating .venv..."
  python3 -m venv .venv
fi

echo ">>> Installing Python dependencies..."
.venv/bin/python -m pip install -e ".[dev]"

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Start MySQL:   docker compose up -d"
echo "  2. Create tables: .venv/bin/python -m alembic upgrade head"
echo "  3. Start API:     ./scripts/start_backend.sh"
echo "  4. iOS app:       open ios/StockManager.xcodeproj (Xcode, iOS 17+ Simulator)"
echo ""

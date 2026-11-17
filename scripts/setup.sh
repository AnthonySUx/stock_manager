#!/usr/bin/env bash
# Setup script for the Stock Manager backend.
# The iOS app is built with Xcode; see docs/app/setup.md §4.

set -euo pipefail

echo "=== Stock Manager Setup ==="
echo ""

# --- Python Backend ---
echo ">>> Installing Python dependencies..."
pip install -e .

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Start MySQL:   docker compose up -d"
echo "  2. Create tables: alembic upgrade head"
echo "  3. Start API:     uvicorn stock_manager.api.main:app --reload"
echo "  4. iOS app:       open ios/StockManager.xcodeproj (Xcode, iOS 17+ Simulator)"
echo ""

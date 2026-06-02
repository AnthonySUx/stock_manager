#!/usr/bin/env bash
# Full setup script for Stock Manager app.
# Installs Python dependencies and frontend dependencies.

set -euo pipefail

echo "=== Stock Manager Setup ==="
echo ""

# --- Python Backend ---
echo ">>> Installing Python dependencies..."
pip install -e .

# --- Frontend ---
echo ">>> Installing frontend dependencies..."
cd frontend
npm install
cd ..

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo "  1. Start MySQL:   docker compose up -d"
echo "  2. Start API:     uvicorn stock_manager.api.main:app --reload"
echo "  3. Start Expo:    cd frontend && npx expo start"
echo ""

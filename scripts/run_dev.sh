#!/usr/bin/env bash

# ==============================================================================
# RubricEye Single Startup Script
# Runs FastAPI Backend and Vite Frontend concurrently with graceful shutdown.
# Usage:
#   ./scripts/run_dev.sh            (Starts Backend + Web Browser UI)
#   ./scripts/run_dev.sh --electron (Starts Backend + Electron Desktop UI)
# ==============================================================================

set -e

# Change directory to project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Load .env file if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    echo "Loading environment from .env file..."
    set -o allexport
    source "$PROJECT_ROOT/.env"
    set +o allexport
fi

# Determine frontend mode
FRONTEND_CMD="npm --prefix frontend run dev:vite"
MODE_LABEL="Web Browser UI (http://127.0.0.1:5173)"

if [[ "$1" == "--electron" ]]; then
    FRONTEND_CMD="npm --prefix frontend run dev"
    MODE_LABEL="Electron Desktop UI"
fi

echo "=================================================="
echo " Starting RubricEye Development Stack"
echo " Backend:  http://127.0.0.1:8765"
echo " Frontend: $MODE_LABEL"
echo "=================================================="

# Function to clean up background processes on Ctrl+C / Exit
cleanup() {
    echo ""
    echo "Shutting down RubricEye processes..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null || true
    fi
    echo "RubricEye stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# Start Backend
PYTHONPATH=backend backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload &
BACKEND_PID=$!
echo "✓ Backend started (PID $BACKEND_PID)"

# Start Frontend
$FRONTEND_CMD &
FRONTEND_PID=$!
echo "✓ Frontend started (PID $FRONTEND_PID)"

echo ""
echo "RubricEye is running! Press Ctrl+C to stop."
echo "--------------------------------------------------"

# Wait for background jobs
wait "$BACKEND_PID" "$FRONTEND_PID"

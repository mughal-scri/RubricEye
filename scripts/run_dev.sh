#!/usr/bin/env bash

# ==============================================================================
# RubricEye Single Startup Script
# Runs FastAPI Backend and Vite Frontend concurrently with graceful shutdown.
# Usage:
#   ./scripts/run_dev.sh            (Starts Backend + Web Browser UI)
#   ./scripts/run_dev.sh --electron (Starts Backend + Electron Desktop UI)
# ==============================================================================

set -e

BACKEND_PORT=8765
FRONTEND_PORT=5173

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

# --- API key sanity check -----------------------------------------------
# Silent failure here means grading calls fail later with no obvious cause,
# and it's easy to not notice until well into testing. Check it loudly now.
if [ -z "$DASHSCOPE_API_KEY" ] && [ -z "$RUBRICEYE_DASHSCOPE_API_KEY" ]; then
    echo ""
    echo "⚠ WARNING: Neither DASHSCOPE_API_KEY nor RUBRICEYE_DASHSCOPE_API_KEY is set."
    echo "  The app will start, but grading calls will fail until one is exported"
    echo "  or added to a .env file at the project root."
    echo ""
fi

# --- Port-conflict check --------------------------------------------------
# A pure-bash TCP probe -- no dependency on lsof/ss/fuser being installed.
port_in_use() {
    (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3<&- 3>&-
}

check_port_or_offer_kill() {
    local port="$1"
    local label="$2"
    if port_in_use "$port"; then
        echo "⚠ Port $port ($label) is already in use -- likely a leftover process"
        echo "  from a previous run that wasn't cleanly stopped (this is exactly what"
        echo "  produced '[Errno 98] Address already in use' silently in the background"
        echo "  before -- if this isn't caught here, the new backend can fail to bind"
        echo "  while an OLD process keeps serving stale code on that port instead)."
        read -r -p "  Kill the existing process on port $port and continue? [y/N] " reply
        if [[ "$reply" =~ ^[Yy]$ ]]; then
            local pid
            pid=$(command -v lsof >/dev/null 2>&1 && lsof -ti ":$port" || true)
            if [ -n "$pid" ]; then
                kill -9 $pid 2>/dev/null || true
                sleep 1
                echo "  Killed PID(s): $pid"
            else
                echo "  Could not auto-locate the PID (lsof unavailable) -- please stop it manually:"
                echo "    fuser -k ${port}/tcp   # or find it via: ps aux | grep $port"
                exit 1
            fi
        else
            echo "Aborting -- free the port manually and re-run."
            exit 1
        fi
    fi
}

check_port_or_offer_kill "$BACKEND_PORT" "backend"
check_port_or_offer_kill "$FRONTEND_PORT" "frontend"

# Determine frontend mode
FRONTEND_CMD="npm --prefix frontend run dev:vite"
MODE_LABEL="Web Browser UI (http://127.0.0.1:$FRONTEND_PORT)"

if [[ "$1" == "--electron" ]]; then
    FRONTEND_CMD="npm --prefix frontend run dev"
    MODE_LABEL="Electron Desktop UI"
fi

echo "=================================================="
echo " Starting RubricEye Development Stack"
echo " Backend:  http://127.0.0.1:$BACKEND_PORT"
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
    # uvicorn --reload runs a supervisor + worker process pair; killing the
    # tracked PID doesn't always cascade to the worker cleanly on an abrupt
    # exit, which is exactly what leaves the orphan that caused the port
    # conflict above. Sweep for it explicitly as a fallback.
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    echo "RubricEye stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# Start Backend
PYTHONPATH=backend backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" --reload &
BACKEND_PID=$!

# --- Real health check, not just "the command ran" ------------------------
echo -n "Waiting for backend to respond on :$BACKEND_PORT"
BACKEND_READY=0
for _ in $(seq 1 30); do
    if port_in_use "$BACKEND_PORT"; then
        BACKEND_READY=1
        break
    fi
    echo -n "."
    sleep 0.5
done
echo ""

if [ "$BACKEND_READY" -eq 1 ]; then
    echo "✓ Backend confirmed listening on :$BACKEND_PORT (PID $BACKEND_PID)"
else
    echo "✗ Backend did NOT come up within 15s -- check the output above for the real error"
    echo "  (previously this failure was easy to miss because success was printed"
    echo "  unconditionally before the process had actually bound to the port)."
    exit 1
fi

# Start Frontend
$FRONTEND_CMD &
FRONTEND_PID=$!
echo "✓ Frontend started (PID $FRONTEND_PID)"

echo ""
echo "RubricEye is running! Press Ctrl+C to stop."
echo "--------------------------------------------------"

# Wait for background jobs
wait "$BACKEND_PID" "$FRONTEND_PID"
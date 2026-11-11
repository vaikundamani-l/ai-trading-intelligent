#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PYTHON_BIN="/home/shadow-khan/myenv/bin/python"

echo "=========================================================="
echo " Starting BTC Quantum Intelligence (Full-Stack Platform)  "
echo "=========================================================="

# Trap kill signal to terminate background processes on Ctrl+C
cleanup() {
    echo ""
    echo "Stopping BTC Quantum Intelligence services..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 1. Start Backend FastAPI
echo "[1/2] Launching Backend on http://localhost:8000 ..."
cd "$DIR/backend"
PYTHONPATH="$DIR/backend" $PYTHON_BIN -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be healthy
sleep 2

# 2. Start Frontend Next.js
echo "[2/2] Launching Frontend on http://localhost:3000 ..."
cd "$DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo "=========================================================="
echo " BTC QUANTUM INTELLIGENCE IS LIVE!                        "
echo " Dashboard: http://localhost:3000                         "
echo " Backend API: http://localhost:8000/docs                   "
echo " Press Ctrl+C to stop all servers.                        "
echo "=========================================================="

wait

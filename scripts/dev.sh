#!/usr/bin/env bash
# Start luciaGo: backend (FastAPI + KataGo) + frontend (Vite).
# Usage: bash scripts/dev.sh
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYEXE="${PYEXE:-/f/anaconda/envs/lucia-go/python.exe}"

if [ ! -f "$PYEXE" ]; then
  echo "Python not found at $PYEXE. Run: conda activate lucia-go, or set PYEXE."
  exit 1
fi

echo "==> Starting backend (FastAPI) on http://127.0.0.1:8000"
(
  cd "$ROOT/backend"
  "$PYEXE" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
) &
BACK_PID=$!
echo "    backend PID: $BACK_PID"

echo "==> Starting frontend (Vite) on http://localhost:5173"
(
  cd "$ROOT/frontend"
  npm run dev
) &
FRONT_PID=$!
echo "    frontend PID: $FRONT_PID"

echo ""
echo "Open http://localhost:5173 (LAN: http://<your-ip>:5173)"
echo "API docs: http://127.0.0.1:8000/docs"
echo "Press Ctrl+C to stop both."

trap 'kill "$BACK_PID" "$FRONT_PID" 2>/dev/null' EXIT INT TERM
wait

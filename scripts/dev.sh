#!/usr/bin/env bash
# One-command local startup for the AirFed dashboard + control API.
#
#   ./scripts/dev.sh
#
# Environment:
#   AIRFED_HOST        bind host for the API (default 127.0.0.1)
#   AIRFED_PORT        API port (default 8010)
#   AIRFED_SKIP_BUILD  set to 1 to reuse the existing frontend dist/
#
# The dashboard process manager launches the MQTT broker and coordinator from
# the UI ("Start broker + coordinator"), and launches simulated workers from
# the Workers page or a federated session. Remote devices only need MQTT.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  echo "error: $PYTHON is missing. Create it with:" >&2
  echo "  python3.12 -m venv .venv && source .venv/bin/activate" >&2
  echo "  python -m pip install -r requirements.txt -r dashboard/requirements.txt" >&2
  exit 1
fi

if ! "$PYTHON" -c "import fastapi, uvicorn, paho.mqtt.client, numpy, pandas" >/dev/null 2>&1; then
  echo "error: dashboard dependencies are missing. Run:" >&2
  echo "  $PYTHON -m pip install -r requirements.txt -r dashboard/requirements.txt" >&2
  exit 1
fi

# Kill any existing processes on the ports
echo "==> Cleaning up existing processes..."
pkill -f "uvicorn.*dashboard.backend.main" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1

if [ "${AIRFED_SKIP_BUILD:-0}" != "1" ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "==> building dashboard frontend"
    npm --prefix dashboard/frontend run build
  else
    echo "warning: npm is not installed; serving API only" >&2
  fi
fi

# Start the frontend dev server in the background if npm is available
if command -v npm >/dev/null 2>&1; then
  cd "$ROOT/dashboard/frontend"
  npm run dev &
  FRONTEND_PID=$!
  cd "$ROOT"
fi

echo "==> AirFed API on http://${AIRFED_HOST:-127.0.0.1}:${AIRFED_PORT:-8010}"
echo "==> Frontend on http://localhost:5173"

# Run uvicorn in the background
"$PYTHON" -m uvicorn dashboard.backend.main:app \
  --host "${AIRFED_HOST:-127.0.0.1}" \
  --port "${AIRFED_PORT:-8010}" &
UVICORN_PID=$!

# Keep script running and wait for either process to exit
echo "==> Servers running. Press Ctrl+C to stop."
wait $UVICORN_PID
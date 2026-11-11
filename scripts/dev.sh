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

if [ "${AIRFED_SKIP_BUILD:-0}" != "1" ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "==> building dashboard frontend"
    npm --prefix dashboard/frontend run build
  else
    echo "warning: npm is not installed; serving API only" >&2
  fi
fi

if "$PYTHON" -c "import socket,sys; s=socket.socket(); s.settimeout(0.3); sys.exit(0 if s.connect_ex(('127.0.0.1', int('${AIRFED_PORT:-8010}'))) == 0 else 1)"; then
  echo "error: port ${AIRFED_PORT:-8010} is already in use; stop the other API first" >&2
  echo "  lsof -nP -iTCP:${AIRFED_PORT:-8010} -sTCP:LISTEN" >&2
  exit 1
fi

echo "==> AirFed API on http://${AIRFED_HOST:-127.0.0.1}:${AIRFED_PORT:-8010}"
exec "$PYTHON" -m uvicorn dashboard.backend.main:app \
  --host "${AIRFED_HOST:-127.0.0.1}" \
  --port "${AIRFED_PORT:-8010}"

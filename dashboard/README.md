# AirFed Dashboard

Read-only operations dashboard for the **Federated PM2.5 Forecasting on IoT Nodes** project.

The dashboard is a separate client from the FL coordinator — it subscribes to MQTT
events, reads the existing model registry, and never publishes commands or model
updates. It surfaces node health, round progress, model versions, historical
air-quality replay vs. model predictions, performance comparisons, and
communication byte counts.

## Stack

- **Backend:** Python FastAPI (`dashboard/backend/`), Paho MQTT observer
  (`dashboard/backend/mqtt_observer.py`), WebSocket notification channel
  (`/ws`), read-only endpoints over the existing registry and CSV experiment
  files.
- **Frontend:** React 18 + TypeScript + Vite, Tailwind CSS, Recharts, Lucide
  icons. Five hash-routed pages plus a data-source aware status bar.

## Setup

Requirements: a Python 3.12 virtualenv with `paho-mqtt`, `fastapi`,
`uvicorn[standard]`, `httpx`, `numpy`, `pandas`. (TensorFlow is not required for
the dashboard — only `dashboard/requirements.txt` adds the web stack.)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt           # server-side deps first
python -m pip install -r dashboard/requirements.txt  # fastapi/uvicorn/httpx
npm install                                    # once, per machine
```

## Run the backend

From the project root, with the `.venv` activated:

```bash
uvicorn dashboard.backend.main:app \
    --host 0.0.0.0 --port 8010 --reload
```

Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness + broker state |
| GET | `/api/status` | Node cards, current round, latest/best model |
| GET | `/api/rounds` | Round history and loss curve |
| GET | `/api/model` | Latest/best version, versions list, transfer size |
| GET | `/api/metrics` | Centralized / local-only / persistence / FedAvg comparison |
| GET | `/api/air-quality?node=<node>` | Historical replay, actual vs. predicted, temp/rh |
| GET | `/api/communication` | MQTT events, bytes up/down, ack rates |
| WS | `/ws` | Live telemetry push |

The dashboard serves the built frontend from `dashboard/frontend/dist` if it exists;
otherwise the SPA route falls back to the API list on `/`.

## Run the frontend

```bash
npm run dev                       # http://localhost:5173  (development)
npm run build                     # dist/, served by uvicorn
npm run preview                   # standalone preview on :4173
```

For production, build the SPA and point uvicorn at `--reload`; the SPA talks to
the same backend on port 8010. On an Android phone, `npm run dev` exposes the
same ports, so both the MacBook and the phone land on the same Wi-Fi network.

## Pages

1. **Overview** — five node cards with online/offline/stale status, training vs.
   inference roles, current round, latest global model version, plus the
   data-source banner (`live_mqtt` / `registry_only` / `unavailable`).
2. **Federated** — live round progress, selected nodes, stage timeline
   (client selection → local training → weight upload → update validation →
   FedAvg aggregation → model registration), weight checksum stats, round
   history table with acceptance columns.
3. **Air Quality** — node selector, PM2.5 historical replay, actual vs.
   predicted overlay, temperature & humidity series, one-hour-ahead
   predictions. Distinguishes historical replay from any real-time sensor feed;
   the API reports `is_realtime: false` explicitly.
4. **Performance** — centralized / local-only / persistence / FedAvg rows
   across raw and clipped targets, seed-wise breakdown, total bytes moved, and
   validation loss history. No metrics are recomputed; the dashboard reads the
   existing `results.csv`, `results_by_seed.csv`, and `stage4_summary.json`.
5. **Communication** — MQTT topic contract, recent events with retained flag
   and direction, per-chunk SHA-256 verdicts, accepted/rejected ack counts, and
   bytes uploaded vs. downloaded totals.

## Data provenance notes

- `is_realtime: false` and `prediction_source: persistence_reference` mean the
  widget is showing the project's existing persistence baseline as a fallback, not
  a real-time sensor stream. Run
  `python -m dashboard.backend.export_predictions` in the provided commands to
  emit genuine FedAvg predictions for every node.
- Raw PM2.5, temperature, and humidity readings never leave a node or enter the
  MQTT payloads (privacy contract from Stage 3). The dashboard displays only
  derived replay values.

## Tests

```bash
python -m pytest -q tests/test_dashboard_backend.py -s
ruff check common baselines tests node server experiments dashboard
```

Back-backed unit tests cover dataset parsing, registry snapshot parsing, the
TelemetryStore ingest state machine (round lifecycle, checksum verification,
rejected acks), metrics comparison assembly, and all six REST endpoints plus
the WebSocket hello exchange. They skip MQTT integration entirely by driving
TelemetryStore directly, so the suite runs without a running broker.

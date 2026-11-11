# AirFed Dashboard

Operations dashboard and local process controller for the **Federated PM2.5
Forecasting on IoT Nodes** project.

The dashboard both **observes** the federated deployment and **controls** it:

- Observes MQTT telemetry, the coordinator model registry, round history,
  air-quality replay, and communication events.
- Launches and stops the local Mosquitto broker, the long-lived control
  coordinator, and arbitrary numbers of simulated workers.
- Publishes session commands (`start`, `pause`, `resume`, `stop`) and a full
  training configuration over MQTT.
- Never rewrites the coordinator's model registry or fabricates round progress.
  Round stages come from retained coordinator `round_progress` / `round_summary`
  messages, so skipped work is displayed as `skipped`, not `complete`.

Remote devices are never launched by the process manager. They connect over
MQTT and register themselves on `{base_topic}/fl/workers/{id}/register`.

## One-command local startup

From the project root:

```bash
./scripts/dev.sh
```

The script builds the frontend, checks dependencies and the API port, and
starts the FastAPI backend on `http://127.0.0.1:8010`. Then:

1. Open **Workers** → **Start broker + coordinator**.
2. Launch simulated workers (dummy or real) or start a training session from
   **Federated** with `simulation_workers > 0`.

Useful environment overrides:

```bash
AIRFED_HOST=0.0.0.0 AIRFED_PORT=8010 ./scripts/dev.sh
AIRFED_SKIP_BUILD=1 ./scripts/dev.sh   # reuse frontend/dist
```

## Stack

- **Backend:** Python FastAPI (`backend/`), Paho MQTT observer, WebSocket
  channel (`/ws`), MQTT control publisher, and a subprocess manager.
- **Frontend:** React 18 + TypeScript + Vite, Tailwind CSS, Lucide icons.
  Six hash routes are implemented: Overview, Workers, Federated, Air Quality,
  Performance, Communication.

## Setup

Requirements: Python 3.12 virtualenv with the project dependencies plus
`fastapi`, `uvicorn[standard]`, `httpx`, `numpy`, `pandas`, `paho-mqtt`.
TensorFlow is only needed for real (non-dummy) simulation workers, not for the
dashboard itself.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r dashboard/requirements.txt
npm --prefix dashboard/frontend install
```

Mosquitto must be installed for the dashboard to own a local broker:
`brew install mosquitto` (macOS) or `apt install mosquitto` (Linux). An already
running broker on the configured host/port is used as-is.

## Run

```bash
./scripts/dev.sh
# or: uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8010
```

For frontend development:

```bash
npm --prefix dashboard/frontend run dev   # http://localhost:5173 (proxied API)
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness, broker reachability, coordinator state |
| GET | `/api/status` | Nodes, dynamic workers, session, round, models, processes |
| GET | `/api/rounds` | Registry round history and loss curve |
| GET | `/api/model` | Latest/best model, versions, transfer size |
| GET | `/api/metrics` | Stage 4 comparison and seed results |
| GET | `/api/air-quality?node=<id>` | Historical replay, observed vs. predicted |
| GET | `/api/communication` | MQTT events, bytes, checksums, topic contract |
| GET | `/api/session` | Session state, current round, summaries, workers, processes |
| GET | `/api/workers` | Dynamic worker registry and managed worker processes |
| GET | `/api/rounds/live` | Authoritative retained round progress/summaries |
| GET | `/api/processes` | Managed process status and crash records |
| GET | `/api/logs?name=<process>&lines=120` | Captured stdout/stderr tail |
| POST | `/api/control/session` | `start` / `pause` / `resume` / `stop` with config |
| POST | `/api/workers/launch` | Launch 1–200 simulated training/inference workers |
| POST | `/api/workers/stop` | Stop specific worker IDs or all workers |
| POST | `/api/processes/start` | Start `broker`, `coordinator`, `stack` |
| POST | `/api/processes/stop` | Stop one process or `all` |
| WS | `/ws` | Live telemetry push |

## Pages

1. **Overview** — node/worker cards, data-source banner, current round, latest
   and best model, broker/observer health.
2. **Workers** — registered workers with role, shard, samples, heartbeat age,
   state and progress; launch/stop simulated workers; stack controls; crash
   records; process log viewer.
3. **Federated** — full training configuration (mode, rounds, min/max workers,
   selection policy, local epochs, deadline, window, learning rate, simulation
   worker count), start/pause/resume/stop controls, frozen per-round selection,
   accurate stage track, accepted/rejected updates, retained round summaries,
   and registry round history.
4. **Air Quality** — node selector, observed PM2.5 replay, federated
   predictions, temperature/humidity, and explicit provenance.
5. **Performance** — Stage 4 method comparison, seed statistics, validation
   loss per round, latest/best model registry state.
6. **Communication** — broker state, live round stages, model transfer
   metadata, checksum verdicts, event stream with direction/retained flags, and
   the topic contract.

## Dynamic worker contract

| Topic | Direction | Purpose |
| --- | --- | --- |
| `{base}/fl/control` | dashboard → coordinator | Session commands and training config |
| `{base}/fl/session` | coordinator → dashboard | Retained session state |
| `{base}/fl/workers/{id}/register` | worker → dashboard/coordinator | Retained self-registration and dataset/model metadata |
| `{base}/fl/workers/{id}/state` | worker → dashboard/coordinator | Non-retained heartbeat and training state |
| `{base}/fl/round/{n}/progress` | coordinator → dashboard | Retained stage status |
| `{base}/fl/round/{n}/summary` | coordinator → dashboard | Retained audit record per round |

A retained registration is history, not proof of life. Only fresh `state`
heartbeats keep a worker online; old states expire after the heartbeat window.
Inference-only workers register and show in the UI but are never selected for
training or aggregation.

## Data provenance notes

- `is_realtime: false` and `prediction_source: persistence_reference` mean the
  widget is showing the project's existing persistence baseline as a fallback,
  not a real-time sensor stream.
- Raw PM2.5, temperature, and humidity readings never leave a node or enter
  MQTT payloads. The dashboard displays only derived replay values.
- The dashboard is a separate MQTT subscriber. It does not modify the model
  registry; the coordinator writes all model/round artifacts.

## Tests

```bash
source .venv/bin/activate
python -m pytest -q tests/test_dashboard_backend.py tests/test_worker_registry.py \
  tests/test_simulation.py tests/test_process_manager.py
python -m pytest -q tests/test_dynamic_fl.py      # real broker, dummy workers
npm --prefix dashboard/frontend run typecheck
```

The dashboard tests drive `TelemetryStore`, the worker registry, simulation
sharding, and the process manager directly, plus REST/WebSocket endpoints. The
dynamic integration test uses a private broker and dummy workers, so it needs
no TensorFlow.

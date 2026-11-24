# AirFed Dashboard

**Federated PM2.5 Forecasting Dashboard for IoT Nodes**

An operations dashboard and local process controller for monitoring and managing a federated learning system that forecasts next-hour PM2.5 air quality across a network of IoT sensors.

## Overview

AirFed enables real-time observation and control of a federated learning deployment for air quality prediction. The dashboard connects to MQTT-based telemetry, monitors the coordinator's model registry, tracks round history, and provides air-quality replay capabilities.

### Key Features

- **Real-time Monitoring**: Observe MQTT telemetry, coordinator state, and model registry updates
- **Session Control**: Start, pause, resume, and stop federated training sessions
- **Worker Management**: Launch and stop simulated training/inference workers
- **Air Quality Intelligence**: Historical replay and federated predictions from PM2.5 sensors
- **Network Topology**: Visual map of IoT nodes and their communication status
- **Experiment Tracking**: Stage 4 method comparison with seed statistics

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AirFed System Architecture                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────┐     MQTT    ┌──────────────────────┐              │
│  │  Coordinator         │◄───────────►│   Workers (IoT)      │              │
│  │  (Federated FL)      │  (Broker)   │   - Training         │              │
│  └──────────┬───────────┘             │   - Inference        │              │
│             │                         └──────────────────────┘              │
│             │                                                              │
│  ┌──────────▼───────────┐                                                  │
│  │  Dashboard Backend   │                                                  │
│  │  (FastAPI + MQTT)    │                                                  │
│  │                      │                                                  │
│  │  ┌─────────────────┐  │    ┌──────────────────┐                         │
│  │  │ MQTT Observer   │  │    │ Control Publisher│                         │
│  │  └─────────────────┘  │    └──────────────────┘                         │
│  │                      │                                                  │
│  │  WebSocket Feed ◄───┤                                                  │
│  └──────────┬───────────┘                                                  │
│             │                                                              │
│  ┌──────────▼───────────┐                                                  │
│  │  Dashboard Frontend   │                                                  │
│  │  (React + TypeScript) │                                                  │
│  │                      │                                                  │
│  │  Pages: Overview,      │                                                  │
│  │         Gateways,     │                                                  │
│  │         Federated     │                                                  │
│  │         Learning,   │                                                  │
│  │         Air Quality,  │                                                  │
│  │         Experiments,  │                                                  │
│  │         Network Topo, │                                                  │
│  │         Terminal      │                                                  │
│  └──────────────────────┘                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Data & Control Flow                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Workers] ──MQTT msgs──► [Broker] ──MQTT──► [Coordinator]      │
│       ▲                    │                    │               │
│       │                    │                    ▼               │
│  [Simulation] ──────────────┼──────────────► [Registry Files]    │
│                             │                                   │
│                             ▼                                   │
│                      [Dashboard Backend]                        │
│                            │                                    │
│            ┌───────────────┼───────────────┐                    │
│            │               │               │                    │
│            ▼               ▼               ▼                    │
│     [REST API]     [WebSocket]      [Control Publisher]        │
│            │                             │                      │
│            └───────────────┬─────────────┘                      │
│                            │                                    │
│                            ▼                                    │
│                   [Dashboard Frontend]                          │
│                            │                                    │
│                            ▼                                    │
│                      [Browser UI]                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python FastAPI | REST API and WebSocket |
| | Paho MQTT | MQTT client for observer |
| | uvicorn | ASGI server |
| **Frontend** | React 18 | UI framework |
| | TypeScript | Type safety |
| | Vite | Build tool |
| | plain CSS | Styling (no Tailwind) |
| | Lucide | Icons |
| **Data** | MQTT | Message transport |
| | JSON files | Registry persistence |
| | CSV | Round history |

## Project Structure

```
iot/
├─ backend/                    # Dashboard backend
│  ├─ main.py                  # FastAPI application
│  ├─ mqtt_observer.py         # MQTT subscription handler
│  ├─ control.py               # Control message publisher
│  ├─ telemetry.py             # WebSocket telemetry store
│  ├─ registry.py              # Model registry reader
│  └─ ...                      # API endpoints
├─ frontend/                   # Dashboard frontend
│  ├─ src/
│  │  ├─ pages/                 # Page components
│  │  ├─ components/            # UI components
│  │  ├─ api/                   # API client
│  │  ├─ styles.css             # CSS utilities
│  │  └─ App.tsx                # Router
│  └─ ...                       # Vite config
├─ common/                     # Shared utilities
│  ├─ mqtt_utils.py            # MQTT helpers
│  ├─ worker_protocol.py       # FL protocol
│  └─ ...                      # Common modules
├─ simulator/                  # Simulation engine
│  ├─ engine.py                # Network simulator
│  ├─ api.py                   # Simulation API
│  └─ workers/                 # Worker implementations
├─ baselines/                  # Baselines (persistence, centralized)
├─ tests/                      # Test suite
├─ scripts/                    # Development scripts
└─ data/                       # Data directory
```

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- Mosquitto MQTT broker

### Install

```bash
# Clone and enter
cd /path/to/iot

# Python environment
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# Install dependencies
python -m pip install -r requirements.txt
python -m pip install -r dashboard/requirements.txt

# Install frontend dependencies
npm --prefix dashboard/frontend install

# Install Mosquitto (macOS)
brew install mosquitto
```

### Development

```bash
# Start development environment (all-in-one script)
./scripts/dev.sh

# Or run components separately:
# Backend API
uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8010

# Frontend (dev server with proxy)
npm --prefix dashboard/frontend run dev

# Open browser
open http://localhost:8010
```

### Production Build

```bash
# Build frontend
npm --prefix dashboard/frontend run build

# Serve full stack
./scripts/dev.sh  # or run backend and serve frontend dist
```

## Dashboard Pages

| Page | Purpose | Key Features |
|------|---------|--------------|
| **Overview** | System health at a glance | Node cards, broker status, current round, model versions |
| **Network Topology** | IoT node map | Visual topology, online/offline status, gateway connections |
| **Gateways** | FL gateway management | Client registry, contribution tracking, start/stop controls |
| **Federated Learning** | Session control | Training config, stage tracking, round history, model registry |
| **Models** | Model comparison | Latest/best, validation loss, parameter transfer size |
| **Air Quality** | Sensor data replay | PM2.5 predictions, observed vs predicted, humidity/temperature |
| **Experiments** | Baseline comparison | Method comparison, seed statistics, validation curves |
| **Terminal** | Interactive console | Command history, system logs, live output |

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | System health, broker status, coordinator state |
| `GET` | `/api/status` | Full system status (nodes, workers, session, models) |
| `GET` | `/api/rounds` | Round history with loss curves |
| `GET` | `/api/model` | Latest/best model, versions, transfer info |
| `GET` | `/api/metrics` | Stage 4 comparison, seed results |
| `GET` | `/api/air-quality` | Historical replay data |
| `GET` | `/api/communication` | MQTT events, bytes, checksums |
| `GET` | `/api/session` | Session state, round summaries |
| `GET` | `/api/workers` | Worker registry and processes |
| `GET` | `/api/fl/gateways` | FL gateway status |
| `GET` | `/api/logs` | Process stdout/stderr tails |
| `POST` | `/api/control/session` | Start/pause/resume/stop session |
| `POST` | `/api/workers/launch` | Launch simulated workers |
| `POST` | `/api/workers/stop` | Stop worker processes |

### WebSocket

- `/ws` - Live telemetry with MQTT events, session updates, and status changes

## MQTT Topic Contract

```
{base_topic}/
├─ fl/
│  ├─ control                    # Session commands (publish)
│  ├─ session                     # Session state (retained)
│  ├─ round/{n}/progress         # Round stage (retained)
│  ├─ round/{n}/summary          # Round summary (retained)
│  └─ workers/{id}/
│     ├─ state                   # Heartbeat (non-retained)
│     └─ register               # Self-registration (retained)
└─ workers/                      # Telemetry from workers
```

## Testing

```bash
# Run backend tests
source .venv/bin/activate
python -m pytest -q tests/

# Frontend typecheck
npm --prefix dashboard/frontend run typecheck

# Integration tests
python -m pytest -q tests/test_dashboard_integration.py
```

## Configuration

Environment variables:

```bash
AIRFED_HOST=0.0.0.0           # API host
AIRFED_PORT=8010              # API port
AIRFED_BROKER_HOST=localhost  # MQTT broker
AIRFED_BROKER_PORT=1883       # MQTT port
AIRFED_BASE_TOPIC=airfed      # MQTT topic prefix
```

## License

This project is for educational and research purposes.

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Paho MQTT Python Client](https://www.eclipse.org/paho/)
- [React Documentation](https://react.dev/)
- [Federated Learning Book](https://the-dlr.org/Book/)
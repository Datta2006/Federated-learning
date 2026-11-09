---
name: sprint26-airfed-dashboard
description: Entry point for tracking the AirFed dashboard development sprint — list of completed tasks, remaining items, design notes, and blockers.
metadata:
  type: project
---

# Sprint 26: AirFed Dashboard

## What is being built
A professional, responsive React + TypeScript + Vite dashboard called **AirFed** that visualizes the existing Federated PM2.5 Forecasting on IoT Nodes project. The dashboard has five pages (Overview, Federated Learning, Air Quality, Performance, Communication), dark professional styling, and works on both MacBook and Android browsers over the same Wi-Fi network.

## Completed work so far
- Backend skeleton created under `dashboard/backend/` (FastAPI app, WebSocket endpoint, MQTT observer, settings/registry/telemetry modules)
- Frontend scaffolding under `dashboard/frontend/` (Vite config, Tailwind setup, UI primitives, API client, types, hooks)
- Backend tests written (`tests/test_dashboard_backend.py`) — 9 passing test cases covering:
  - Dataset row parsing
  - Registry snapshot building
  - Metrics comparison assembly
  - Telemetry round lifecycle + checksums
  - Historical round fallback
  - Air quality prediction merging
  - Persistence fallback explicitness
  - Raw dataset leading gap fill
  - Full API endpoint + WebSocket integration (TestClient)
- Unit tests for backend modules (`test_federated.py`, `test_dag_runner.py`, etc.) continue to pass
- Stale registry watch logic implemented
- Live metrics endpoint built
- Base URL discovery implemented
- Styling system created (dark navy background, emerald green accents, responsive breakpoints)

## In progress
- **First page implementation** (Overview): creating component structure, types, hooks

## Blockers
- None — development continues without blockers

## Design decisions
- Use Tailwind CSS for all styling; Recharts for charts
- Dark professional theme: deep navy/charcoal background, emerald green for connected nodes and successful aggregation, blue for model communication, red for rejected updates and offline nodes
- Maintain strict separation between live telemetry and historical replay data
- All existing tests must continue to pass

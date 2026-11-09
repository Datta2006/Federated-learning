# AirFed Overview Page Design

**Project:** Federated PM2.5 Forecasting on IoT Nodes (Stage 4)
**Date:** 2026-11-06
**Scope:** One React page only. Not architectural; bounded by the approved FrontendAgent / PlanSkill design gate below. Nothing writes to the FL coordinator or MQTT broker.
**File:** `docs/superpowers/specs/2026-11-06-airfed-overview-design.md`

---

## 1. Intent and success criteria

The Overview page is the landing surface of the read-only dashboard. A student opening the Android preview or the desktop build should understand, in under five seconds, which five nodes are online, whether any federated round is in flight, what global model version is live, and where that model sits in the registry. It must never fabricate data: every cell either comes from a verified API response or renders an explicit "N/A" when a source is unavailable.

Success criteria:
- Five node cards render with online/offline/stale status, role badge, year, and last heartbeat.
- Server host/port, base topic, and MQTT connection state render next to the data-source banner.
- The current round shows round number, selected nodes, phase, registered model version, bytes up/down, and stage timeline; falls back cleanly to the latest completed round from `rounds.csv`.
- Latest and best global model versions appear; transfer size (parameters × 4 bytes / chunk size) is shown when available.
- Connection and aggregation health surfaces: broker connected count, ack counts, checksum ok vs bad.
- No hardcoded values, no untested telemetry. Acceptance tests cover each view independently.

## 2. Repository structure inspected

| Path | What it contains | Relevance |
| --- | --- | --- |
| `dashboard/frontend/src/{main.tsx,App.tsx?}` | App shell mounts the first hash route | Need to add Overview route |
| `dashboard/frontend/src/types.ts` (366 lines, 20 interfaces) | NodeView, RoundView, Stage, ModelRecord, StatusPayload, RoundsPayload, ModelPayload, ComparisonRow, CommEvent, LiveMessage, SocketState | Type contracts for the Overview page |
| `dashboard/frontend/src/hooks/useHashRoute.ts` (34 lines) | Hash-route router | Route wiring target |
| `dashboard/frontend/src/hooks/useLiveFeed.ts` (94 lines) | WebSocket stream of `{type:"hello", mqtt_event", "tick"}` events | Live refresh plumbing |
| `dashboard/frontend/src/lib/api.ts` (55 lines) | Typed fetch helpers against `http://localhost:8010` | Data access |
| `dashboard/frontend/src/lib/format.ts` (107 lines) | `formatNumber`, `formatBytes`, status helpers | Read-side formatting |
| `dashboard/frontend/src/lib/useApi.ts` (57 lines) | Polling hook with retries | Fallback polling |
| `dashboard/frontend/src/components/ui.tsx` (348 lines) | Primitive UI pieces (`Bar`, `StatusBadge`, `Kpi`, etc.) | Reusable building blocks |
| `dashboard/backend/main.py` | All seven REST endpoints + `/ws` handler | Backend contract |
| `dashboard/backend/telemetry.py` | TelemetryStore, TOPIC_CONTRACT, ROUND_STAGE_DEFINITIONS, `status_payload`, `communication_payload` | MQTT → frontend pipeline |
| `dashboard/backend/registry.py` | RegistryReader: rounds.csv, latest.json, best.json, scan_versions | Model registry snapshot |
| `dashboard/backend/mqtt_observer.py` | Paho client, reconnect backoff, queue drainer, `build_observer()` | Live ingestion seam |
| `dashboard/backend/settings.py` | Settings dataclass, `discover_registry()` picks freshest registry by mtime | Configuration |
| `common/config.json` | nodes=node1..node5, training=[node1..node4], inference_only=[node5], base_topic="aq" | Topology source of truth |
| `server/fl_coordinator.py` | Feeds `server/model_registry/*` | Authoritative source for topology |

## 3. Existing architecture reused

- **Backend already delivers the ingredients.** `GET /api/status` returns exactly the fields Overview needs: `nodes`, `current_round`, `latest_model`, `best_model`, `registry`, `broker`, `observer`, `system`. No new backend work is required beyond routing a focused request.
- **Data provenance preserved.** The same `provenance` block (`live` / `historical` / `note`) and `data_source` banner (`live_mqtt` / `registry_only` / `unavailable`) ship unchanged, so Overview inherits them consistently with pages 2–5.
- **Component library intact.** `Kpi`, `StatusBadge`, `Bar`, `EmptyState`, link components exist in `ui.tsx`; the spec reuses at least two of them directly and three more as needed.
- **WebSocket already streams.** The same `/ws` handler pushes `hello` and `mqtt_event` payloads to every tab via `useLiveFeed`; Overview consumes that stream to drop poll-based refreshes.
- **No Fl coordinate / no broker code touched.** The dashboard is already read-only by construction.

## 4. Component hierarchy

```
OverviewPage (hash route "#/overview")
├── ProvenanceBanner        data_source + broker + observer banner
├── TopologyRack             horizontal layout of 5 node cards
│   └── NodeCard[5]          role badge, online/offline/stale dot, year, last health, last message
├── RoundPanel              current round inline + copy to Federated page
│   ├── RoundHeader          round number, phase label, registered version, is_live
│   ├── SelectedNodes        list of tags or nothing
│   ├── PhaseMeter           Bar component from stages list
│   └── StageTimeline        Row of Stage links (complete/active/pending)
├── ModelBoard               latest.json + best.json side by side
│   ├── ModelCard (latest)  version, parameters, weighted_val_loss, has_weights, created_utc, sources
│   └── ModelCard (best)     same fields
└── ConnectionHealthCard    ack counts, checksum ok/bad, observed events count
```

### Existing reusable pieces

| Component | Where used | Why reuse |
| --- | --- | --- |
| `Kpi` | ModelBoard headers | Same parameter / loss readouts the performance page already displays |
| `StatusBadge` | NodeCard status dot | Direct mapping to `NodeView["status"]`; zero new logic |
| `Bar` | PhaseMeter + ConnectionHealthCard progress bars | Already accepts a list of `{value,label}`; also drives nothing else in this page |
| `LinkSettingsLink`, `Anchor` | Any table-row copy | Pre-built navigational helpers for stage rows |
| `EmptyState` | ConnectionHealthCard when no totals | Same pattern used by other empty pages |

### New components written by this design

- `NodeCard` — one per node. Owns status, role, last-seen timestamps, reason. Pulls its payload from `NodeView`.
- `RoundPanel` — owns the current-round representation; delegates stage detail and bytes display to children.
- `ModelBoard` — latest vs best card pair; depends on `ModelRecord`.
- `ConnectionHealthCard` — derived from `ConnectionHealth` shape built from `CommsView`; pulls nothing from telemetry directly.
- `OverviewPage` — top-level layout and the 5-node rack.

## 5. Data flow

```
MQTT broker
  └─ aq/{nodeN}/status, aq/{nodeN}/health
       └─ MQTTObserver (paho loop_start)  →  TelemetryStore.ingest
            └─ _classify() matches TOPIC_CONTRACT
                 └─ node state, round state, global announce, acks, chunks
                      └─ publish_threadsafe to /ws
                           │
Websocket client
  └─ useLiveFeed listens for {"type":"mqtt_event","event":...}
       └─ OverviewPage state updated

REST fallback (in order)
GET /api/status  → StatusPayload
    ├─ nodes[]                ← node cards (live or stale)
    ├─ current_round           ← round panel (live: inferred from MQTT; else registry fallback)
    ├─ latest_model            ← latest card
    ├─ best_model              ← best card
    ├─ registry.round_count    ← metric, display only
    └─ broker/observer         ← data-source banner + health card

GET /api/model  → ModelPayload (transfer metadata only)
GET /api/communication  → CommPayload totals (optional second call)
```

### Provider precedence for each field

| Field | Primary | Fallback | Disambiguation |
| --- | --- | --- | --- |
| Node presence / online-vs-offline | `nodes[].status` from store | List of nodes from `configured_nodes` | Missing status = `unknown` |
| Current round | `current_round` (live or historical fallback) | — | Live shown when `is_live`; stale flag exposed |
| Latest model | `latest_model` | — | None → "No models available" |
| Best model | `best_model` | — | None → "No evaluation recorded" |
| Transfer bytes | `transfer.bytes` (= params × 4) | `model_transfer.bytes` from `/api/model` | `null` handled explicitly |
| Total acks | `current_round.acks` counts | — | Both accepted and rejected rendered |
| Checksum status | `current_round` ack + event list | — | ok / bad tally rendered from `events` or `communication_payload` |
| Broker / base topic | `broker.{host,port,base_topic}` | — | When unavailable → show `unavailable` banner |

## 6. Layout

### Desktop (≥ 1024 px wide)

```
┌────────────────────────────────────────────────────┐
│ PROVENANCE BANNER                                   │
│ live_mqtt · broker 127.0.0.1:1883 · aq/nodeN      │
├────────────────────────────────────────────────────┤
│ NODE TOPOLOGY (5 cards, 10px gap, 120px height)     │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│ │ node1    │ │ node2     │ │ node3    │ ...         │
│ │ online    │ │ online    │ │ offline  │             │
│ │ training  │ │ training  │ │ training │             │
│ │ 2010      │ │ 2011      │ │ 2012     │             │
│ │ last:…   │ │ last:…   │ │ last:…  │             │
│ └──────────┘ └──────────┘ └──────────┘             │
├──────────────────────┬─────────────────────────────┤
│ ROUND PANEL          │ MODEL BOARD                 │
│ round 3 · v0003      │ ┌───────────────────────┐   │
│ selected: node1...   │ │ LATEST v0003          │   │
│ phase: FedAvg aggreg │ │ params: 9025           │   │
│ ████░░░░ 60%         │ │ loss: 0.021           │   │
│ stages complete/     │ │ weights: yes           │   │
│ active/pending       │ │ created: ...           │   │
│   ● client_selection │ │                       │   │
│   ● model_broadcast  │ │ BEST v0001             │   │
│   ● local_training   │ │ params: 9024           │   │
│   ● weight_upload    │ │ loss: 0.018            │   │
│   ● update_validat. │ │                        │   │
│   ● fedavg_aggregation│ └───────────────────────┘   │
│   ● model_register   │                             │
└──────────────────────┴─────────────────────────────┘
│ CONNECTION HEALTH                                     │
│ bytes up 1.2MB · bytes down .4MB · 9 acks · 1 bad    │
└───────────────────────────────────────────────────────┘
```

### Mobile / narrow (< 768 px)

Single column, cards stack vertically, each card shows only `id`, `role`, and a compact status chip (online / offline / stale). Round panel and ModelBoard collapse into compact two-line summaries. The 5-card rack becomes a horizontal scroll or a single sticky row at the top. ConnectionHealthCard stays visible below the fold.

### Tablet (768–1024 px)

Two-column like mobile with cards full width; topology keeps the horizontal row because five short cards fit.

## 7. API contract consumed

Only these four endpoints exist and they are sufficient:

| Endpoint | What Overview reads |
| --- | --- |
| `GET /api/status` | nodes, current_round, latest_model, best_model, registry, broker, observer, config, predictions, system, provenance |
| `GET /api/model` | versions, transfer.{parameters,bytes,chunk_size,chunks,dtype} |
| `GET /api/communication` (optional, 2nd call) | observed totals, acks counts, rejected events, topic contract |
| WS `/ws` | `{"type":"hello","data":{"mqtt_enabled":bool,"broker":{host,port,base_topic}}}` then stream `mqtt_event` |

Endpoints named in `README.md` (`/api/rounds`, `/api/air-quality`) are irrelevant to Overview; no call expected.

Every failure path is caught inside `lib/api.ts` already — test at `tests/test_dashboard_backend.py::test_api_endpoints_and_websocket` and the viewer will degrade to cached HTML gracefully.

## 8. Files this design writes

| File | Role |
| --- | --- |
| `dashboard/frontend/src/pages/OverviewPage.tsx` | Top-level component, routing, page shell |
| `dashboard/frontend/src/components/NodeCard.tsx` | Per-node card rendering |
| `dashboard/frontend/src/components/ModelBoard.tsx` | Latest vs best card pair |
| `dashboard/frontend/src/components/RoundPanel.tsx` | Current round panel incl. stage timeline |
| `dashboard/frontend/src/components/ConnectionHealthCard.tsx` | Connection / aggregation health summary |
| `dashboard/frontend/src/hooks/useOverviewStatus.ts` | Aggregates `/api/status` + WS `mqtt_event` into one state slice |
| `dashboard/frontend/src/pages/FederatedPage.tsx` (minor touch) | Copy stage timeline row to direct URL anchor so Overview can deep-link |
| `docs/superpowers/specs/2026-11-06-airfed-overview-design.md` | This document |
| Tests: `tests/test_dashboard_backend.py` (existing), new `tests/test_overview_frontend.py` | Frontend smoke test using happy-dom |

Files that **do not** change: `main.tsx`, `App.tsx` (if present), `components/ui.tsx`, `hooks/useHashRoute.ts`, `lib/*.ts`, `types.ts`, backend files. `useHashRoute.ts` needs one line added per existing page; Overview gets the first route hash `#/overview`.

## 9. How to keep data honest

- `NodeView["status"]` only ever arrives through `TelemetryStore._node_view` — there is no input path into the frontend that bypasses the ingest state machine.
- `round.model_version`, `round.phase`, `round.registered_version`, `round.selected`, `round.acks` all derive from the same `live_round` object in the store. Historical rounds come from `rounds.csv` parsed once by `RegistryReader`.
- Latest and best come from `latest.json` / `best.json`, each version records maintained by `fl_coordinator._write_model`. Nobody writes to those files from the frontend.
- Base topic comes from `settings.broker.base_topic` rather than being hardcoded in the page.
- Transfer bytes is computed as `parameters * 4` only because the constraint says "do not assume chunk semantics"; a simple parameter-carrying summary is the design decision, and `model_transfer.chunks` tells the display whether chunk math was actually used.

## 10. Unresolved technical questions

1. **`App.tsx` routing.** `main.tsx` imports `./App`; the directory listing confirms no `App.tsx` file exists in `src/pages` yet, so I am assuming the router lives as `src/App.tsx` with a `Routes` tree keyed by hash. If the actual location differs, the route string should change accordingly — this is the one edit allowed outside the listed new files.
2. **Smoke-test browser environment.** `tests/test_overview_frontend.py` requires either happy-dom or jsdom plus a Vite proxy path. The repo currently has no `happy-dom` in `requirements.txt`; I propose adding it alongside `numpy` in `dashboard/requirements.txt`. If you prefer Pytest-driven integration over unit tests, the scope can stay smaller and skip frontend DOM coverage.
3. **`node-year` display format.** Years 2010–2014 are stored in `config.json`; formatting choices (absolute date vs relative offset) are visual preferences, not data concerns — either choice is defensible.
4. **Deep-link into the Federated stage.** Requiring a one-line addition to `FederatedPage` adds coupling to Overview's success path; the design carries the change but it stays optional and behind a stable anchor fragment (`#federated`).

## 11. Approvals

This document proposes a minimal, four-component design anchored entirely to existing REST endpoints and one WebSocket stream. Scope is intentionally bounded: no new backend paths, no MQTT subscription changes, no FL coordinator modification. If the user wants a thicker spec (full responsive matrix, deep-link table rows, per-node detail drilldown), expand this document section by section before implementation.

# AirFed Demo Runbook

This document contains the commands to start and demonstrate the project. It
covers the dashboard-controlled dynamic platform, the legacy five-node
deployment, the offline scorer, and one-command local startup. No test commands
are included.

The **dynamic platform** is the primary workflow:

```text
dashboard            FastAPI + React control plane
dashboard backend    launches broker, control coordinator, simulated workers
workers              self-register with ID, role, shard, samples, heartbeat
coordinator          waits for min workers, freezes selection per round, FedAvg
```

The legacy **five-node topology** remains supported:

```text
node1, node2, node3, node4   training nodes (2010-2013)
node5                        inference-only node (2014)
flserver                     legacy CLI coordinator
dashboard                    observer + control plane
```

Default ports:

| Service | Address |
| --- | --- |
| Mosquitto broker | `127.0.0.1:1883` |
| Dashboard backend | `http://127.0.0.1:8010` |
| Dashboard frontend (dev) | `http://127.0.0.1:5173` |
| Coordinator registry | `server/model_registry/` |

---

## 1. One-time setup

Run these from the project root (`iot/`).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r dashboard/requirements.txt
npm --prefix dashboard/frontend install
```

Mosquitto is expected at `/usr/local/bin/mosquitto`. Check it once:

```bash
mosquitto -h | head -1
```

Build the dashboard once, so the backend can serve the static frontend:

```bash
npm --prefix dashboard/frontend run build
```

---

## 2a. Dashboard against existing results (no training)

Use this when you only want to show the dashboard, the registry, the round
history, and the performance comparison. It does not start training.

### Terminal 1 - dashboard backend

```bash
source .venv/bin/activate
uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8010
```

If `dashboard/frontend/dist` was built in step 1, open:

```text
http://127.0.0.1:8010/
```

The Overview page shows the five nodes, the current/last federated round, the
latest and best global model, and connection health. The data-source banner
reads `registry_only` until a broker is running. The dashboard automatically
picks the freshest registry from `server/model_registry/` or the committed
Stage 4 experiment runs under `.stage4_runs/`.

Useful API checks from another terminal:

```bash
curl -s http://127.0.0.1:8010/api/health
curl -s http://127.0.0.1:8010/api/status
curl -s http://127.0.0.1:8010/api/rounds
curl -s http://127.0.0.1:8010/api/model
curl -s http://127.0.0.1:8010/api/metrics
curl -s 'http://127.0.0.1:8010/api/air-quality?node=node1'
curl -s http://127.0.0.1:8010/api/communication
```

---

## 2. One-command local startup

```bash
./scripts/dev.sh
```

This builds the frontend, checks dependencies/ports, and starts the API at
`http://127.0.0.1:8010`. Use `AIRFED_SKIP_BUILD=1 ./scripts/dev.sh` to reuse an
existing `dashboard/frontend/dist`.

Then open the dashboard and use the controls (no other terminal needed):

1. **Workers** → **Start broker + coordinator**.
2. **Workers** → launch N simulated workers (dummy for a protocol demo, real
   for actual TensorFlow training).
3. **Federated** → configure rounds/min/max workers/selection/deadline and press
   **Start**.

## 2b. Dynamic dashboard-controlled training (primary)

The control coordinator runs as a long-lived MQTT process. The dashboard
publishes session commands on `aq/fl/control`; workers register on
`aq/fl/workers/{id}/register` and heartbeat on `aq/fl/workers/{id}/state`.

### What the dashboard controls

- Session: start, pause, resume, stop.
- Participation: `min_workers`, `max_workers` (blank = all), `all`/`random`
  selection, and joins/leaves between rounds.
- Training: fixed/continuous mode, rounds, local epochs, round deadline,
  learning rate, window hours.
- Aggregation: sample-weighted FedAvg; single-client rounds are explicitly
  marked and never presented as a full cross-client aggregate.
- Workers: launch 1–200 simulated training or inference workers, stop specific
  workers, view logs, and detect crashes.

### Expected behavior

- A worker whose heartbeat expires is shown stale/offline; retained old state
  never implies online.
- Inference-only workers register and appear in the UI but are excluded from
  training and aggregation.
- If fewer than `min_workers` are available, the session waits instead of
  starting a round.
- The participant list is frozen at the start of each round. Late joiners join
  the next round.
- If too few valid updates arrive, aggregation and model registration are shown
  `skipped`; the dashboard does not fabricate a successful round.

### Real (non-dummy) simulation workers

Remove the dummy checkbox in the Workers page or use the API:

```bash
curl -s -X POST http://127.0.0.1:8010/api/workers/launch \
  -H 'Content-Type: application/json' \
  -d '{"count": 2, "role": "training", "simulation": true, "dummy": false}'
```

Real simulation workers partition only the **training portion of training
years** (2010–2013) into contiguous, non-overlapping shards. The 2014 test year
is never used for training. TensorFlow import takes ~45 seconds per worker, so
wait for registration before starting a session.

### API checks

```bash
curl -s http://127.0.0.1:8010/api/session
curl -s http://127.0.0.1:8010/api/workers
curl -s http://127.0.0.1:8010/api/rounds/live
curl -s http://127.0.0.1:8010/api/processes
curl -s 'http://127.0.0.1:8010/api/logs?name=coordinator&lines=80'
```

## 3. Legacy live demo: broker + nodes + coordinator + dashboard

Run each block in its own terminal. Keep the terminals open.

### Terminal 1 - MQTT broker

```bash
mkdir -p /tmp/fedpm25-mosquitto
mosquitto -c docs/mosquitto.conf -v
```

Leave this running. It prints client connects and message traffic.

### Terminal 2 - dashboard backend

```bash
source .venv/bin/activate
uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8010
```

### Terminals 3-6 - four training nodes

Start one node per terminal. TensorFlow import takes roughly 45 seconds on the
current laptop, so wait for `nodeN online` in each terminal before starting the
coordinator. If you start the coordinator first, it waits for
`--startup-wait-sec`.

```bash
source .venv/bin/activate
python -m node.fl_node --node-id node1 --window-hours 24
```

```bash
source .venv/bin/activate
python -m node.fl_node --node-id node2 --window-hours 24
```

```bash
source .venv/bin/activate
python -m node.fl_node --node-id node3 --window-hours 24
```

```bash
source .venv/bin/activate
python -m node.fl_node --node-id node4 --window-hours 24
```

### Terminal 7 - inference-only node (the phone role)

```bash
source .venv/bin/activate
python -m node.fl_node --node-id node5 --inference-only
```

`node5` publishes retained status and never trains or uploads weights.

### Terminal 8 - federated coordinator

Start after the node terminals show `online`. This runs three short rounds,
which is enough for a live demonstration:

```bash
source .venv/bin/activate
python -m server.fl_coordinator \
  --rounds 3 --local-epochs 1 \
  --deadline-sec 180 --min-clients 3 \
  --startup-wait-sec 60 --verbose
```

For the default five rounds and 120-second deadline:

```bash
python -m server.fl_coordinator --verbose
```

The coordinator log should contain, once per round:

```text
online nodes: node1 node2 node3 node4
round N started model=vNNNN ...
ack accepted round=N node=node1 reason=None
...
round N collected 4/4
round=N selected=4 received=4 ... time=... val_loss=... version=vNNNN
```

### Terminal 9 - dashboard frontend (development mode)

Optional if you already built the frontend and are using
`http://127.0.0.1:8010/`. For live reload during the demo:

```bash
npm --prefix dashboard/frontend run dev
```

Open:

```text
http://127.0.0.1:5173/#/overview
```

Vite proxies `/api` and `/ws` to the backend on port 8010.

### What to show on the dashboard

1. **Data-source banner** changes from `registry_only` to `live_mqtt` once the
   broker and coordinator are active.
2. **Node topology** shows whatever training/inference workers are online. The
   legacy nodes appear as training `node1`–`node4` and inference-only `node5`;
   dynamic workers appear alongside them.
3. **Current round** shows the round number, phase, selected nodes, accepted
   acks, bytes up/down, and accurate stage statuses (`complete`, `active`,
   `pending`, `skipped`, `failed`).
4. **Global models** shows the latest registered version and the best
   validation-loss checkpoint.
5. **Workers** page shows registration, shard, samples, heartbeat age, state,
   progress, process logs, and crash records. **Federated** controls the full
   session lifecycle. **Communication** shows checksum verdicts and topic
   contract. **Performance** and **Air Quality** read the existing artifacts.

---

## 4. Score the final model offline

Run after the coordinator finishes, from another terminal:

```bash
source .venv/bin/activate
python -m server.offline_eval --verbose
```

Use the best validation checkpoint instead of the latest registered version:

```bash
python -m server.offline_eval --best --verbose
```

The scorer prints per-node rows for node1-node4, the pooled result, and the
unseen `node5` row.

---

## 5. Optional: regenerate Stage 1 / Stage 4 artifacts

These are long-running and are not required for a live dashboard demo.

Stage 1 baselines (writes `results.csv`, `results_by_seed.csv`,
`results.png`):

```bash
source .venv/bin/activate
python -m baselines.run_all --verbose 0
```

Improved Stage 1 variant:

```bash
python -m baselines.improved --local-windows 12,24 --verbose 0
```

Fair four-node Stage 4 comparison (private loopback broker):

```bash
python -m experiments.stage4_experiment --mode baselines \
  --seeds 42,43,44 --rounds 15 --local-epochs 1

python -m experiments.stage4_experiment --mode federated \
  --seeds 42,43,44 --rounds 15 --local-epochs 1 \
  --deadline-sec 240 --startup-timeout 600
```

---

## 6. Stop everything

In each node, coordinator, dashboard, and broker terminal, press `Ctrl-C`.
The nodes publish a retained graceful-offline status and the coordinator stops
cleanly.

If a background process is left behind, check the listening ports:

```bash
lsof -nP -iTCP:1883 -sTCP:LISTEN
lsof -nP -iTCP:8010 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

---

## 7. Troubleshooting

**Dashboard shows `registry_only` and nodes are `unknown`**

The broker is not running, or the dashboard started before it. Start
`mosquitto`, then reload the page; the observer reconnects automatically.

**Coordinator says fewer than `min_clients` online**

Wait for all four training nodes to print `online`, or restart the coordinator
with a longer `--startup-wait-sec`. `node5` is inference-only and never counts
as a training client.

**Frontend cannot reach the API**

Start the backend on port 8010 first. When using `npm run dev`, the Vite proxy
targets `http://127.0.0.1:8010`. Override it with `AIRFED_API` if needed:

```bash
AIRFED_API=http://127.0.0.1:8010 npm --prefix dashboard/frontend run dev
```

**A live round exists but the dashboard is stale**

The dashboard marks telemetry stale after 30 seconds and rounds stale after
120 seconds. Check that the broker log is still receiving messages.

**Regenerate the shared scaler**

Only needed after changing the dataset or split settings:

```bash
source .venv/bin/activate
python -m common.preprocess --build-config
```

**Port already in use**

Stop the old process:

```bash
lsof -nP -iTCP:8010 -sTCP:LISTEN
kill <pid>
```

Repeat with ports `1883` and `5173` as needed.

# Federated PM2.5 Forecasting on IoT Nodes

College IoT project. **Stages 1, 2, 3, and 4 are implemented**, plus the
pre-Stage-3 improved model variant:

- **Stage 1:** real-data inspection, shared preprocessing, CNN-RNN model,
  centralized / local-only / persistence / PM2.5-only baselines, 3-seed
  evaluation, MQTT chunking helpers.
- **Stage 2:** Mosquitto broker config, MQTT node hello-world with retained
  online status, retained LWT offline status, health heartbeats, and a small
  server-side status/health observer.
- **Stage 3:** chunked model-weight exchange over MQTT. Float32 weights are
  sent as 16 KiB sequenced chunks with per-chunk and whole-payload SHA-256,
  JSON metadata (`schema_version`, `node_id`, `ts`), out-of-order/duplicate/
  corrupted/missing handling, server acknowledgements, `.npy` + JSON receipts,
  a prediction-preservation check, and a retained global-model announce.
- **Stage 4:** FedAvg over MQTT for four training nodes plus one inference-only
  node. The server runs a dependency DAG per round, validates every update,
  averages by `n_samples`, keeps a versioned model registry, and tracks the
  best evaluated checkpoint by weighted validation loss. Nodes are long-lived
  and evaluate each incoming global model on their own validation split; final
  test metrics come from a separate offline scorer.
- **Pre-Stage 3:** delta-target improved CNN-RNN (12 h / 24 h windows, no
  pooling, hour sin/cos), a 6-hour-ahead comparison, a commented LAN broker
  profile, and a two-node retained-status/LWT integration test.

Dataset replay, prediction publishing, the dashboard, and phone/Termux
inference are later stages. The live federated topology is **four training
nodes (`node1`–`node4`) plus one inference-only node (`node5`, the phone)**.
The phone does not train, does not upload weights, and its code must not import
TensorFlow; it may only publish status, health, and predictions. The server
enforces this through `federated.training_nodes` and
`federated.inference_only_nodes` in `common/config.json`. The Stage 1 baselines
still use all five data years; the Stage 4 comparison uses node1-node4 and
scores node5 separately as unseen data.

Project root: the `iot/` directory containing this README.

## Stage 1 status

- Dataset copied to `data/beijing_pm25.csv` from
  `data/PRSA_data_2010.1.1-2014.12.31.csv`; the original is untouched.
  The two files are SHA-256 identical.
- Real data verified with pandas: **43,824 rows**, 13 columns, years
  **2010-2014**, **2,067 missing `pm2.5` values**.
- `common/` implements config loading, preprocessing, the Keras model,
  weight flatten/unflatten, chunking with SHA-256, and MQTT helpers.
- `baselines/` implements four real-data baselines:
  **persistence**, **centralized**, **local-only**, and the
  **PM2.5-only ablation**, all over seeds **42, 43, 44**.
- `baselines/improved.py` adds the improved variant: **delta target**
  (`y[t+h] - pm25[t]`), **12 h and 24 h windows**, **no pooling**
  (`pool_size=1`), and **hour-of-day sin/cos** inputs, still over the same
  seeds. It also reports a **6-hour-ahead** horizon against persistence.
- `results.csv` reports mean ± std for both **raw unclipped** test targets and
  **clipped** test targets. The **headline is raw unclipped**.
- Federated results are **not** present yet; they will be added later.

## Data report

```text
shape: (43824, 13)
columns: No, year, month, day, hour, pm2.5, DEWP, TEMP, PRES, cbwd, Iws, Is, Ir
pm2.5 dtypes: float64 after pandas NA handling
pm2.5 NA: 2067
year range: 2010-2014
```

First five rows:

```text
 No  year  month  day  hour  pm2.5  DEWP  TEMP   PRES cbwd   Iws  Is  Ir
  1  2010      1    1     0    NaN   -21 -11.0 1021.0   NW  1.79   0   0
  2  2010      1    1     1    NaN   -21 -12.0 1020.0   NW  4.92   0   0
  3  2010      1    1     2    NaN   -21 -11.0 1019.0   NW  6.71   0   0
  4  2010      1    1     3    NaN   -21 -14.0 1019.0   NW  9.84   0   0
  5  2010      1    1     4    NaN   -20 -12.0 1018.0   NW 12.97   0   0
```

Relative humidity is derived from `TEMP` and `DEWP` with the Magnus formula.
The three model inputs are `[pm25, temp, rh]`.

## Setup (laptop only)

The project requires **Python 3.10+** and **paho-mqtt 2.x**. TensorFlow is
**not** installed or required on Termux. Stages 1 and 3 training/weight-building
run on the laptop; Termux code must stay inference-only and must not import
TensorFlow. Use a laptop Python 3.12 environment for Stage 1 and the demos.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Always use the project virtual environment (`source .venv/bin/activate`); do
not install packages globally.

Build the shared scaler in `common/config.json` once (and again after changing
the dataset or split settings):

```bash
python -m common.preprocess --build-config
```

Real output on this dataset:

```text
wrote /Users/apple/Documents/4thyear/iot/common/config.json
trained rows: 35059
pm25 clip (p99.5): 463.710000
pm25: min=0.000000 max=463.710000
temp: min=-19.000000 max=42.000000
rh: min=2.688797 max=100.000000
```

## Run the Stage 1 baselines

```bash
python -m baselines.run_all --verbose 0
```

This runs seeds `42,43,44` by default, writes `results.csv`,
`results_by_seed.csv`, `results.png`, and `baselines/local_only_per_node.csv`.
Useful variants:

```bash
python -m baselines.run_all --seeds 42 --epochs 1 --verbose 0   # smoke test; overwrites results
python -m baselines.run_all --skip-local --verbose 0            # skip slow local-only
python -m baselines.centralized --verbose 2                     # single method, no CSV write
python -m baselines.persistence
python -m baselines.pm25_only --verbose 2
python -m baselines.local_only --verbose 0
```

Run the improved variant suite (12 h and 24 h, local-only, and 6 h horizon).
It upserts its rows into `results.csv` and regenerates `results.png`:

```bash
python -m baselines.improved --local-windows 12,24 --verbose 0
```

Smoke-test the improved plumbing without overwriting the reported results:

```bash
python -m baselines.improved --seeds 42 --windows 12 --skip-local --skip-horizon \
  --epochs 1 --verbose 0 --no-write
```

## Stage 1 results

Seeds: `42, 43, 44`. Values are **mean ± standard deviation over seeds**.
Raw targets are filled/interpolated but **not** clipped. Clipped targets are
capped at the training p99.5 value, **463.71**. The **raw unclipped result is the
headline** because it reflects the actual test-hour PM2.5 distribution,
including extreme values; the clipped result is the secondary,
training-aligned view.

### Headline: raw unclipped test targets

```text
method        RMSE              MAE               R2
centralized   25.626 ± 0.078    14.986 ± 0.243    0.9416 ± 0.0004
local_only    28.495 ± 0.238    17.179 ± 0.489    0.9278 ± 0.0012
pm25_only     27.374 ± 0.316    16.392 ± 0.774    0.9333 ± 0.0015
persistence   24.938 ± 0.000    13.634 ± 0.000    0.9447 ± 0.0000
```

### Secondary: clipped test targets

```text
method        RMSE              MAE               R2
centralized   24.766 ± 0.049    14.689 ± 0.243    0.9443 ± 0.0002
local_only    27.430 ± 0.271    16.882 ± 0.489    0.9316 ± 0.0013
pm25_only     26.510 ± 0.226    16.096 ± 0.773    0.9361 ± 0.0011
persistence   25.272 ± 0.000    13.760 ± 0.000    0.9420 ± 0.0000
```

**Interpretation, stated plainly:** persistence (next hour = current hour) wins
on every **raw headline** metric. Centralized is close but does not beat it on the
headline. On the secondary clipped view, centralized edges persistence on RMSE
and R2, while persistence still has the lower MAE. The PM2.5-only ablation is
worse than centralized, so temperature and humidity do add signal. Local-only is
the weakest, which is the expected motivation for federation. The current
CNN-RNN does **not** demonstrate clear skill over persistence yet; this is not
hidden and is listed in the known issues.

Per-node local-only results are in `baselines/local_only_per_node.csv`.

## Improved variant results (pre-Stage 3)

The paper-faithful model above does **not** beat persistence. The improved
variant changes four things while keeping the same 3-seed protocol:

- **Delta target:** the model predicts the scaled change
  `y[t+h] - pm25[t]`, and the last observed hour is added back before inverse
  Min-Max scaling. This makes the model start near persistence and learn a
  correction instead of re-learning the current value.
- **Longer window:** 12 h and 24 h instead of 3 h.
- **No effective pooling:** `MaxPooling1D(pool_size=1)` is an identity pool,
  so the RNN sees every hour instead of one pooled timestep.
- **Hour-of-day features:** `sin(2*pi*hour/24)` and `cos(2*pi*hour/24)`
  appended after the three scaled sensor features.

These numbers come from
`python -m baselines.improved --local-windows 12,24 --verbose 0` on the real
Beijing data, seeds `42, 43, 44`. Headline raw unclipped targets:

```text
method                       RMSE              MAE               R2
persistence_w12              24.938 ± 0.000    13.634 ± 0.000    0.9447 ± 0.0000
centralized_improved_w12     23.912 ± 0.444    13.596 ± 0.594    0.9491 ± 0.0019
centralized_improved_w24     23.726 ± 0.283    13.557 ± 0.547    0.9499 ± 0.0012
local_only_improved_w12      24.971 ± 0.190    14.823 ± 0.210    0.9445 ± 0.0008
local_only_improved_w24      25.576 ± 0.874    15.333 ± 1.089    0.9418 ± 0.0040
```

Secondary clipped targets:

```text
method                       RMSE              MAE               R2
centralized_improved_w12     23.293 ± 0.422    13.307 ± 0.587    0.9507 ± 0.0018
centralized_improved_w24     23.084 ± 0.253    13.273 ± 0.540    0.9516 ± 0.0011
local_only_improved_w12      24.288 ± 0.153    14.534 ± 0.213    0.9464 ± 0.0007
local_only_improved_w24      24.841 ± 0.790    15.040 ± 1.086    0.9439 ± 0.0036
persistence_w12              25.272 ± 0.000    13.760 ± 0.000    0.9420 ± 0.0000
```

Six-hour-ahead horizon (raw unclipped), same first-80%/last-20% split:

```text
method                       RMSE              MAE               R2
centralized_improved_w12_h6  67.041 ± 2.071    44.319 ± 1.317    0.5999 ± 0.0249
persistence_w12_h6           77.418 ± 0.000    47.376 ± 0.000    0.4668 ± 0.0000
```

**Interpretation, stated plainly:** the 24 h improved variant beats
persistence on all three raw headline metrics (RMSE 23.726 vs 24.938, MAE
13.557 vs 13.634, R2 0.9499 vs 0.9447) and does so with lower seed variance
than the 12 h variant. At 6 hours it is clearly better than persistence (RMSE
67.04 vs 77.42, R2 0.600 vs 0.467). The improved **local-only** models clearly
beat the old local-only model (28.495) but are still worse than persistence on RMSE
(24.971 for 12 h, 25.576 for 24 h, vs 24.938). The 12 h local-only model is
better than the 24 h one, while the centralized 24 h model is the best overall.
That gap between local-only and centralized is exactly what federated averaging
is meant to close. These are single-dataset Beijing results, not a general
claim.

## Model size and federated update size

The CNN-RNN has **8,769 trainable parameters**. At float32:

```text
8,769 parameters × 4 bytes = 35,076 bytes ≈ 34.25 KiB ≈ 35 KB
```

A full raw float32 weight update is therefore about **35 KB per node per round**.
With 16 KiB chunks (`chunk_size=16384`), that is 3 chunks:
`16,384 + 16,384 + 2,308` bytes. MQTT/JSON/base64/chunk-header overhead is
additional and is not included in the 35 KB figure. The PM2.5-only ablation has
**8,513 parameters ≈ 34 KB** raw.

The improved variant has **9,025 trainable parameters** (five inputs, same
Conv1D/RNN/Dense widths). At float32:

```text
9,025 parameters × 4 bytes = 36,100 bytes ≈ 35.25 KiB ≈ 36.1 KB
```

That is still **3 chunks** at 16 KiB: `16,384 + 16,384 + 3,332` bytes. The 12 h
and 24 h variants have identical parameter counts and identical update size;
only the input window length changes. This keeps a federated update in the
"few chunks" range required for MQTT.

## Stage 2: MQTT hello-world

### Broker

`docs/mosquitto.conf` has three profiles:

- **Profile A (default, development):** `listener 1883 127.0.0.1`,
  `allow_anonymous true`. Open to processes on this laptop only. Persistence
  lives at `/tmp/fedpm25-mosquitto/`.
- **Profile B (LAN, commented out):** `listener 1883 0.0.0.0`,
  `allow_anonymous false`, `password_file`, `acl_file`. Enable it when phones
  or virtual nodes connect over Wi-Fi. Keep Profile A for day-to-day dev.
- **Profile C (LAN demo only, commented out):** `listener 1883 0.0.0.0`,
  `allow_anonymous true`, **no ACL**. This is for a private hotspot or a
  trusted Wi-Fi network during a classroom demo. Every device on that network
  can read and forge federated traffic; never use it on public Wi-Fi or the
  internet.

Run the default profile from the project root:

```bash
mkdir -p /tmp/fedpm25-mosquitto
mosquitto -c docs/mosquitto.conf -v
```

To enable the LAN profile, comment out Profile A's `listener` and
`allow_anonymous` lines, uncomment Profile B, then create credentials:

```bash
mkdir -p /tmp/fedpm25-mosquitto
mosquitto_passwd -c -b /tmp/fedpm25-mosquitto/passwd flserver '<server-password>'
mosquitto_passwd -b /tmp/fedpm25-mosquitto/passwd node1 '<node1-password>'
mosquitto_passwd -b /tmp/fedpm25-mosquitto/passwd node2 '<node2-password>'
mosquitto_passwd -b /tmp/fedpm25-mosquitto/passwd node3 '<node3-password>'
mosquitto_passwd -b /tmp/fedpm25-mosquitto/passwd node4 '<node4-password>'
mosquitto_passwd -b /tmp/fedpm25-mosquitto/passwd node5 '<node5-password>'
chmod 600 /tmp/fedpm25-mosquitto/passwd
```

The exact ACL is committed as `docs/acl.example`. Each training node may
publish under its own `aq/<node_id>/#` and its own Stage 3 update subtree
`aq/fl/round/+/update/<node_id>/#`, and read `aq/fl/#`; the server may
read/write everything. The inference-only node has no weight-write permission:

```bash
cp docs/acl.example /tmp/fedpm25-mosquitto/acl
chmod 600 /tmp/fedpm25-mosquitto/acl
```

Then point clients at the laptop's LAN IP:

```bash
ipconfig getifaddr en0
python -m node.node_client --node-id node1 --host 192.168.1.50 --verbose
```

**Stage 3 ACL is already included:** each node publishes its update on
`aq/fl/round/{r}/update/{node}/...`, outside `aq/<node_id>/#`. The committed
`docs/acl.example` therefore gives every node both its own tree and its own
update subtree:

```text
topic write aq/node1/#
topic write aq/fl/round/+/update/node1/#
topic read aq/fl/#
```

`topic read aq/fl/#` covers the round ack and the retained global announce.
The `cmd` and `alerts` read lines stay commented until those stages land. The
server already has `topic readwrite #`, so it needs no extra line.

To use **Profile C** for a demo, comment out Profile A's two lines, uncomment
the Profile C block in `docs/mosquitto.conf`, and point every client at the
laptop's LAN IP:

```bash
ipconfig getifaddr en0
mosquitto -c docs/mosquitto.conf -v
python -m node.weight_sender --node-id node1 --host 192.168.1.50 --wait-ack
```

On this machine `mosquitto`, `mosquitto_pub`, and `mosquitto_sub` are installed
at `/usr/local/bin`. **`mosquitto_passwd` is not installed** (the source build
did not install it), so the LAN commands above need it built/installed from the
Mosquitto source tree first. The default anonymous loopback profile does not
need it.

### Server status observer

In terminal 2, subscribe to every node's status and health topics:

```bash
python -m server.fl_server --verbose
```

Expected initial line:

```text
status node1: online at 2026-11-04T07:28:25.483Z
health node1: backend=none uptime=0.0s at 2026-11-04T07:28:25.483Z
```

### Node hello-world

In terminal 3:

```bash
python -m node.node_client --node-id node1 --interval 2 --keepalive 5 --verbose
```

The node publishes:

- retained `aq/node1/status` = `online`
- non-retained `aq/node1/health` every 2 seconds
- retained `aq/node1/status` = `offline, reason=lwt` if the process dies
- retained `aq/node1/status` = `offline, reason=graceful` on Ctrl+C/SIGTERM

Inspect retained status from terminal 4:

```bash
mosquitto_sub -h 127.0.0.1 -t 'aq/+/status' -v
```

### LWT test

Run the node with a short keepalive, then kill it with `SIGKILL`:

```bash
python -m node.node_client --node-id node1 --interval 2 --keepalive 3 --verbose
# in another terminal:
kill -9 <node_pid>
```

After roughly `1.5 × keepalive` seconds the broker publishes the retained LWT:

```text
status node1: offline reason=lwt at 2026-11-04T07:28:25.479Z
```

The LWT payload's `ts` is set when the node connects, so it is the connection
time, not the exact process-death time. Use the server's receive time if you
need the event time.

Stage 2 verified online retained status, retained LWT offline, and graceful
offline on this machine. Health fields are `null` in Stage 2 because no sensor
backend exists yet; no fake readings are published.

### Two-node independence test

`tests/test_two_nodes_integration.py` starts a throwaway Mosquitto broker on a
free localhost port, runs the real `node.node_client` as `node1` and `node2`,
`SIGKILL`s node1, and asserts that node1's retained status becomes
`offline reason=lwt` while node2 remains `online`. It then `SIGKILL`s node2 and
asserts both retained statuses are independently `offline reason=lwt`. It skips
automatically if `mosquitto` is not installed.

```bash
python -m pytest -q tests/test_two_nodes_integration.py -s
```

Real output on this machine:

```text
1 passed in 8.64s
```

### Topic contract

```text
aq/<node_id>/status                     retained; online/offline; LWT uses offline
aq/<node_id>/health                     QoS 1; heartbeat; not retained
aq/<node_id>/prediction                 inference-only node output (later stage)
aq/<node_id>/cmd                        reserved for set_interval/ring/force_sync
aq/alerts/<zone>                        reserved for retained AQI alerts
aq/fl/global/announce                   retained; global model metadata (flserver)
aq/fl/global/chunk/<i>                  QoS 1; global model chunk i; not retained
aq/fl/round/<r>/update/<node>/meta      QoS 1; round update metadata
aq/fl/round/<r>/update/<node>/chunk/<i> QoS 1; round update chunk i
aq/fl/round/<r>/ack/<node>              QoS 1; server acknowledgement
aq/server/...                           reserved for server commands/rounds
```

## Stage 3: chunked weight exchange over MQTT

### What was built

Stage 3 sends one float32 weight vector from a node to the server (or from the
server to the fleet) over MQTT. It is deliberately **transport-agnostic** at the
core: `common/weight_transfer.py` owns the envelope, validation, chunking, and
receiver state machine; `node/weight_sender.py` and `server/weight_receiver.py`
are paho-mqtt CLI adapters. The sender also offers an optional
`--train-epochs` plumbing path for the real-weight demo. The same core is used
by the unit tests.

Each transfer is:

1. **Metadata** (`update_meta` for a round, `announce` for the global model)
   with `schema_version`, `node_id`, `ts` (UTC ISO-8601), `model_version`,
   whole-payload `sha256`, `size`, `chunks`, `chunk_size`, `dtype`, `count`,
   `kind`, the model architecture needed to rebuild it, and an optional
   prediction fingerprint.
2. **Sequenced chunks** (`chunk`) with `index`, `chunks`, `size`,
   `chunk_sha256`, and base64 `data`. Default size is **16 KiB**, so the
   improved 9,025-parameter model is **36,100 bytes → 3 chunks**.
3. **A server ack** for round updates with `status` (`accepted`/`rejected`),
   `reason`, `missing`, and `predictions_match`.

Every JSON object carries `schema_version`, `node_id`, and `ts`, and all
messages use QoS 1. Global mode uses `node_id=flserver`; update acks also use
`node_id=flserver` with `target_node` set to the sender.

### Privacy contract

Only model weights, checksums, model metadata, and prediction fingerprints
leave a node. **Raw PM2.5, temperature, and humidity readings never enter the
Stage 3 payloads.** The receiver accepts weight uploads only from
`federated.training_nodes`. An inference-only node or unknown node ID gets an
explicit `rejected` ack and is never saved, so the phone cannot impersonate a
training node.

### Run the demos

Start the broker in terminal 1:

```bash
mkdir -p /tmp/fedpm25-mosquitto
mosquitto -c docs/mosquitto.conf -v
```

Start the receiver in terminal 2. **It must be running before the sender**:
chunks are not retained, so a late receiver misses them (the global announce is
the only retained Stage 3 message).

```bash
source .venv/bin/activate
python -m server.weight_receiver --mode update --verbose
```

Run the dummy-array plumbing test in terminal 3 (no TensorFlow, so this is the
fast path):

```bash
python -m node.weight_sender --node-id node1 --round 1 --dummy --wait-ack --verbose
```

Real output on this machine (sender):

```text
publishing mode=update node_id=node1 round=1 model_version=dummy-v1 kind=dummy size=36100 chunks=3 chunk_size=16384 sha256=fd8be11577cd2473e7b8931811465eb10c69bcf16cb178682c6c0757ef3663a1
all chunks published
ack accepted sha256=fd8be11577cd2473e7b8931811465eb10c69bcf16cb178682c6c0757ef3663a1 chunks_received=3 predictions_match=None
```

Receiver:

```text
subscribed aq/fl/round/+/update/+/meta, aq/fl/round/+/update/+/chunk/+
metadata round=1 node=node1 model_version=dummy-v1 size=36100 chunks=3 sha256=fd8be11577cd2473e7b8931811465eb10c69bcf16cb178682c6c0757ef3663a1
accepted round=1 node=node1 model_version=dummy-v1 size=36100 chunks=3 sha256=fd8be11577cd2473e7b8931811465eb10c69bcf16cb178682c6c0757ef3663a1 predictions_match=None saved=/private/tmp/fedpm25-demo/registry/round_1_node1.npy
ack accepted round=1 node=node1 reason=None
```

#### Real improved 24 h Keras weights

The default real mode builds the improved 24 h architecture with the configured
seed. This transfers real Keras weights and checks that the receiver's
predictions are unchanged:

```bash
python -m node.weight_sender --node-id node1 --round 1 --wait-ack --verbose
```

Sender and receiver output:

```text
publishing mode=update node_id=node1 round=1 model_version=improved_w24_seed42 kind=model size=36100 chunks=3 chunk_size=16384 sha256=3c6295097c4b7fbdd59aeaf6460fc7b98111b67fb555f723cf3222496319994b
all chunks published
ack accepted sha256=3c6295097c4b7fbdd59aeaf6460fc7b98111b67fb555f723cf3222496319994b chunks_received=3 predictions_match=True

prediction check sample_match=True digest_match=True
accepted round=1 node=node1 model_version=improved_w24_seed42 size=36100 chunks=3 sha256=3c6295097c4b7fbdd59aeaf6460fc7b98111b67fb555f723cf3222496319994b predictions_match=True saved=/private/tmp/fedpm25-demo-real/registry/round_1_node1.npy
```

Train one epoch on the node's own windows before sending (this is a plumbing
check, not a claimed federated result):

```bash
python -m node.weight_sender --node-id node1 --round 1 --train-epochs 1 --wait-ack --verbose
```

```text
trained node1 for 1 epoch(s) on 6286 windows
publishing mode=update node_id=node1 round=1 model_version=improved_w24_seed42 kind=model size=36100 chunks=3 chunk_size=16384 sha256=ddf7d91f5784bb9e8aac4ffa77d28bbc00e9b29837bafb6345ffe0ec21d05ce1
all chunks published
ack accepted sha256=ddf7d91f5784bb9e8aac4ffa77d28bbc00e9b29837bafb6345ffe0ec21d05ce1 chunks_received=3 predictions_match=True
```

#### Global model announce

Global mode publishes a retained announce plus non-retained chunks under
`aq/fl/global/...`. There is no ack in this direction. Start the receiver in
global mode before the sender:

```bash
python -m server.weight_receiver --mode global --verbose
python -m node.weight_sender --mode global --verbose
```

```text
publishing mode=global node_id=flserver round=- model_version=improved_w24_seed42 kind=model size=36100 chunks=3 chunk_size=16384 sha256=3c6295097c4b7fbdd59aeaf6460fc7b98111b67fb555f723cf3222496319994b
all chunks published

metadata round=None node=flserver model_version=improved_w24_seed42 size=36100 chunks=3 sha256=3c6295097c4b7fbdd59aeaf6460fc7b98111b67fb555f723cf3222496319994b
prediction check sample_match=True digest_match=True
accepted round=None node=flserver model_version=improved_w24_seed42 size=36100 chunks=3 sha256=3c6295097c4b7fbdd59aeaf6460fc7b98111b67fb555f723cf3222496319994b predictions_match=True saved=/private/tmp/fedpm25-demo-global2/registry/global_improved_w24_seed42.npy
```

The retained announce is the only Stage 3 message a late subscriber receives:

```json
{"schema_version":1,"node_id":"flserver","ts":"2026-11-05T09:51:12.386Z","message_type":"announce","model_version":"improved_w24_seed42","sha256":"3c6295097c4b7fbdd59aeaf6460fc7b98111b67fb555f723cf3222496319994b","size":36100,"chunks":3,...}
```

### Failure handling demos

Both hooks are test-only flags on the sender. Corrupt one chunk **after** its
SHA-256 is computed, so the receiver sees a real checksum mismatch:

```bash
python -m node.weight_sender --node-id node1 --round 1 --dummy --wait-ack --corrupt-chunk 1
```

```text
ack rejected reason=chunk checksum mismatch at index 1: expected e5b53a268d169bf0e0fd1a432d0c897d9b77aa7936e13e1278788029879f626c, got 468da76698bd4d12aa850ae1cfbb88dbb5a1996185071258e838e85e1ebc3dd0 missing=[1, 2]
```

Drop a chunk and let the receiver's missing timeout fire:

```bash
python -m node.weight_sender --node-id node1 --round 1 --dummy --wait-ack --drop-chunk 1
```

```text
ack rejected reason=missing chunks: [1] missing=[1]
```

Both rejections exit **2**, send a `rejected` ack, and save nothing. The
receiver also rejects:

- a conflicting duplicate chunk (an identical QoS 1 duplicate is tolerated),
- a chunk whose topic index disagrees with its payload index,
- a chunk count / size / dtype inconsistency in metadata,
- an update from an unknown node or from the inference-only node, with an
  explicit `rejected` ack,
- a whole-payload SHA-256 mismatch at `finalize`,
- a rebuilt model whose probe predictions differ from the metadata fingerprint.

### Receiver state machine

`WeightReceiver` accepts chunks **out of order** and keeps one in-flight
transfer per `(round, node)` (or one global transfer). It records identical
duplicates as `duplicates_ignored`, marks the transfer failed on any
conflicting or malformed chunk, and `finalize()` joins the payload, checks the
whole-transfer SHA-256, and decodes float32. For `kind="model"` the receiver
rebuilds the same Keras architecture, loads the received weights, runs a
deterministic synthetic probe, and compares the first eight predictions plus
their SHA-256. That proves the weights survived the round trip; it is not a
test-set accuracy evaluation.

Accepted transfers are written as `<stem>.npy` (no pickle) plus a JSON receipt
containing metadata, chunk counts, duplicate count, prediction result, and a
UTC timestamp. Default location is `server/model_registry/`; override with
`--out-dir`.

### Stage 3 files

- `common/weight_transfer.py` — pure transfer seam: metadata, chunk messages,
  SHA-256, topic builders/parsers, `WeightReceiver`, ack builder, prediction
  fingerprint, dummy weights.
- `node/weight_sender.py` — CLI sender for update and global modes; dummy,
  seeded real, and one-epoch trained weights; ack wait; corrupt/drop test hooks.
- `server/weight_receiver.py` — CLI receiver for update and global modes;
  validation, reassembly, prediction check, `.npy`/JSON save, ack.
- `tests/test_weight_transfer.py` — 18 unit tests, including a real improved
  24 h Keras round trip with unchanged predictions.
- `tests/test_weight_transfer_mqtt.py` — 4 real-broker integration tests:
  accepted round trip, corrupted chunk rejected, missing chunk rejected, and an
  inference-only node update rejected with an ack.
- `tests/broker_utils.py` — shared throwaway-Mosquitto helpers, also used by
  the Stage 2 two-node test.

## Stage 4: FedAvg over MQTT

### What was built

| File | Role |
| --- | --- |
| `common/federated.py` | Pure rules: weighted `fedavg`, weighted validation loss, version names, update metadata/weight validation. No MQTT or TensorFlow. |
| `common/model_delivery.py` | Retained global-model publisher and version-aware late-joiner receiver. |
| `server/dag_runner.py` | Generic task DAG: dependency order, retries, per-task timeouts, failure propagation, cycle detection. |
| `server/fl_coordinator.py` | Server round DAG, online detection, update collection, ack/reject, FedAvg, versioned registry, `rounds.csv`. |
| `node/fl_node.py` | Long-lived node: imports TensorFlow once, waits for invitations, evaluates, trains, uploads, repeats. |
| `server/offline_eval.py` | Separate final scorer over each node's last-20% test slice. |
| `experiments/stage4_experiment.py` | Fair four-node baselines, federated seeds, offline scoring, `results.csv`/`results.png`/`stage4_summary.json`. |
| `common/broker.py` | Throwaway loopback Mosquitto helper shared by tests and the experiment. |

The server round DAG is:

```text
check_online_nodes -> select_clients -> broadcast_global_model
-> wait_for_updates -> validate_updates -> fedavg_aggregate
-> register_model -> announce
```

The node DAG is `receive_model -> evaluate -> local_train -> upload`.

### Round contract

- A round starts only when at least `federated.min_clients` training nodes are
  online (default 3 of 4). Online state comes from retained `aq/<node>/status`
  plus the server's receive time; offline or slow nodes are dropped and the
  round continues.
- The server publishes the current global model, then
  `aq/fl/round/{r}/start` with round id, `model_version`, `local_epochs`,
  `learning_rate`, selected nodes, `min_clients`, and `deadline_ts`.
- Nodes train locally and upload chunks under
  `aq/fl/round/{r}/update/{node}/...`. Each update carries `round`, `node_id`,
  `n_samples`, `n_val`, `val_loss`, chunk count, and SHA-256 checksums.
- The server rejects an update with an explicit ack when the sender is
  inference-only or not a training node, the round id is wrong, the checksum
  does not match, weights contain NaN/Infinity, the weight count differs from
  the global model, or the norm is abnormal. Accepted updates are acknowledged
  immediately.
- `fedavg` weights each node by its `n_samples`. The aggregated model is
  registered as `v{r:04d}`; `latest.json` follows the newest version.
- Nodes evaluate the model they **received** (version `v{r-1}`), not the model
  produced by the round. The server attributes `weighted_val_loss` to that
  evaluated version, updates its registry record, and moves `best.json` only
  when a finite validation loss is lower.
- Every round appends one row and one summary line to
  `server/model_registry/rounds.csv`:
  `round, selected, received, dropped_nodes, bytes_up, bytes_down,
  round_time_sec, weighted_val_loss, evaluated_version, model_version`.

No payload contains raw readings. The server never holds raw node data; it only
receives weights and scalar validation summaries.

### Late joiners

The chosen mechanism is **retained chunks carrying `model_version`** plus a
retained announce. Mosquitto retains the latest message on each global-model
chunk topic, so a node that starts after the model was published still receives
every chunk. `GlobalModelReceiver` buffers chunks that arrive before the
announce, assembles only the announced version, and ignores chunks from stale
versions. This avoids any server-side subscriber handshake and survives a
broker restart or a late inference-only node. Tested by
`tests/test_model_delivery.py` (including a real broker and a late subscriber).

### Run the live topology

Terminal 1 — broker (Profile A, loopback):

```bash
mkdir -p /tmp/fedpm25-mosquitto
mosquitto -c docs/mosquitto.conf -v
```

Terminals 2–6 — the four training nodes and the inference-only node. Start the
nodes first so their retained status is available, or give the server a startup
wait:

```bash
source .venv/bin/activate
python -m node.fl_node --node-id node1
python -m node.fl_node --node-id node2
python -m node.fl_node --node-id node3
python -m node.fl_node --node-id node4
python -m node.fl_node --node-id node5 --inference-only
```

Terminal 7 — server:

```bash
source .venv/bin/activate
python -m server.fl_coordinator \
  --rounds 5 --local-epochs 1 --deadline-sec 120 \
  --min-clients 3 --startup-wait-sec 120
```

Host and port come from `common/config.json` or `--host`/`--port`; nothing is
hardcoded. Stop the nodes and server with Ctrl-C; both disconnect cleanly.

Score the final registered model offline:

```bash
python -m server.offline_eval --verbose          # latest.json (recommended)
python -m server.offline_eval --best --verbose   # best validation checkpoint
```

The default is `latest.json`, because the final round's model has seen every
aggregation but has not itself been evaluated. `--best` loads `best.json`, the
evaluated version with the lowest weighted validation loss.

### Reproduce the fair comparison

```bash
# Fair four-node baselines: 15 epochs for compute parity with 15 local epochs
python -m experiments.stage4_experiment --mode baselines \
  --seeds 42,43,44 --rounds 15 --local-epochs 1

# Federated: private loopback broker, 15 rounds, seeds 42/43/44
python -m experiments.stage4_experiment --mode federated \
  --seeds 42,43,44 --rounds 15 --local-epochs 1 \
  --deadline-sec 240 --startup-timeout 600
```

### Results on this machine

All rows are pooled node1-node4 test slices (`n_test=7,013`,
`n_train=25,161`), mean ± std over seeds 42/43/44. Headline is raw unclipped.

| Method | Epochs | RMSE raw | MAE raw | R² raw |
| --- | ---: | ---: | ---: | ---: |
| Persistence (24 h) | 0 | 25.2435 | 13.8794 | 0.9429 |
| Centralized improved 24 h, 4 nodes | 12.67 | 24.9862 ± 0.5810 | 14.5723 ± 0.5125 | 0.9440 ± 0.0026 |
| Local-only improved 24 h, 4 nodes | 12.58 | 25.9442 ± 0.8332 | 15.4061 ± 0.9813 | 0.9396 ± 0.0039 |
| **FedAvg improved 24 h** | **15.00** | **24.2709 ± 0.1279** | **13.6546 ± 0.0813** | **0.9472 ± 0.0006** |

Clipped-target secondary metrics for the federated model: RMSE
23.5001 ± 0.1934, MAE 13.3172 ± 0.0990, R² 0.9492 ± 0.0008.

Unseen node5 (2014, never trained or scored into the pooled headline),
`n_test=1,752`:

| RMSE raw | MAE raw | R² raw |
| ---: | ---: | ---: |
| 22.3849 ± 0.1970 | 12.3869 ± 0.1182 | 0.9568 ± 0.0008 |

Per-seed federated results (15/15 rounds completed, 4/4 updates every round):

| Seed | Latest | Best (val loss) | RMSE raw | MAE raw | R² raw | Mean round time |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 42 | v0015 | v0013 (0.001757) | 24.3946 | 13.7470 | 0.9466 | 5.40 s |
| 43 | v0015 | v0014 (0.001729) | 24.1392 | 13.5945 | 0.9477 | 5.96 s |
| 44 | v0015 | v0014 (0.001762) | 24.2788 | 13.6222 | 0.9471 | 7.64 s |

Federated beats centralized, local-only, and persistence on all three pooled raw
metrics in this fair four-node comparison. The margin over centralized (0.72
RMSE) is close to centralized's seed std (0.58), so treat the gain as modest
rather than decisive. The improved delta target is what makes the learned models
competitive with persistence.

### Bytes per round vs raw training data

| Quantity | Bytes |
| --- | ---: |
| One float32 weight vector (9,025 params) | 36,100 |
| Chunks at 16 KiB | 3 |
| Mean wire bytes up per round (4 nodes) | 198,376.7 |
| Mean wire bytes down per round (global model + acks + start) | 100,554.8 |
| Mean wire bytes total per round | 298,931.5 |
| Raw windowed training tensors (node1-node4) | 13,418,400 |
| Raw feature rows (rough, 3 features × float32) | 335,736 |

Fifteen rounds move about **4.48 MB** total (298,931.5 × 15), versus
**13.42 MB** for a single copy of the raw windowed tensors. The server stores no
raw data.

### Stage 4 files

- `common/federated.py`, `common/model_delivery.py`, `common/broker.py`
- `server/dag_runner.py`, `server/fl_coordinator.py`, `server/offline_eval.py`
- `node/fl_node.py`
- `experiments/stage4_experiment.py`
- `tests/test_federated.py`, `tests/test_dag_runner.py`,
  `tests/test_model_delivery.py`, `tests/test_fl_integration.py`,
  `tests/test_offline_eval.py`
- Generated: `stage4_summary.json`, updated `results.csv`,
  `results_by_seed.csv`, `results.png`; per-seed registries and logs under the
  gitignored `.stage4_runs/`.

## Tests

```bash
python -m pytest -q
ruff check common baselines tests node server experiments
```

Current result on this machine: **79 passed**, lint clean. The broker-backed
tests skip if `mosquitto` is not installed. The real-weight test needs
TensorFlow. Coverage includes:

- Magnus-formula relative humidity and physical clipping
- PM2.5 forward-fill/interpolate/clip behaviour
- raw-vs-clipped target handling and no scaler leakage from test outliers
- sliding-window shapes, values, and target indices
- Min-Max scale/inverse round trip
- delta/horizon window alignment, cyclic-hour features, and delta reconstruction
- chunk splitting, out-of-order reassembly, SHA-256, duplicates, missing chunks
- float32 encode/decode round trip and exact weight preservation
- metadata validation: header, UTC timestamp, size/count/dtype, chunk count,
  round rules
- four-training-node / one-inference-only role split and sender refusal of an
  inference-only upload
- Stage 3 topic builders/parsers and JSON-safe chunk sequencing
- ack content without raw sensor readings
- receiver tolerance of identical QoS 1 duplicates and rejection of conflicts
- per-chunk SHA-256, whole-payload SHA-256, topic/payload index disagreement,
  and out-of-range chunk indexes
- real improved 24 h Keras weights round trip with unchanged predictions
- real-broker sender → receiver → ack, corrupted-chunk rejection,
  missing-chunk timeout, and inference-only rejection, each asserting that
  rejected transfers save nothing
- RMSE/MAE/R2, raw/clipped target scoring, mean/std aggregation
- stale per-seed rows are replaced when a method is rerun
- MQTT topic construction and JSON message/LWT payload helpers
- two real nodes with independent retained status and independent LWT
- FedAvg hand-computed on tiny unequal `n_samples`
- update validation rejects NaN/Infinity, bad checksum, wrong round id,
  inference-only sender, non-training sender, weight-count mismatch, and an
  abnormal weight norm
- DAG topological ordering, retries, per-task timeout, failure propagation, and
  cycle detection
- retained global-model delivery to a late subscriber, stale-version rejection,
  and buffering chunks that arrive before the announce
- end-to-end three-node dummy round on a throwaway broker, including
  hand-computed weighted FedAvg, `rounds.csv`, registry, acks, and a scan of
  every topic/payload for raw-reading fields
- a four-training-node + one-inference-only round where node4 is killed after
  the round starts; the round still completes with three updates and node5
  never uploads
- offline registry selection (`latest` vs `best` vs explicit version) and
  pooled test-slice scoring

## Methodology notes

- Node mapping: `node1=2010`, `node2=2011`, `node3=2012`, `node4=2013`,
  `node5=2014`. This five-year mapping is the Stage 1 data mapping used by the
  baselines. In the live MQTT topology, `node1`–`node4` are training nodes and
  `node5` is the inference-only phone (`federated.training_nodes` and
  `federated.inference_only_nodes`).
- Each node uses the first 80% of its year's rows for train/validation and the
  last 20% for test. The scaler and 99.5th-percentile clip value are fitted on
  training rows only, so test values do not leak into scaling.
- `pm2.5` is forward-filled first, then interpolated for any remaining leading
  gaps, then clipped at the global training 99.5th percentile.
- Raw unclipped targets use the same fill/interpolate step but skip the p99.5
  clip. They still contain no NaNs.
- Min-Max bounds are shared by every node through `common/config.json`.
- Paper-faithful model: `Conv1D(64) -> MaxPool -> Flatten -> reshape ->
  SimpleRNN(64, dropout=0.2) -> Dense(1)`, Adam lr 0.001, early stopping on
  validation loss.
- Improved model: same widths with `pool_size=1`, 12 h or 24 h windows, hour
  sin/cos appended, and a delta target in scaled space. The target index for
  horizon `h` is `i + window - 1 + h`; `h=1` is the next-hour task and `h=6`
  is the 6-hour-ahead task.
- Negative predictions are clipped to zero before computing metrics.
- Persistence uses the raw current-hour PM2.5 as its single prediction vector
  for both raw and clipped targets, matching how the learned models are scored.
- `local_only` trains five independent models; each is scored on its own test
  slice and then predictions are pooled for the headline metrics.
- Seed handling: centralized and PM2.5-only use the seed directly; local-only
  uses `seed + node_index` for its five models.
- Stage 3 transports contiguous little-endian float32 weights in JSON base64
  chunks of 16 KiB. The 16 KiB limit applies to the raw chunk before base64 and
  JSON overhead. Chunk count is `ceil(size / chunk_size)`; the last chunk is
  shorter and its exact length is checked.
- Stage 3 uses the existing `common/chunking.py` assembler and the existing
  `common/model.py` flatten/unflatten helpers. Topic builders and parsers live
  in `common/weight_transfer.py` so the sender, receiver, and tests share one
  contract.

## Known issues / current limits

- Stage 4 **averages** weights, but the final registered model (`latest.json`)
  has not itself been evaluated: nodes always evaluate the model they received.
  Use `best.json`/`--best` if you want the lowest validation-loss checkpoint.
  The headline in this README scores `latest.json`.
- Stage 4 validation-based selection uses each node's own validation split, not
  the test split. Test metrics come only from the separate offline scorer, so
  the test data never influences checkpoint selection.
- Stage 4 is simulated on one laptop: five node processes plus the server share
  one CPU and one TensorFlow install. Startup can take 60-90 seconds because
  TensorFlow import alone takes ~45 seconds; round time is 5-8 seconds.
- The Stage 4 inference-only `node.fl_node --inference-only` process is a
  laptop simulation and still imports TensorFlow. The phone/Termux client is a
  separate, later process and must not import TensorFlow.
- Stage 3 update chunks are **not retained**. Only the global announce and the
  Stage 4 global-model chunks are retained, so a receiver must be running before
  a node sends a round update. A receiver that starts late sees the retained
  global announce and then rejects it for missing chunks. There is no
  resume-after-reconnect or application-level retransmission for updates; the
  sender must resend the whole transfer.
- The receiver keeps accepted weights and receipts on disk, but in-flight
  transfers are memory-only and one-per-`(round, node)`. A restart loses
  partial progress.
- The prediction check is a deterministic synthetic probe compared on the first
  eight values plus a SHA-256 digest. It proves exact weight transport, not
  test-set accuracy, and it does not use raw node readings.
- Stage 3/4 has no message signing. It relies on the broker's password file and
  ACL (Profile B). Profile C is anonymous and demo-only, so anyone on the same
  trusted network can publish forged updates.
- There is no TLS listener enabled; the commented TLS block is an example.
- The phone/Termux client is still a later stage and must remain
  **inference-only** (`node5` in the live topology). It must not train or upload
  weights, and its code must not import TensorFlow. The server rejects any
  update from `node5` with an explicit ack; the broker ACL also omits `node5`'s
  update-write line.
- `mosquitto_passwd` is missing from this machine's source build, so the LAN
  password-file commands in `docs/mosquitto.conf` require installing it first.
  Profile C avoids it for demos; `docs/acl.example` already contains the Stage 3
  update-write lines for Profile B.
- The **paper-faithful** CNN-RNN does **not** beat persistence. The improved
  variant (delta target, 24 h window, no pooling, hour sin/cos) does:
  RMSE 23.726 vs 24.938 and R2 0.9499 vs 0.9447 over 3 seeds. The main fix is
  the delta target, which makes the model learn a correction to persistence
  instead of re-learning the current value.
- Federated 24 h wins the fair four-node comparison on pooled raw RMSE, MAE,
  and R², but the margin over centralized (0.72 RMSE) is close to centralized's
  seed std (0.58). With three seeds this is a modest, not decisive, gain. The
  federated run also uses more total local epochs (15) than centralized
  (12.67 ± early stopping), so compute is matched by budget, not by wall time.
- TensorFlow import takes ~45 seconds on the current Intel macOS machine.
- TensorFlow 2.16.2 is the available macOS x86 package for Python 3.12.
- Seeded training is deterministic where TensorFlow permits; timing varies with
  machine load. Metrics were stable enough across 3 seeds to report mean ± std.
- Profile A allows anonymous access on loopback only. Profile C allows anonymous
  access on the LAN for trusted-network demos only. Neither is an internet
  deployment profile.
- Stage 2 health payloads intentionally contain `null` sensor fields.

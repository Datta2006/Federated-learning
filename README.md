# Federated PM2.5 Forecasting on IoT Nodes

College IoT project. **Stages 1 and 2 are implemented**:

- **Stage 1:** real-data inspection, shared preprocessing, CNN-RNN model,
  centralized / local-only / persistence / PM2.5-only baselines, 3-seed
  evaluation, MQTT chunking helpers.
- **Stage 2:** Mosquitto broker config, MQTT node hello-world with retained
  online status, retained LWT offline status, health heartbeats, and a small
  server-side status/health observer.

Federated averaging, dataset replay, predictions, dashboard, and phone/Termux
nodes are later stages.

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

TensorFlow is **not** installed or required on Termux. Use a laptop Python 3.12
environment for Stage 1.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

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

## Stage 2: MQTT hello-world

### Broker

`docs/mosquitto.conf` is a local development broker config:

- listener on `127.0.0.1:1883` (loopback only for Stage 2; widening to
  `0.0.0.0` for phone/LAN nodes requires enabling auth/ACL/TLS)
- anonymous clients allowed **for local development only**
- persistence enabled at `/tmp/fedpm25-mosquitto/`
- commented username/password, ACL, and TLS examples

Run it from the project root:

```bash
mkdir -p /tmp/fedpm25-mosquitto
mosquitto -c docs/mosquitto.conf -v
```

On a normal machine the usual install is `brew install mosquitto`. On this
macOS 12 machine Homebrew's build failed in its Python/Sphinx docs stage, so
Mosquitto 2.0.20 was built from source with OpenSSL 3 and
`WITH_WEBSOCKETS=OFF`, then installed as `/usr/local/bin/mosquitto` plus
`mosquitto_pub` and `mosquitto_sub`.

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

### Topic contract

```text
aq/<node_id>/status      retained; online/offline; LWT uses offline
aq/<node_id>/health      QoS 1; heartbeat; not retained
aq/<node_id>/prediction  reserved for a later stage
aq/<node_id>/data/<k>    reserved for chunked data/weights
aq/server/...            reserved for server commands/rounds
```

## Tests

```bash
python -m pytest -q
ruff check common baselines tests node server
```

Current result: **24 passed**, lint clean. Coverage includes:

- Magnus-formula relative humidity and physical clipping
- PM2.5 forward-fill/interpolate/clip behaviour
- raw-vs-clipped target handling and no scaler leakage from test outliers
- sliding-window shapes, values, and target indices
- Min-Max scale/inverse round trip
- chunk splitting, out-of-order reassembly, SHA-256, duplicates, missing chunks
- RMSE/MAE/R2, raw/clipped target scoring, mean/std aggregation
- stale per-seed rows are replaced when a method is rerun
- MQTT topic construction and JSON message/LWT payload helpers

## Methodology notes

- Node mapping: `node1=2010`, `node2=2011`, `node3=2012`, `node4=2013`,
  `node5=2014`.
- Each node uses the first 80% of its year's rows for train/validation and the
  last 20% for test. The scaler and 99.5th-percentile clip value are fitted on
  training rows only, so test values do not leak into scaling.
- `pm2.5` is forward-filled first, then interpolated for any remaining leading
  gaps, then clipped at the global training 99.5th percentile.
- Raw unclipped targets use the same fill/interpolate step but skip the p99.5
  clip. They still contain no NaNs.
- Min-Max bounds are shared by every node through `common/config.json`.
- Model: `Conv1D(64) -> MaxPool -> Flatten -> reshape -> SimpleRNN(64,
  dropout=0.2) -> Dense(1)`, Adam lr 0.001, early stopping on validation loss.
- Negative predictions are clipped to zero before computing metrics.
- Persistence uses the raw current-hour PM2.5 as its single prediction vector
  for both raw and clipped targets, matching how the learned models are scored.
- `local_only` trains five independent models; each is scored on its own test
  slice and then predictions are pooled for the headline metrics.
- Seed handling: centralized and PM2.5-only use the seed directly; local-only
  uses `seed + node_index` for its five models.

## Known issues / current limits

- No federated averaging, dataset replay, prediction publishing, dashboard, or
  phone backend yet. Those are later stages.
- The CNN-RNN does **not** beat persistence on the current data/architecture.
  The likely causes are the very short 3-hour window, `MaxPool(2)` compressing
  it to one timestep for the RNN, and strong hour-to-hour autocorrelation.
  This should be addressed before claiming model superiority.
- TensorFlow import takes ~45 seconds on the current Intel macOS machine.
- TensorFlow 2.16.2 is the available macOS x86 package for Python 3.12.
- Seeded training is deterministic where TensorFlow permits; timing varies with
  machine load. Metrics were stable enough across 3 seeds to report mean ± std.
- The broker config allows anonymous access for local development only. The
  commented ACL/TLS blocks in `docs/mosquitto.conf` are examples, not enabled.
- Stage 2 health payloads intentionally contain `null` sensor fields.

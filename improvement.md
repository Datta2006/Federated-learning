# AirFed — Project Problems & Demo-Readiness Report

**Reviewed:** 21 November 2026
**Scope:** the federated PM2.5 forecasting project in this repository, with one
goal in mind: **can this be demonstrated live to a teacher who will ask "how
does it work?" and "show me the result?" without anything being hidden in a
terminal?**

**Method:** read the README, DEMO, product/design docs, dashboard backend and
frontend, coordinator, worker and protocol code; ran the test suite and the
TypeScript type-checker; queried the live dashboard API and the running
MQTT/coordinator/worker stack on this laptop; inspected the generated registry
and CSV artifacts.

No code was changed. This file is the only change.

---

## 1. Verdict

The engineering core is much stronger than the demo story around it.

- **The system really works.** All 120 tests pass in about 63 seconds, the
  frontend type-checks cleanly, the MQTT stack is live, and a real 14-round
  FedAvg history exists in the registry.
- **The main risk is not correctness. It is the first five minutes.**
  A person following `DEMO.md` is told to click buttons that do not exist,
  to rely on registry artifacts that are git-ignored, and to launch real
  TensorFlow workers that take roughly 45 seconds just to import. On a fresh
  clone the "Global models" and round-history pages will be empty.
- **The strongest evidence is buried in artifacts from different runs.**
  The dashboard mixes a live registry with a legacy `best.json`, an offline
  prediction export from an untracked `.stage4_runs` folder, and evaluation CSVs
  produced by a different experiment. A teacher can reasonably ask which run
  the numbers on screen belong to.
- **The demo shows an operations console, not an explanation.** There is no
  architecture overview, no visual explanation of what FedAvg is doing, and no
  single "here is the win" summary. You will have to provide that narration
  yourself.

**Bottom line:** demo-able, but only with a prepared environment and a fixed
runbook. Do not start the demo from a clean clone or trust `DEMO.md` as written.

---

## 2. What is genuinely solid (keep this)

These are worth saying out loud to the teacher, because they are real:

| Area | Evidence |
| --- | --- |
| Test coverage | `pytest`: 120 passed in 63s; includes real-broker, checksum, FedAvg, worker expiry, DAG and dynamic-session tests |
| Frontend quality | `tsc --noEmit` passes; seven coherent pages; honest empty/stale states |
| Real chunked weight transfer | float32 weights sent in 16 KiB chunks with per-chunk and whole-payload SHA-256 |
| Real FedAvg | sample-weighted aggregation, registry versions, rounds.csv history |
| Honest UI language | labels things as offline, historical, stale, single-client, or skipped |
| Working live stack | broker + coordinator + 10 simulated training workers were genuinely running and exchanging models when reviewed |
| Clear data pipeline | 2010–2013 training years, 2014 held out, no test leakage, documented baselines |

---

## 3. Problems that can break the live demonstration (P0)

### P0-1. The runbook tells the user to click controls that do not exist

`DEMO.md` step 2 and the root `README.md` say:

> **Workers** → **Start broker + coordinator**

No such button exists anywhere in the frontend. A grep of all frontend source
finds no call to `/api/processes/start` and no "Start broker" or "Start stack"
control. The broker and coordinator are actually started implicitly when you
press **Start session** on the Overview page or **Launch** on Workers.

`DEMO.md` also says the Workers page has a **"view logs"** control and a
**remove the dummy checkbox** workflow. The Workers page has neither: it only
shows a crash log tail, and it hard-codes `dummy: false`.

**Why it matters:** the first instruction in the primary demo path cannot be
followed. A first-time user will conclude the UI is broken before the demo
starts.

**Improvement:** either add the missing controls, or rewrite `DEMO.md` to match
the real flow exactly. At minimum, state that starting a session auto-starts the
broker and coordinator, and that the first start can take 30–60 seconds.

---

### P0-2. A fresh clone has no model registry, no round history, and no demo runs

`DEMO.md` says the dashboard falls back to:

> committed Stage 4 experiment runs under `.stage4_runs/`

This is false. `.stage4_runs/`, `server/model_registry/`,
`dashboard/frontend/dist/`, and `.airfed_runtime/` are all in `.gitignore`
and none are tracked by git.

Verified state:

| Artifact | Tracked? | Needed for | Fresh-clone result |
| --- | --- | --- | --- |
| `server/model_registry/` (latest, best, rounds.csv, 14 versions) | **No** | Global models, round history, live session proof | Empty; pages say "unavailable" |
| `.stage4_runs/` | **No** | Source of the air-quality prediction export | Missing |
| `dashboard/frontend/dist/` | **No** | Serving the UI from port 8010 | `./scripts/dev.sh` must rebuild it |
| `.airfed_runtime/` | **No** | Worker/coordinator logs | Missing (recreated) |
| `results.csv`, `results_by_seed.csv`, `stage4_summary.json` | Yes | Performance page | Works |
| `dashboard/backend/data/predictions.json` | Yes | Air Quality page | Works, but its `model_dir` points to the missing `.stage4_runs` run |
| `data/beijing_pm25.csv` | Yes | Dataset | Works |

**Why it matters:** this is the single biggest reproducibility problem. On the
evaluator's machine, the most convincing pages — **Global models** and
**Federated round history** — will be empty until a new session is trained. The
Air Quality page will still draw, but its provenance points at a directory that
does not exist.

**Improvement:** decide on one of two honest options:

1. Commit a small, curated demo registry and the matching Stage 4 run (or at
   least a small `demo_registry/` with provenance), and point the demo at it; or
2. Make the demo create its own artifacts in a dedicated run directory, and
   state clearly that the first run produces the history.

Do not claim that ignored files are committed.

---

### P0-3. The default UI path launches real TensorFlow workers, slowly, with no dummy mode

`SessionControl.tsx` defaults to `simulation_workers: 2`, `launch_workers:
true`, and the backend launches them with `simulation=True, dummy=False`.
`WorkersPage.tsx` also hard-codes `dummy: false`. There is no checkbox, no
"demo mode", and no fast protocol-only path.

Each worker imports TensorFlow (~45 seconds on this laptop, per the README),
then trains. A 3-round session with 2 workers is a multi-minute wait, and the
UI's only feedback during that time is a generic "waiting for workers" state.
If the user clicks Start while the coordinator is still booting, the request
can also sit behind the 30-second control-ping readiness loop.

**Why it matters:** a live demo has a short attention budget. "It is waiting"
for two minutes looks like a failure, especially when the previous session's
workers are already online and the new launch silently skips them.

**Improvement:** expose a clearly labelled **Demo (dummy weights)** option in
the UI and make it the default for a protocol demonstration; keep real
simulation as a separate "train for real" path. Pre-warm or pre-launch the
stack before the teacher arrives. Show a per-worker startup timeline ("process
started → TensorFlow imported → registered → waiting for selection") instead of
one spinner.

---

### P0-4. Leftover state contaminates every subsequent demo

The live instance reviewed had:

- 10 simulated workers still online **two days** after their session finished;
- a session in `completed` state from 19 November;
- `best.json` pointing to `v0001` from an older legacy run;
- a registry containing 17 rows from mixed legacy and dynamic runs;
- a 43 MB broker log in `.airfed_runtime/`.

There is no reset/clear/cleanup control in the UI. Session stop does not stop
worker processes. Starting a broker/coordinator that is already alive simply
returns "already running". `ProcessManager.start_workers` silently skips any
worker ID that is still alive: asking for 2 workers when `sim-1` and `sim-2`
exist reports `skipped` and reuses the old processes.

**Why it matters:** the dashboard can report "10 online" when you just asked
for 2, show a "best model" that was not produced by the demo, and display a
completed session before you touch anything. A teacher asking "why is that
already running?" is a bad start.

**Improvement:** add a **Reset demo environment** action (stop workers, stop
coordinator, optionally archive/clear the live registry, clear retained state);
give every run a run ID and display it on every page; separate legacy and
dynamic registries so "best" is scoped to one run.

---

### P0-5. There is no explanation of the system in the UI

The dashboard answers "what is the coordinator doing right now?" very well.
It does not answer "what is federated learning, what is this round doing, and
why is this better than just training centrally?" There is no:

- architecture diagram (worker → broker → coordinator → registry);
- MQTT topic map or message-flow view for a newcomer;
- explanation of FedAvg, local epochs, non-IID shards, or the delta target;
- one-screen summary of the project's research question and result.

The teacher will ask "how does it work?" and the honest answer requires you to
narrate code and topics that the UI never shows.

**Improvement (documentation or a small new panel, not necessarily code):** add
a single **Architecture / How it works** page or a slide that shows node
partitioning, the MQTT topics, one round's stages, and where FedAvg happens.
The existing StageRail is a good basis, but it shows state, not concepts.

---

### P0-6. Despite the IoT title, nothing runs on an IoT device

Everything — broker, coordinator, four "nodes", the inference-only `node5`,
the dashboard — runs on one laptop. `node5` is a command-line flag, not a phone;
there is no sensor feed, no ESP32/phone client, and the data is historical
replay. The dashboard does label the air-quality page as historical, which is
good, but the broader claim still needs framing.

**Why it matters:** in an IoT course, "where is the device?" is an obvious
question, and "it is simulated" can undersell the work if it is not positioned
correctly.

**Improvement:** present it honestly as a **federated edge/IoT simulation**, and
show the intended device role explicitly (the inference-only phone is the
future/real-world node). If any hardware demo is possible at all, even a phone
opening the dashboard or a single node process on another machine, it would
change the room's perception. Otherwise, put the word "simulated" in the title
slide, not in a footnote.

---

### P0-7. The "visible result" is split across incompatible runs

Three different evidence streams are shown together:

1. **Live registry** — `v0014`, dynamic workers `sim-1..sim-10`, 14 rounds,
   validation loss from `rounds.csv`.
2. **Legacy best** — `best.json` points to `v0001` with `n_samples: 25161`
   from the original four-node, full-year run.
3. **Offline predictions** — `predictions.json` is from `v0015` of
   `.stage4_runs/20261105T120202Z/seed-44`, and the Air Quality API correctly
   flags it as **stale** because the live registry's latest is `v0014`.

The Performance page's best baseline comes from a third artifact set
(`stage4_summary.json`, three seeds, raw/clipped metrics).

**Why it matters:** the teacher may ask "so which model is the result?" and the
honest answer is "four different runs, and the on-screen latest model has not
been scored yet." That is defensible academically but weak as a demo.

**Improvement:** produce one coherent demo run and show its lineage
(run ID → rounds → registered version → offline score). Label every number with
its run. Hide or quarantine legacy artifacts during the demo.

---

### P0-8. Failures are still debugged in the terminal

The design goal says "no terminal commands". In practice:

- there is no full log viewer in the UI, only crash tails;
- there is no UI control to stop the broker or coordinator;
- clearing a stuck retained session or stale worker requires MQTT tooling or a
  backend restart;
- the recovery instructions in `DEMO.md` are shell commands (`lsof`, `curl`,
  `kill`).

**Why it matters:** if the live demo wedges, the recovery path is exactly the
thing the project says it avoids.

**Improvement:** expose a read-only log panel for coordinator/broker/worker,
plus explicit stop/reset controls. Keep the shell commands as a fallback, not
as the primary recovery path.

---

## 4. Correctness and data-integrity problems (P1)

### P1-1. `rounds.csv` has a broken schema after dynamic sessions

The file's header has **10 columns**:

```
round, selected, received, dropped_nodes, bytes_up, bytes_down,
round_time_sec, weighted_val_loss, evaluated_version, model_version
```

Rows 12–14 have **15 fields**:

```
..., model_version, accepted_nodes, rejected_nodes, single_client,
aggregated, status
```

`ROUND_COLUMNS` in `server/fl_coordinator.py` was extended, but the existing
file header was never migrated. `dashboard/backend/registry.py` uses
`csv.DictReader`, so the extra columns are silently ignored. The dashboard's
round history therefore cannot show `status`, `aggregated`, or
`single_client` from the CSV, even though the live round view does.

**Why it matters:** the most objective audit artifact in the project is
malformed for any external reader (Excel, pandas, a marker), and the dashboard
quietly loses the fields that prove a round really aggregated.

**Improvement:** version the CSV schema, migrate or rotate the file, and add a
regression test for old and new rows.

### P1-2. The Communication page can show zero acknowledgements while the round says all were accepted

On the reviewed running instance, `/api/communication` reported:

```
acks_accepted: 0, acks_rejected: 0
```

while the same response's round progress showed all 10 workers `accepted`, and
the coordinator log showed 80 accepted acks. The event table was dominated by
`worker_state` and `health` messages. This needs investigation: either the ack
topic is not reaching the observer, the event buffer evicts acks, or a
reconnect resets totals.

**Why it matters:** "checksums and acknowledgements" is one of the project's
best technical selling points. A page that shows 0/0 during a successful round
undermines exactly the proof you want to show.

### P1-3. `latest.json` has no validation loss for the latest model, while `rounds.csv` does

`latest.json` for `v0014` has `weighted_val_loss: null` and `n_val: 0`;
the corresponding `rounds.csv` row has `0.00233` because it evaluates `v0013`.
That is internally consistent (the freshly aggregated model has not been
evaluated yet), but the UI shows both, and it looks like missing data.

**Improvement:** label the round as "evaluating the previous version" and show
the evaluation lineage explicitly.

### P1-4. Performance page uses clipped metrics while the documented headline is raw

The README says the headline result is **raw unclipped** targets. The
Performance page selects the "best baseline" using `rmse_clipped_mean` and
displays clipped RMSE/MAE/R². The raw numbers exist in `results.csv` but are not
shown. A teacher comparing the slide to the dashboard will see different values.

### P1-5. Session controls expose only part of what the backend supports

The UI exposes rounds, min workers, simulation workers, local epochs, and
deadline. The backend and README also claim configurable selection strategy,
max workers, mode (fixed/continuous), learning rate, window size, and
worker stop by ID. Those are API-only.

**Why it matters:** "the dashboard controls the full session lifecycle" is an
overclaim unless you use the API. Either scope the claim or expose the
controls.

### P1-6. No authentication and permissive CORS on a control API

The dashboard can start/stop sessions and launch up to 200 worker processes,
with `allow_origins=["*"]` and no token or origin check. Any web page the
browser visits could POST to `127.0.0.1:8010` and start a session (or read the
API). This is low risk on a private demo laptop but is a genuine security flaw.

### P1-7. No end-to-end or visual regression test

The 120 tests are backend-focused. There is no test that loads the dashboard,
starts a session in a browser, and asserts that the stage rail advances or that
the model card updates. Backend tests can pass while the primary demo flow is
broken (as the missing "Start broker" button illustrates).

---

## 5. Repository hygiene and reproducibility problems (P1/P2)

### P1-8. `node_modules` is committed to git

`git ls-files dashboard/frontend/node_modules | wc -l` returns **7,418 tracked
files**, including platform-specific binaries (`esbuild`, `rollup`). Meanwhile
`dist/` is correctly ignored.

Consequences:

- repository bloat and platform lock-in;
- any `npm install` produces a large diff;
- reviewers see generated third-party code instead of the project;
- the git pack is ~20 MB and the working `node_modules` is ~122 MB.

**Fix:** untrack `dashboard/frontend/node_modules`, add it to `.gitignore`, and
commit `package-lock.json` only.

### P1-9. Absolute local path committed in prediction metadata

`dashboard/backend/data/predictions.json` contains:

```
"model_dir": "/Users/apple/Documents/4thyear/iot/.stage4_runs/20261105T120202Z/seed-44/registry"
```

This is not portable and points to an ignored directory. The embedded
prediction series still works, but its provenance is broken on any other
machine.

### P1-10. The working directory is cluttered with generated state

Present but ignored: `.airfed_runtime/` (43 MB broker log, pid files),
`.stage4_runs/`, `server/model_registry/`, `.pytest_cache/`, `.ruff_cache/`,
`.DS_Store`, an empty `simulator/` directory. None of it is dangerous, but a
screen-shared file tree looks messy and makes it harder to answer "what is the
actual project?"

### P1-11. Setup is heavy and fragile for a demo machine

- Root `requirements.txt` includes TensorFlow (~hundreds of MB) even though the
  dashboard alone does not need it.
- `scripts/dev.sh` hard-codes `.venv`; using another environment fails.
- A fresh clone needs `npm install` (or relies on the committed
  `node_modules`), a frontend build, Mosquitto, and TensorFlow.
- `requirements.txt` pins `tensorflow==2.16.2`, which is tied to specific
  Python/macOS combinations.

**Improvement:** add a "dashboard-only" and a "full training" setup path, and
verify the demo path on a clean machine (or a fresh clone in a temp directory).

---

## 6. Documentation problems (P2)

The docs are extensive, but they contradict the app and each other:

| Claim | Reality |
| --- | --- |
| "Workers → Start broker + coordinator" (`DEMO.md`, `README.md`) | Button does not exist |
| "Remove the dummy checkbox" (`DEMO.md`) | Checkbox does not exist |
| "view logs" on Workers page (`DEMO.md`) | No log viewer; only crash tails |
| "committed Stage 4 experiment runs under `.stage4_runs/`" (`DEMO.md`) | Directory is git-ignored and untracked |
| "Current result: 118 passed" (`README.md`) | 120 tests now pass |
| "Federated results are not present yet" (Stage 1 section) | Stage 4 is implemented and has results |
| "dashboard controls selection strategy, max workers, etc." | Not exposed in the UI, only via API |

Also:

- `README.md` is ~1,050 lines and `DEMO.md` ~410 lines. There is no one-page
  summary a teacher can read in two minutes, and no slide-ready result.
- There is no setup verification script that says "your demo is ready" /
  "your demo is missing X".
- `dashboard/CLAUDE.md` contains agent-skill routing that is irrelevant to a
  course evaluator and adds noise to the repository.

---

## 7. Recommended demo plan (no code changes needed)

This is the order that makes the project look as good as it actually is.

### Before the teacher arrives (15 minutes)

1. Start from the existing `.venv`, not a clean clone.
2. Stop old workers and the coordinator; archive or move
   `server/model_registry/` if you want a clean run (do this deliberately and
   back it up).
3. Start `./scripts/dev.sh`, open the dashboard once, and confirm the API is
   live.
4. Start the broker/coordinator and 2 dummy workers **in advance** (via the
   API if the UI cannot) so TensorFlow is already imported and registered.
5. Keep one terminal open only for emergency recovery, not as part of the
   demo.
6. Prepare a 5-slide story: problem → architecture → one round → result →
   limitations.

### During the demo (5–7 minutes)

1. **One sentence of context:** "Air-quality nodes would normally send raw data
   to a server; here they train locally and only exchange model weights."
2. **Overview page:** show the session, workers, stage rail, and one round
   advancing. Explain selection → distribution → training → upload →
   validation → FedAvg → registration.
3. **Communication page:** show chunks, bytes, checksums, and acks. This is the
   most tangible "it is really happening over MQTT" evidence.
4. **Global models page:** show the version number increasing and the registry
   record. Point at the weight transfer size (9,025 parameters, ~36 KB, 3
   chunks).
5. **Performance page:** show the comparison against persistence, local-only,
   and centralized. State the honest result: FedAvg wins slightly; the margin
   is modest.
6. **Air Quality page:** show the offline prediction vs actual curve. Say
   clearly: "historical replay, not a live sensor."
7. **Limitations slide:** simulation, no phone yet, test metrics are offline,
   communication is not encrypted/signed in the demo profile.

### Do not do live

- Do not run the full baseline pipeline.
- Do not launch 10 real workers.
- Do not start from a clean clone.
- Do not let an unattended stale session be the first thing on screen.

---

## 8. Likely teacher questions and honest answers

| Question | Recommended answer |
| --- | --- |
| "Is this really federated?" | Yes: workers train locally and upload float32 weights; the server never sees raw rows. The dashboard proves it from MQTT traffic and registry records. |
| "Where is the IoT device?" | It is a local simulation of an edge deployment. `node5` represents the inference-only phone role; a physical client is future work. |
| "How do you know the model is better?" | Offline evaluation on the 2014 test year. FedAvg improves RMSE over persistence/local-only/centralized, but the margin over centralized is modest. |
| "Why is the validation loss 0.002 but RMSE 23?" | Loss is in scaled delta-target space; RMSE is in µg/m³ after inverse scaling. Mention this before it is asked. |
| "What happens if a node drops?" | The coordinator waits until the deadline, requires `min_workers`, marks missing updates, and skips registration if too few valid updates arrive. The tests cover this. |
| "Is it secure?" | Not for production: one trusted LAN, anonymous profile for the demo, no TLS/signing. The docs say so. |
| "What is your contribution?" | The working end-to-end system: chunked MQTT weight transfer, dynamic worker registration/selection, sample-weighted FedAvg, a versioned registry, and an honest operations dashboard. |
| "Why is the latest model not scored?" | Nodes evaluate the model they receive; the newly aggregated model is scored in the next round or by the offline scorer. Use `best.json`/`--best` for the best checkpoint. |

---

## 9. Prioritized improvements

| Priority | Improvement | Why |
| --- | --- | --- |
| P0 | Fix or rewrite `DEMO.md`/README to match the real UI | The current first instruction is impossible |
| P0 | Provide a committed, small demo registry + matching run, or generate one in a dedicated run directory | Fresh clone currently demonstrates empty pages |
| P0 | Add a **Demo (dummy)** mode and pre-warm the stack | Turns a multi-minute wait into a fast, visible round |
| P0 | Add reset/cleanup for workers, coordinator, retained state, and registry | Prevents stale state from hijacking the demo |
| P0 | Choose one run and label every number with its run/version | Removes "which model is the result?" confusion |
| P0 | Add an architecture/how-it-works view or slide | The teacher's first question is conceptual |
| P1 | Fix the `rounds.csv` schema migration | The audit artifact is malformed |
| P1 | Investigate the 0/0 ack counter | It undercuts the strongest protocol proof |
| P1 | Show both raw and clipped metrics, and the seed spread | Matches the documented headline |
| P1 | Expose the remaining session controls or narrow the claim | Avoids overclaiming |
| P1 | Add a minimal end-to-end UI smoke test | Prevents dead demo paths |
| P1 | Stop tracking `node_modules`; ignore it | Repo bloat and platform lock-in |
| P2 | Remove absolute paths from committed metadata | Portability |
| P2 | Add a one-page summary/slide deck | Teacher-facing clarity |
| P2 | Clean generated clutter from the workspace before demoing | Perceived quality |
| P2 | Add auth/origin check to the control API | Real, even if low-risk locally |

---

## 10. Pre-demo checklist

- [ ] Working directory is the prepared laptop, not a fresh clone.
- [ ] `.venv`, `npm`, Mosquitto, and TensorFlow all verified.
- [ ] Frontend build exists and `http://127.0.0.1:8010/` loads.
- [ ] Old sessions/workers consciously cleaned or intentionally reused.
- [ ] Coordinator, broker, and two workers already registered.
- [ ] One short session has been run end-to-end today.
- [ ] Registry has a version you are happy to point at.
- [ ] Performance page shows a sensible best baseline.
- [ ] Air Quality page's "offline/historical" labels are visible.
- [ ] Communication page shows non-zero traffic during a round.
- [ ] You have a one-slide architecture diagram.
- [ ] You have a one-slide result and a one-slide limitations page.
- [ ] Emergency recovery commands are in a note, not memorized.
- [ ] No terminal window is the center of attention.

---

## 11. What was verified during this review

- `pytest -q`: **120 passed**, 1 deprecation warning, 63.26 s.
- `npx tsc --noEmit` in `dashboard/frontend`: exit 0.
- Live API on `127.0.0.1:8010`: health/status/rounds/model/metrics/air-quality/
  communication all respond.
- Live stack: Mosquitto on 1883, coordinator, and 10 `node.fl_node` workers
  running; 14 dynamic rounds and 80 accepted updates recorded.
- `rounds.csv`: 10-column header, 15-field rows for rounds 12–14.
- `/api/model`: latest `v0014` with `weighted_val_loss: null`; best `v0001`
  from a legacy run; transfer 9,025 parameters / 36,100 bytes / 3 chunks.
- `/api/air-quality`: prediction export `v0015`, live registry `v0014`,
  `prediction_stale: true`.
- `/api/communication`: `acks_accepted: 0` while round progress showed 10
  accepted acks.
- Git: `node_modules` tracked (7,418 files); `.stage4_runs`,
  `server/model_registry`, `dashboard/frontend/dist`, `.airfed_runtime` all
  untracked/ignored.
- Runtime: 43 MB `broker.log`, workers alive for ~2 days, session state from
  19 November still retained.

---

*This report is intentionally critical. The purpose is not to diminish the
work, which is substantial, but to make sure the live demonstration survives
the first question and the first empty page.*

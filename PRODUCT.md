# AirFed — Product context

## What this is

AirFed is a federated-learning system for next-hour PM2.5 forecasting across a
small network of air-quality nodes. This repository contains the training
pipeline, MQTT protocol, coordinator, simulated/remote workers, and a local
operations dashboard.

The dashboard is the operator surface. It does not train models; it observes,
explains, and (through an explicit control adapter) starts/stops coordinator
sessions.

## Who uses it

- An engineer running a demo or a study on one machine.
- A reviewer who needs to see that a federated round is genuinely happening:
  which workers were selected, what they uploaded, what was aggregated, and
  which model version was registered.
- A maintainer diagnosing a stalled coordinator or a worker that stopped
  heartbeating.

## Jobs to be done

1. **Know the state in five seconds.** Is the coordinator alive? Is a session
   running or idle? Which round and stage is it in? Are workers online?
2. **Start a trustworthy session.** The dashboard must not report success until
   the coordinator has acknowledged the command with a correlated request id.
3. **Follow a round end to end.** Selected clients → distribution → training →
   upload → validation → FedAvg → registration.
4. **Audit history.** Global model versions, validation loss per round,
   performance baselines, and communication volume.
5. **Understand air-quality output honestly.** Distinguish offline FedAvg
   predictions from the persistence reference and historical replay.

## Non-negotiables

- Never fabricate progress, metrics, stages, or training data. If a value is not
  confirmed by the backend, show its absence.
- The dashboard is read-only over MQTT except for the explicit control
  publisher.
- The legacy five-node Stage-4 topology, offline evaluation artifacts, REST
  contracts, and dynamic worker registration must keep working.
- Degrade gracefully: no broker, no workers, or no session must still render a
  coherent, honest UI.

## Success

An operator can open the dashboard, start a two-client FedAvg session, watch
each stage transition in real time, and see the registered model version — with
no terminal commands and no invented intermediate states.

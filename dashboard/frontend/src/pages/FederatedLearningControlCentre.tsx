import { useState } from "react";
import { useCommandCenter } from "../hooks/useCommandCenter";
import { usePoll } from "../hooks/usePoll";
import { useAction } from "../hooks/useAction";
import type { CommandResponse, RoundsPayload, Stage } from "../types";
import { pendingStages } from "../lib/stages";
import { formatBytes, formatNumber, relativeTime } from "../lib/format";
import { ChartLegend, LineChart } from "../components/charts/LineChart";
import {
  Badge,
  Dot,
  Empty,
  Field,
  Panel,
  Progress,
  Stat,
  StatusBadge,
} from "../components/primitives";

const ACTIVE = new Set(["starting", "waiting", "running", "paused", "stopping"]);

const stageClass: Record<string, string> = {
  complete: "stage stage-complete",
  active: "stage stage-active",
  failed: "stage stage-failed",
  skipped: "stage stage-skipped",
  pending: "stage",
};

export function FederatedLearningControlCentrePage() {
  const { status, refresh } = useCommandCenter();
  const roundsPoll = usePoll<RoundsPayload>("/api/rounds?limit=40", 5000);
  const action = useAction<CommandResponse>();

  const [rounds, setRounds] = useState(3);
  const [minWorkers, setMinWorkers] = useState(2);
  const [simWorkers, setSimWorkers] = useState(3);
  const [localEpochs, setLocalEpochs] = useState(1);
  const [deadline, setDeadline] = useState(120);
  const [dummyWorkers, setDummyWorkers] = useState(true);

  const session = status?.session_view ?? null;
  const round = status?.current_round ?? null;
  const state = session?.state ?? "idle";
  const active = ACTIVE.has(state);
  const stages: Stage[] = round?.stages?.length ? round.stages : pendingStages();
  const history = roundsPoll.data?.history ?? [];
  const recent = [...history].reverse().slice(0, 15);
  const lossHistory = roundsPoll.data?.loss_history ?? [];
  const lossSeries = [
    {
      name: "Weighted val loss",
      color: "var(--accent)",
      values: lossHistory.map((row) => row.weighted_val_loss),
    },
  ];

  const send = async (actionName: "start" | "pause" | "resume" | "stop") => {
    const body =
      actionName === "start"
        ? {
            action: actionName,
            config: {
              mode: "fixed",
              rounds,
              min_workers: minWorkers,
              max_workers: null,
              local_epochs: localEpochs,
              deadline_sec: deadline,
              selection_strategy: "all",
              aggregation_method: "fedavg",
              window_hours: 24,
              learning_rate: 0.001,
              simulation_workers: simWorkers,
              launch_workers: simWorkers > 0,
              worker_role: "training",
              dummy_workers: dummyWorkers,
            },
          }
        : { action: actionName };
    const result = await action.run("/api/control/session", body);
    if (result?.ok) {
      refresh();
      roundsPoll.refresh();
    }
  };

  const completed = session?.completed_rounds ?? 0;
  const total = session?.total_rounds ?? null;
  const progress = total && total > 0 ? (completed / total) * 100 : session?.progress ?? null;
  const currentLoss = round?.weighted_val_loss ?? null;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Federated learning session</h1>
          <p className="page-sub">
            A start is reported only after the coordinator echoes the request id. Stage progress is
            inferred from observed MQTT metadata; pending stages stay pending.
          </p>
        </div>
        <div className="toolbar">
          <StatusBadge status={state} />
          {session?.stale && <Badge tone="warn">state is stale</Badge>}
          <span className="mono tiny faint">{session?.session_id ?? "no session id"}</span>
          <button className="btn btn-sm" type="button" onClick={() => { refresh(); roundsPoll.refresh(); }}>
            Refresh
          </button>
        </div>
      </div>

      {action.error && (
        <div className="notice notice-bad" role="alert">
          <span style={{ flex: 1 }}>{action.error}</span>
        </div>
      )}
      {action.result?.ok && (
        <div className="notice notice-ok">
          Coordinator acknowledged <span className="mono">{action.result.command}</span>
          {action.result.request_id ? ` · ${action.result.request_id.slice(0, 10)}` : ""}
          {action.result.idempotent_replay ? " · replay of an accepted command" : ""}
        </div>
      )}

      <div className="stat-grid">
        <Stat label="Session state" value={state} sub={session?.message ?? "no session observed"} />
        <Stat
          label="Round"
          value={round?.round ?? (completed || "—")}
          sub={round?.phase_label ?? (active ? "waiting" : "idle")}
        />
        <Stat
          label="Completed rounds"
          value={total ? `${completed}/${total}` : completed}
          sub={session?.remaining_rounds !== null && session?.remaining_rounds !== undefined ? `${session.remaining_rounds} remaining` : "—"}
        />
        <Stat
          label="Weighted val loss"
          value={currentLoss === null ? "—" : formatNumber(currentLoss, 4)}
          sub={round?.registered_version ? `registered ${round.registered_version}` : "not registered yet"}
        />
      </div>

      <div className="cols">
        <Panel
          title="Session control"
          subtitle={
            active
              ? "Commands are published over MQTT and wait for the coordinator acknowledgement."
              : "Configure a fixed-round FedAvg session. Demo weights skip TensorFlow."
          }
          actions={<StatusBadge status={state} />}
        >
          {!active && (
            <div className="form-grid" style={{ marginBottom: 12 }}>
              <Field label="Rounds">
                <input className="input" type="number" min={1} max={50} value={rounds} onChange={(event) => setRounds(Number(event.target.value))} />
              </Field>
              <Field label="Min workers">
                <input className="input" type="number" min={1} max={20} value={minWorkers} onChange={(event) => setMinWorkers(Number(event.target.value))} />
              </Field>
              <Field label="Launch sims">
                <input className="input" type="number" min={0} max={20} value={simWorkers} onChange={(event) => setSimWorkers(Number(event.target.value))} />
              </Field>
              <Field label="Local epochs">
                <input className="input" type="number" min={1} max={10} value={localEpochs} onChange={(event) => setLocalEpochs(Number(event.target.value))} />
              </Field>
              <Field label="Deadline (s)">
                <input className="input" type="number" min={10} max={3600} value={deadline} onChange={(event) => setDeadline(Number(event.target.value))} />
              </Field>
            </div>
          )}

          {!active && (
            <label className="check" style={{ marginBottom: 12 }}>
              <input type="checkbox" checked={dummyWorkers} onChange={(event) => setDummyWorkers(event.target.checked)} />
              <span>
                <strong>Demo mode</strong> — launch dummy workers and skip TensorFlow initialization.
              </span>
            </label>
          )}

          <div className="toolbar">
            {!active && (
              <button className="btn btn-primary" type="button" disabled={action.pending} onClick={() => void send("start")}>
                Start session
              </button>
            )}
            {active && state !== "paused" && state !== "stopping" && (
              <button className="btn" type="button" disabled={action.pending} onClick={() => void send("pause")}>
                Pause
              </button>
            )}
            {state === "paused" && (
              <button className="btn btn-primary" type="button" disabled={action.pending} onClick={() => void send("resume")}>
                Resume
              </button>
            )}
            {active && (
              <button className="btn btn-danger" type="button" disabled={action.pending} onClick={() => void send("stop")}>
                Stop session
              </button>
            )}
            {action.pending && <span className="loading-text">Publishing and waiting for acknowledgement…</span>}
          </div>

          <div style={{ marginTop: 16 }}>
            <div className="spread" style={{ marginBottom: 6 }}>
              <span className="small muted">
                {total ? `${completed} of ${total} rounds completed` : `${completed} rounds completed`}
              </span>
              <span className="mono small">{progress === null ? "—" : `${Math.round(progress)}%`}</span>
            </div>
            <Progress value={progress} />
          </div>
        </Panel>

        <Panel title="Current round" subtitle={round ? `source: ${round.source}` : "No live round observed"} bodyTight>
          {!round ? (
            <Empty title="No round in progress" hint="Start a session to create round state." />
          ) : (
            <dl className="kv" style={{ padding: "4px 16px 12px" }}>
              <div>
                <dt>Selected</dt>
                <dd className="mono">{round.selected?.join(", ") || "—"}</dd>
              </div>
              <div>
                <dt>Upload nodes</dt>
                <dd className="mono">{round.upload_nodes?.join(", ") || "—"}</dd>
              </div>
              <div>
                <dt>Accepted</dt>
                <dd className="mono">{round.accepted?.join(", ") || "—"}</dd>
              </div>
              <div>
                <dt>Rejected</dt>
                <dd className="mono">{round.rejected?.join(", ") || "—"}</dd>
              </div>
              <div>
                <dt>Bytes up</dt>
                <dd className="mono">{formatBytes(round.bytes_up)}</dd>
              </div>
              <div>
                <dt>Bytes down</dt>
                <dd className="mono">{formatBytes(round.bytes_down)}</dd>
              </div>
              <div>
                <dt>Live</dt>
                <dd>{round.is_live ? "yes" : "no"}</dd>
              </div>
              <div>
                <dt>Model version</dt>
                <dd className="mono">{round.model_version ?? "—"}</dd>
              </div>
            </dl>
          )}
        </Panel>
      </div>

      <Panel title="Round stages" subtitle="Only the coordinator can mark a stage complete.">
        <div className="stages">
          {stages.map((stage, index) => (
            <div key={stage.key} className={stageClass[stage.status] ?? "stage"}>
              <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>
              <div style={{ minWidth: 0 }}>
                <div className="stage-label">{stage.label}</div>
                <div className="stage-status">{stage.status}</div>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="cols">
        <Panel
          title="Validation loss"
          subtitle="Weighted validation loss per registered round"
          actions={lossHistory.length > 0 ? <span className="tiny faint">{lossHistory.length} points</span> : null}
        >
          {lossHistory.length > 0 && <ChartLegend series={lossSeries} />}
          <LineChart
            series={lossSeries}
            labels={lossHistory.map((row) => `r${row.round}`)}
            caption="Weighted validation loss per round"
          />
        </Panel>

        <Panel title="Observer note" subtitle="How these values are produced">
          <div className="stack" style={{ gap: 10 }}>
            <p className="small muted">{roundsPoll.data?.note ?? "Round history comes from the coordinator registry."}</p>
            <dl className="kv">
              <div>
                <dt>Registry</dt>
                <dd className="mono">{roundsPoll.data?.source ?? "—"}</dd>
              </div>
              <div>
                <dt>Rounds file</dt>
                <dd className="mono small">{roundsPoll.data?.registry_path ?? "—"}</dd>
              </div>
              <div>
                <dt>Round live</dt>
                <dd>{roundsPoll.data?.round_is_live ? "yes" : "no"}</dd>
              </div>
              <div>
                <dt>Round stale</dt>
                <dd>{roundsPoll.data?.round_is_stale ? "yes" : "no"}</dd>
              </div>
            </dl>
            {roundsPoll.error && <div className="notice notice-bad">{roundsPoll.error}</div>}
          </div>
        </Panel>
      </div>

      <Panel title="Round history" subtitle="Newest first" bodyTight>
        {recent.length === 0 ? (
          <Empty title="No rounds recorded yet" hint="Completed rounds will appear here from the coordinator registry." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Round</th>
                  <th className="right">Selected</th>
                  <th className="right">Received</th>
                  <th className="right">Dropped</th>
                  <th className="right">Bytes up</th>
                  <th className="right">Seconds</th>
                  <th className="right">Val loss</th>
                  <th>Version</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((row) => (
                  <tr key={row.round}>
                    <td className="primary mono">{row.round}</td>
                    <td className="num">{row.selected?.length ?? 0}</td>
                    <td className="num">{row.received ?? 0}</td>
                    <td className="num">{row.dropped_nodes?.length ?? 0}</td>
                    <td className="num">{formatBytes(row.bytes_up)}</td>
                    <td className="num">{formatNumber(row.round_time_sec, 1)}</td>
                    <td className="num">{formatNumber(row.weighted_val_loss, 4)}</td>
                    <td className="mono">{row.model_version || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="row tiny faint">
        <Dot tone={status?.broker.connected ? "ok" : "bad"} />
        broker {status?.broker.connected ? "connected" : "unreachable"} · last update{" "}
        {session?.updated_utc ? relativeTime(session.updated_utc) : "—"}
      </div>
    </div>
  );
}

import { useState } from "react";
import {
  CircleStop,
  Gauge,
  Pause,
  Play,
  Radio,
  RefreshCw,
  RotateCw,
} from "lucide-react";
import { useApi } from "../lib/useApi";
import { useAction } from "../hooks/useAction";
import { useLiveFeed } from "../hooks/useLiveFeed";
import { formatInteger, formatNumber, relativeTime, titleCase } from "../lib/format";
import type {
  CommandResponse,
  LiveRoundsPayload,
  RoundSummaryView,
  RoundsPayload,
  SessionPayload,
  TrainingConfigInput,
} from "../types";
import {
  Badge,
  EmptyState,
  ErrorState,
  Kpi,
  PageSkeleton,
  Panel,
  PanelHeader,
  SummaryRow,
} from "../components/ui";
import { StageTrack } from "../components/StageTrack";

const defaultConfig: TrainingConfigInput = {
  mode: "fixed",
  rounds: 3,
  min_workers: 1,
  max_workers: null,
  local_epochs: 1,
  deadline_sec: 60,
  selection_strategy: "all",
  aggregation_method: "fedavg",
  window_hours: 24,
  learning_rate: 0.001,
  simulation_workers: 0,
  launch_workers: true,
  worker_role: "training",
};

export function FederatedPage() {
  const session = useApi<SessionPayload>("/api/session", 2500);
  const live = useApi<LiveRoundsPayload>("/api/rounds/live", 2500);
  const history = useApi<RoundsPayload>("/api/rounds?limit=40", 5000);
  const { revision } = useLiveFeed();
  const control = useAction<CommandResponse>();
  const [config, setConfig] = useState<TrainingConfigInput>(defaultConfig);

  if (session.loading && !session.data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <PageSkeleton rows={3} />
      </div>
    );
  }
  if (session.error && !session.data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <ErrorState message={session.error} onRetry={session.refresh} />
      </div>
    );
  }
  if (!session.data) return null;

  const data = session.data;
  const state = data.session?.state ?? "idle";
  const running = state === "running" || state === "waiting" || state === "paused";
  const round = live.data?.current_round ?? data.current_round;
  const summaries = live.data?.summaries ?? data.round_summaries ?? [];
  const counts = data.worker_counts;

  const update = <K extends keyof TrainingConfigInput>(key: K, value: TrainingConfigInput[K]) =>
    setConfig((current) => ({ ...current, [key]: value }));

  const runControl = async (action: "start" | "pause" | "resume" | "stop") => {
    await control.run("/api/control/session", {
      action,
      config: action === "start" ? config : undefined,
    });
    session.refresh();
    live.refresh();
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 pb-10 pt-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Session"
          value={titleCase(state)}
          tone={state === "running" ? "emerald" : state === "paused" ? "amber" : "blue"}
          icon={<Radio size={15} />}
          hint={data.session?.session_id ?? "No session started yet"}
        />
        <Kpi
          label="Round"
          value={data.session?.round ?? round?.round ?? "—"}
          icon={<Gauge size={15} />}
          tone="violet"
          hint={data.session ? `${data.session.completed_rounds} completed` : "—"}
        />
        <Kpi
          label="Available workers"
          value={formatInteger(counts?.available ?? 0)}
          icon={<Play size={15} />}
          tone="emerald"
          hint={`${counts?.online ?? 0} online · ${counts?.training ?? 0} training`}
        />
        <Kpi
          label="Last update"
          value={relativeTime(data.session?.updated_utc ?? null)}
          icon={<RefreshCw size={15} />}
          hint={data.session?.message ?? "No coordinator message"}
        />
      </div>

      {control.error ? <ErrorState title="Control command failed" message={control.error} /> : null}

      <Panel>
        <PanelHeader
          title="Training configuration"
          subtitle="Commands are published over MQTT to the control coordinator. Worker selection is frozen per round."
          icon={<Gauge size={15} />}
          action={
            <div className="flex flex-wrap gap-1.5">
              <button type="button" className="btn btn-primary" disabled={control.pending} onClick={() => void runControl("start")}>
                <Play size={13} /> Start
              </button>
              <button type="button" className="btn" disabled={control.pending || !running} onClick={() => void runControl("pause")}>
                <Pause size={13} /> Pause
              </button>
              <button type="button" className="btn" disabled={control.pending || !running} onClick={() => void runControl("resume")}>
                <RotateCw size={13} /> Resume
              </button>
              <button type="button" className="btn" disabled={control.pending || !running} onClick={() => void runControl("stop")}>
                <CircleStop size={13} /> Stop
              </button>
            </div>
          }
        />
        <div className="grid gap-3 px-5 pb-5 pt-1 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="label">Mode</span>
            <select className="input mt-1" value={config.mode} onChange={(event) => update("mode", event.target.value as TrainingConfigInput["mode"])}>
              <option value="fixed">fixed rounds</option>
              <option value="continuous">continuous</option>
            </select>
          </label>
          <label className="block">
            <span className="label">Rounds</span>
            <input className="input mt-1" type="number" min={1} max={1000} value={config.rounds} onChange={(event) => update("rounds", Math.max(1, Number(event.target.value) || 1))} />
          </label>
          <label className="block">
            <span className="label">Min workers</span>
            <input className="input mt-1" type="number" min={1} max={200} value={config.min_workers} onChange={(event) => update("min_workers", Math.max(1, Number(event.target.value) || 1))} />
          </label>
          <label className="block">
            <span className="label">Max workers (blank = all)</span>
            <input
              className="input mt-1"
              type="number"
              min={1}
              max={200}
              value={config.max_workers ?? ""}
              onChange={(event) => update("max_workers", event.target.value === "" ? null : Math.max(1, Number(event.target.value)))}
            />
          </label>
          <label className="block">
            <span className="label">Selection</span>
            <select className="input mt-1" value={config.selection_strategy} onChange={(event) => update("selection_strategy", event.target.value as TrainingConfigInput["selection_strategy"])}>
              <option value="all">all eligible</option>
              <option value="random">random up to max</option>
            </select>
          </label>
          <label className="block">
            <span className="label">Aggregation</span>
            <select className="input mt-1" value={config.aggregation_method} onChange={() => undefined}>
              <option value="fedavg">sample-weighted FedAvg</option>
            </select>
          </label>
          <label className="block">
            <span className="label">Local epochs</span>
            <input className="input mt-1" type="number" min={1} max={50} value={config.local_epochs} onChange={(event) => update("local_epochs", Math.max(1, Number(event.target.value) || 1))} />
          </label>
          <label className="block">
            <span className="label">Deadline (seconds)</span>
            <input className="input mt-1" type="number" min={1} max={3600} value={config.deadline_sec} onChange={(event) => update("deadline_sec", Math.max(1, Number(event.target.value) || 1))} />
          </label>
          <label className="block">
            <span className="label">Window hours</span>
            <input className="input mt-1" type="number" min={1} max={168} value={config.window_hours} onChange={(event) => update("window_hours", Math.max(1, Number(event.target.value) || 1))} />
          </label>
          <label className="block">
            <span className="label">Learning rate</span>
            <input className="input mt-1" type="number" min={0.00001} step={0.0001} value={config.learning_rate} onChange={(event) => update("learning_rate", Number(event.target.value) || 0.001)} />
          </label>
          <label className="block">
            <span className="label">Simulation workers to launch</span>
            <input className="input mt-1" type="number" min={0} max={200} value={config.simulation_workers} onChange={(event) => update("simulation_workers", Math.max(0, Number(event.target.value) || 0))} />
          </label>
          <label className="mt-6 flex items-center gap-2 text-[12px] text-mist-300">
            <input type="checkbox" checked={config.launch_workers} onChange={(event) => update("launch_workers", event.target.checked)} />
            Start broker/coordinator and launch workers
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3 border-t border-ink-700/60 px-5 py-3 text-[11px] text-mist-500">
          <Badge tone="mist">config v{revision}</Badge>
          <span>Minimum required: {config.min_workers} · deadline {config.deadline_sec}s · {config.local_epochs} local epoch(s)</span>
          <span>Single-client rounds are explicitly marked, never presented as a full aggregate.</span>
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title={round ? `Round ${round.round}` : "Current round"}
          subtitle={round ? `${round.phase_label} · ${round.is_live ? "live" : "not live"} · source ${round.source}` : "No round telemetry yet."}
          icon={<Gauge size={15} />}
          action={round?.single_client ? <Badge tone="amber">single client round</Badge> : undefined}
        />
        <div className="space-y-4 px-5 pb-5 pt-2">
          {!round ? (
            <EmptyState
              title="Waiting for a round"
              message="Start a session with at least one online training worker. Stage rows come from retained coordinator progress messages, so skipped work is shown as skipped."
            />
          ) : (
            <>
              <StageTrack stages={round.stages ?? []} />
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
                <SummaryRow label="status" value={round.phase_label} />
                <SummaryRow label="selected" value={formatInteger(round.selected.length)} />
                <SummaryRow label="accepted" value={formatInteger(round.accepted.length)} />
                <SummaryRow label="rejected" value={formatInteger(round.rejected.length)} />
                <SummaryRow label="bytes up" value={formatInteger(round.bytes_up)} />
                <SummaryRow label="bytes down" value={formatInteger(round.bytes_down)} />
              </div>
              {round.accepted.length > 0 || round.rejected.length > 0 ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  <div>
                    <span className="label">Accepted updates</span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {round.accepted.length === 0 ? <span className="text-[11px] text-mist-500">none</span> : round.accepted.map((id) => <Badge key={id} tone="emerald">{id}</Badge>)}
                    </div>
                  </div>
                  <div>
                    <span className="label">Rejected updates</span>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {round.rejected.length === 0 ? <span className="text-[11px] text-mist-500">none</span> : round.rejected.map((id) => (
                        <Badge key={id} tone="red">
                          {id}{round.reasons[id] ? ` · ${round.reasons[id]}` : ""}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        <PanelHeader
          title="Round summaries"
          subtitle="Retained audit record per round: accepted, rejected, checksums, aggregation, model version."
          icon={<CircleStop size={15} />}
          action={<button type="button" className="btn" onClick={() => live.refresh()}><RefreshCw size={13} /> Refresh</button>}
        />
        {summaries.length === 0 ? (
          <EmptyState title="No completed rounds" message="Summaries appear after each round finishes or fails. They are published retained on the round summary topic." />
        ) : (
          <SummaryTable summaries={[...summaries].reverse()} />
        )}
      </Panel>

      <Panel className="overflow-hidden">
        <PanelHeader
          title="Registered round history"
          subtitle="Coordinator registry rows (rounds.csv) — independent of live MQTT telemetry."
          icon={<Gauge size={15} />}
        />
        {!history.data || history.data.history.length === 0 ? (
          <EmptyState title="No registry rounds" message="The registry has no rounds yet. This is expected before the first completed round." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead className="border-y border-ink-700/70 bg-ink-800/40 text-mist-500">
                <tr>
                  <th className="px-4 py-2 font-medium">round</th>
                  <th className="px-3 py-2 font-medium">selected</th>
                  <th className="px-3 py-2 font-medium">received</th>
                  <th className="px-3 py-2 font-medium">dropped</th>
                  <th className="px-3 py-2 font-medium">val loss</th>
                  <th className="px-3 py-2 font-medium">round time</th>
                  <th className="px-3 py-2 font-medium">model</th>
                </tr>
              </thead>
              <tbody>
                {[...history.data.history].reverse().map((row) => (
                  <tr key={row.round} className="border-b border-ink-700/40 last:border-0">
                    <td className="px-4 py-2 mono text-mist-100">{row.round}</td>
                    <td className="px-3 py-2 mono text-mist-300">{row.selected.length}</td>
                    <td className="px-3 py-2 mono text-mist-300">{row.received}</td>
                    <td className="px-3 py-2 mono text-signal-red/90">{row.dropped_nodes.length ? row.dropped_nodes.join(", ") : "—"}</td>
                    <td className="px-3 py-2 mono text-mist-200">{formatNumber(row.weighted_val_loss, 6)}</td>
                    <td className="px-3 py-2 mono text-mist-300">{row.round_time_sec === null ? "—" : `${formatNumber(row.round_time_sec, 1)} s`}</td>
                    <td className="px-3 py-2 mono text-signal-violet">{row.model_version || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function SummaryTable({ summaries }: { summaries: RoundSummaryView[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[11px]">
        <thead className="border-y border-ink-700/70 bg-ink-800/40 text-mist-500">
          <tr>
            <th className="px-4 py-2 font-medium">round</th>
            <th className="px-3 py-2 font-medium">status</th>
            <th className="px-3 py-2 font-medium">selected</th>
            <th className="px-3 py-2 font-medium">accepted</th>
            <th className="px-3 py-2 font-medium">rejected</th>
            <th className="px-3 py-2 font-medium">aggregated</th>
            <th className="px-3 py-2 font-medium">single</th>
            <th className="px-3 py-2 font-medium">val loss</th>
            <th className="px-3 py-2 font-medium">seconds</th>
            <th className="px-3 py-2 font-medium">model</th>
          </tr>
        </thead>
        <tbody>
          {summaries.map((row) => (
            <tr key={row.round} className="border-b border-ink-700/40 last:border-0">
              <td className="px-4 py-2 mono text-mist-100">{row.round}</td>
              <td className="px-3 py-2">
                <Badge tone={row.status === "completed" ? "emerald" : row.status === "failed" ? "red" : "amber"}>{row.status}</Badge>
              </td>
              <td className="px-3 py-2 mono text-mist-300">{row.selected.length}</td>
              <td className="px-3 py-2 mono text-signal-emerald">{row.accepted.length}</td>
              <td className="px-3 py-2 mono text-signal-red">{Object.keys(row.rejected ?? {}).length}</td>
              <td className="px-3 py-2 mono text-mist-300">{row.aggregated ? "yes" : "no"}</td>
              <td className="px-3 py-2 mono text-mist-300">{row.single_client ? "yes" : "no"}</td>
              <td className="px-3 py-2 mono text-mist-200">{formatNumber(row.weighted_val_loss, 6)}</td>
              <td className="px-3 py-2 mono text-mist-300">{formatNumber(row.seconds, 1)}</td>
              <td className="px-3 py-2 mono text-signal-violet">{row.model_version || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

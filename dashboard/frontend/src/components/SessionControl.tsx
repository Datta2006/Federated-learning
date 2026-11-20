import { useState } from "react";
import { CheckCircle2, CircleAlert, Loader2, Play, Pause, Square } from "lucide-react";
import { useAction } from "../hooks/useAction";
import type { CommandResponse, SessionState } from "../types";
import { StatusPill } from "./ui";

const ACTIVE = new Set(["starting", "waiting", "running", "paused", "stopping"]);

export function SessionControl({
  session,
  onDone,
}: {
  session: SessionState | null;
  onDone: () => void;
}) {
  const { run, pending, error, result, resetError } = useAction<CommandResponse>();
  const [rounds, setRounds] = useState(3);
  const [minWorkers, setMinWorkers] = useState(2);
  const [simWorkers, setSimWorkers] = useState(2);
  const [deadline, setDeadline] = useState(120);
  const [localEpochs, setLocalEpochs] = useState(1);

  const state = session?.state ?? "idle";
  const active = ACTIVE.has(state);
  const success = result?.ok && !error;

  const send = async (action: "start" | "pause" | "resume" | "stop") => {
    resetError();
    const payload =
      action === "start"
        ? {
            action,
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
            },
          }
        : { action };
    const response = await run("/api/control/session", payload);
    if (response?.ok) onDone();
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StatusPill status={state} pulse={state === "running" || state === "starting"} />
          {session?.stale ? (
            <span className="chip border-warn/30 bg-warn-soft text-warn-text">
              state is stale
            </span>
          ) : null}
          {session?.session_id ? (
            <span className="mono text-2xs text-ink-600">{session.session_id}</span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {!active ? (
            <button
              className="btn btn-primary"
              disabled={pending}
              onClick={() => void send("start")}
              type="button"
            >
              {pending ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
              Start session
            </button>
          ) : null}
          {active && state !== "paused" && state !== "stopping" ? (
            <button
              className="btn"
              disabled={pending}
              onClick={() => void send("pause")}
              type="button"
            >
              <Pause size={13} /> Pause
            </button>
          ) : null}
          {state === "paused" ? (
            <button
              className="btn btn-primary"
              disabled={pending}
              onClick={() => void send("resume")}
              type="button"
            >
              <Play size={13} /> Resume
            </button>
          ) : null}
          {active ? (
            <button
              className="btn btn-danger"
              disabled={pending}
              onClick={() => void send("stop")}
              type="button"
            >
              <Square size={13} /> Stop
            </button>
          ) : null}
        </div>
      </div>

      {!active ? (
        <div className="grid grid-cols-2 gap-2 rounded border border-line bg-inset p-3 sm:grid-cols-5">
          <label className="block">
            <span className="label">Rounds</span>
            <input
              className="input mt-1"
              type="number"
              min={1}
              max={50}
              value={rounds}
              onChange={(event) => setRounds(Number(event.target.value))}
            />
          </label>
          <label className="block">
            <span className="label">Min workers</span>
            <input
              className="input mt-1"
              type="number"
              min={1}
              max={50}
              value={minWorkers}
              onChange={(event) => setMinWorkers(Number(event.target.value))}
            />
          </label>
          <label className="block">
            <span className="label">Launch sims</span>
            <input
              className="input mt-1"
              type="number"
              min={0}
              max={20}
              value={simWorkers}
              onChange={(event) => setSimWorkers(Number(event.target.value))}
            />
          </label>
          <label className="block">
            <span className="label">Local epochs</span>
            <input
              className="input mt-1"
              type="number"
              min={1}
              max={10}
              value={localEpochs}
              onChange={(event) => setLocalEpochs(Number(event.target.value))}
            />
          </label>
          <label className="block">
            <span className="label">Deadline (s)</span>
            <input
              className="input mt-1"
              type="number"
              min={10}
              max={3600}
              value={deadline}
              onChange={(event) => setDeadline(Number(event.target.value))}
            />
          </label>
        </div>
      ) : null}

      {pending ? (
        <p className="flex items-center gap-2 text-[11px] text-ink-400">
          <Loader2 size={12} className="animate-spin text-accent" />
          Publishing command and waiting for the coordinator to acknowledge it…
        </p>
      ) : null}

      {error ? (
        <div className="flex items-start gap-2 rounded border border-bad/35 bg-bad-soft px-3 py-2 text-[11px] text-bad-text">
          <CircleAlert size={14} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-medium">Command failed</div>
            <div className="mt-0.5 leading-relaxed text-bad-text/80">{error}</div>
          </div>
        </div>
      ) : null}

      {success && !pending ? (
        <p className="flex items-center gap-2 text-[11px] text-ok-text">
          <CheckCircle2 size={13} />
          Coordinator acknowledged <span className="mono">{result?.command}</span>
          {result?.request_id ? (
            <span className="mono text-ink-600">· {result.request_id.slice(0, 8)}</span>
          ) : null}
          {result?.idempotent_replay ? (
            <span className="text-ink-600">· replay of an earlier accepted command</span>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

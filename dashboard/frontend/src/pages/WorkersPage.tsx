import { useMemo, useState } from "react";
import {
  Activity,
  Cpu,
  Play,
  RefreshCw,
  Server,
  Square,
  Trash2,
  Users,
} from "lucide-react";
import { useApi } from "../lib/useApi";
import { useAction } from "../hooks/useAction";
import { formatInteger, formatNumber, relativeTime } from "../lib/format";
import type { CommandResponse, LogPayload, WorkerView, WorkersPayload } from "../types";
import {
  Badge,
  Bar,
  EmptyState,
  ErrorState,
  Kpi,
  PageSkeleton,
  Panel,
  PanelHeader,
  StatusBadge,
} from "../components/ui";

export function WorkersPage() {
  const { data, error, loading, lastUpdated, refresh } = useApi<WorkersPayload>(
    "/api/workers",
    2500,
  );
  const [count, setCount] = useState(2);
  const [role, setRole] = useState<"training" | "inference">("training");
  const [dummy, setDummy] = useState(false);
  const [prefix, setPrefix] = useState("sim");
  const [logName, setLogName] = useState<string | null>(null);
  const launch = useAction<CommandResponse>();
  const stop = useAction<CommandResponse>();
  const stack = useAction<CommandResponse>();

  const logs = useApi<LogPayload>(
    logName ? `/api/logs?name=${encodeURIComponent(logName)}&lines=200` : "/api/logs?name=coordinator&lines=1",
    3000,
  );

  const processNames = useMemo(() => {
    const names = new Set<string>(["coordinator", "broker"]);
    data?.processes.forEach((item) => names.add(item.name));
    return [...names].sort();
  }, [data]);

  const stopWorker = async (worker: WorkerView) => {
    await stop.run("/api/workers/stop", { ids: [worker.id] });
    refresh();
  };

  if (loading && !data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <PageSkeleton rows={2} />
      </div>
    );
  }
  if (error && !data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <ErrorState message={error} onRetry={refresh} />
      </div>
    );
  }
  if (!data) return null;

  const { counts, workers } = data;
  const actionError = launch.error ?? stop.error ?? stack.error;

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 pb-10 pt-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Registered workers" value={formatInteger(counts.total)} icon={<Users size={15} />} tone="blue" hint="Streams seen this API session" />
        <Kpi label="Online" value={formatInteger(counts.online)} icon={<Activity size={15} />} tone="emerald" hint={`${counts.offline} expired / offline`} />
        <Kpi label="Selectable" value={formatInteger(counts.available)} icon={<Cpu size={15} />} tone="violet" hint="Online training workers eligible for selection" />
        <Kpi label="Busy" value={formatInteger(counts.busy)} icon={<Server size={15} />} tone="amber" hint="Training or uploading right now" />
      </div>

      {actionError ? <ErrorState title="Action failed" message={actionError} /> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            title="Launch simulated workers"
            subtitle="Simulated workers run real training on disjoint date shards of the training years. Dummy workers are protocol-only."
            icon={<Play size={15} />}
          />
          <div className="grid gap-3 px-5 pb-5 pt-1 sm:grid-cols-2">
            <label className="block">
              <span className="label">Worker count</span>
              <input
                className="input mt-1"
                type="number"
                min={1}
                max={200}
                value={count}
                onChange={(event) => setCount(Math.max(1, Math.min(200, Number(event.target.value) || 1)))}
              />
            </label>
            <label className="block">
              <span className="label">Role</span>
              <select className="input mt-1" value={role} onChange={(event) => setRole(event.target.value as typeof role)}>
                <option value="training">training</option>
                <option value="inference">inference (no aggregation)</option>
              </select>
            </label>
            <label className="block">
              <span className="label">ID prefix</span>
              <input className="input mt-1" value={prefix} onChange={(event) => setPrefix(event.target.value)} />
            </label>
            <label className="mt-6 flex items-center gap-2 text-[12px] text-mist-300">
              <input type="checkbox" checked={dummy} onChange={(event) => setDummy(event.target.checked)} />
              Dummy protocol workers (no TensorFlow)
            </label>
            <div className="sm:col-span-2 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={launch.pending}
                onClick={async () => {
                  await launch.run("/api/workers/launch", {
                    count,
                    role,
                    simulation: true,
                    dummy,
                    prefix: prefix.trim() || "sim",
                  });
                  refresh();
                }}
              >
                <Play size={13} /> Launch {count}
              </button>
              <button
                type="button"
                className="btn"
                disabled={stop.pending}
                onClick={async () => {
                  await stop.run("/api/workers/stop", {});
                  refresh();
                }}
              >
                <Square size={13} /> Stop all workers
              </button>
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Backend stack"
            subtitle="Broker and long-lived control coordinator launched as managed processes."
            icon={<Server size={15} />}
          />
          <div className="space-y-3 px-5 pb-5 pt-1">
            <div className="flex flex-wrap items-center gap-2 text-[12px]">
              <Badge tone={data.broker.reachable ? "emerald" : "red"}>
                broker {data.broker.host}:{data.broker.port} {data.broker.reachable ? "reachable" : "down"}
              </Badge>
              <Badge tone={data.coordinator?.running ? "emerald" : "red"}>
                coordinator {data.coordinator?.running ? `pid ${data.coordinator.pid}` : "stopped"}
              </Badge>
              <Badge tone={data.broker.owned ? "blue" : "mist"}>
                {data.broker.owned ? "owned by dashboard" : "external"}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="btn btn-primary"
                disabled={stack.pending}
                onClick={async () => {
                  await stack.run("/api/processes/start", { name: "stack" });
                  refresh();
                }}
              >
                <Play size={13} /> Start broker + coordinator
              </button>
              <button
                type="button"
                className="btn"
                disabled={stack.pending}
                onClick={async () => {
                  await stack.run("/api/processes/stop", { name: "all" });
                  refresh();
                }}
              >
                <Square size={13} /> Stop stack
              </button>
              <button type="button" className="btn" onClick={refresh}>
                <RefreshCw size={13} /> Refresh
              </button>
            </div>
            <p className="text-[11px] text-mist-500">
              Runtime logs: <span className="mono text-mist-300">{data.crashes.length} crash record(s)</span> ·
              last updated {relativeTime(lastUpdated?.toISOString() ?? null)}
            </p>
            {data.crashes.length > 0 ? (
              <div className="space-y-1.5">
                {data.crashes.slice(-3).map((crash) => (
                  <div key={`${crash.name}-${crash.at}`} className="rounded-md border border-signal-red/30 bg-signal-redDim/20 px-2.5 py-2 text-[11px]">
                    <span className="font-semibold text-signal-red">{crash.name}</span> exited with code{" "}
                    {crash.exit_code ?? "—"} at {crash.at}
                    {crash.log_tail.length > 0 ? (
                      <pre className="mono mt-1 max-h-24 overflow-auto whitespace-pre-wrap text-[10px] text-mist-400">
                        {crash.log_tail.slice(-4).join("\n")}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </Panel>
      </div>

      <Panel className="overflow-hidden">
        <PanelHeader
          title="Workers"
          subtitle="Live registration, heartbeat expiry, shard assignment, and training state."
          icon={<Users size={15} />}
          action={<button type="button" className="btn" onClick={refresh}><RefreshCw size={13} /> Refresh</button>}
        />
        {workers.length === 0 ? (
          <EmptyState
            title="No workers registered"
            message="Launch simulated workers or start a node with --dynamic. Workers appear here after their retained registration and first heartbeat."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead className="border-y border-ink-700/70 bg-ink-800/40 text-mist-500">
                <tr>
                  <th className="px-4 py-2 font-medium">worker</th>
                  <th className="px-3 py-2 font-medium">role</th>
                  <th className="px-3 py-2 font-medium">status</th>
                  <th className="px-3 py-2 font-medium">state</th>
                  <th className="px-3 py-2 font-medium">shard</th>
                  <th className="px-3 py-2 font-medium">samples</th>
                  <th className="px-3 py-2 font-medium">round</th>
                  <th className="px-3 py-2 font-medium">progress</th>
                  <th className="px-3 py-2 font-medium">last seen</th>
                  <th className="px-3 py-2 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {workers.map((worker) => (
                  <tr key={worker.id} className="border-b border-ink-700/40 last:border-0">
                    <td className="px-4 py-2.5">
                      <div className="mono font-semibold text-mist-100">{worker.id}</div>
                      <div className="text-[10px] text-mist-500">{worker.dataset}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge tone={worker.role === "training" ? "violet" : "blue"}>{worker.role}</Badge>
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={worker.status} />
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="text-mist-200">{worker.state ?? "—"}</div>
                      {worker.phase ? <div className="text-[10px] text-mist-500">{worker.phase}</div> : null}
                    </td>
                    <td className="px-3 py-2.5 mono text-mist-300">
                      {worker.shard_index === null
                        ? "—"
                        : `${worker.shard_index + 1}/${worker.shard_count ?? "?"}`}
                    </td>
                    <td className="px-3 py-2.5 mono text-mist-300">
                      {formatInteger(worker.n_samples)}
                      <span className="text-mist-500"> / {formatInteger(worker.n_val)}</span>
                    </td>
                    <td className="px-3 py-2.5 mono text-mist-300">{worker.current_round ?? "—"}</td>
                    <td className="px-3 py-2.5 w-28">
                      {worker.progress === null ? (
                        <span className="text-mist-500">—</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <Bar value={worker.progress} max={1} tone="violet" height={4} />
                          <span className="mono text-[10px] text-mist-400">
                            {formatNumber(worker.progress * 100, 0)}%
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 mono text-mist-400">{relativeTime(worker.last_seen)}</td>
                    <td className="px-3 py-2.5 text-right">
                      <div className="flex justify-end gap-1">
                        <button type="button" className="btn px-2 py-1" onClick={() => setLogName(worker.id)}>
                          logs
                        </button>
                        <button
                          type="button"
                          className="btn px-2 py-1"
                          disabled={stop.pending}
                          onClick={() => void stopWorker(worker)}
                          title="Stop this managed worker process"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel>
        <PanelHeader
          title="Process log"
          subtitle={logName ? `Tail of ${logName}` : "Select a worker or open the coordinator log."}
          icon={<Server size={15} />}
          action={
            <div className="flex items-center gap-2">
              <select
                className="input py-1"
                value={logName ?? ""}
                onChange={(event) => setLogName(event.target.value || null)}
              >
                <option value="">select process…</option>
                {processNames.map((name) => (
                  <option key={name} value={name}>{name}</option>
                ))}
              </select>
              <button type="button" className="btn" onClick={() => logs.refresh()}><RefreshCw size={13} /></button>
            </div>
          }
        />
        <div className="px-5 pb-5 pt-1">
          {!logName ? (
            <p className="py-6 text-center text-[12px] text-mist-500">Choose a process to view its stdout/stderr tail.</p>
          ) : logs.error ? (
            <p className="py-4 text-[12px] text-signal-red">{logs.error}</p>
          ) : (
            <pre className="mono max-h-72 overflow-auto whitespace-pre-wrap rounded-lg border border-ink-700 bg-ink-950/70 p-3 text-[10.5px] leading-relaxed text-mist-300">
              {(logs.data?.lines ?? []).join("\n") || "Waiting for output…"}
            </pre>
          )}
        </div>
      </Panel>
    </div>
  );
}

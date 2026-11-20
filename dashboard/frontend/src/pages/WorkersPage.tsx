import { useState } from "react";
import { Cpu, Layers, Play, Square, TriangleAlert } from "lucide-react";
import { useApi } from "../lib/useApi";
import { useAction } from "../hooks/useAction";
import type { CommandResponse, WorkersPayload } from "../types";
import {
  Badge,
  DataRow,
  Dot,
  EmptyState,
  Metric,
  Panel,
  PanelHead,
  PageTitle,
  Skeleton,
  StatusPill,
} from "../components/ui";
import { formatInteger, formatPercent, relativeTime } from "../lib/format";

export function WorkersPage() {
  const { data, error, loading, refresh } = useApi<WorkersPayload>("/api/workers", 4000);
  const action = useAction<CommandResponse>();
  const [count, setCount] = useState(2);
  const [role, setRole] = useState<"training" | "inference">("training");

  const launch = async () => {
    const response = await action.run("/api/workers/launch", {
      count,
      role,
      simulation: true,
      dummy: false,
      prefix: "sim",
    });
    if (response) refresh();
  };

  const stopAll = async () => {
    const response = await action.run("/api/workers/stop", {});
    if (response) refresh();
  };

  const workers = data?.workers ?? [];
  const counts = data?.counts;
  const processes = data?.processes ?? [];

  return (
    <div className="space-y-5">
      <PageTitle
        title="Workers"
        description="Dynamic workers that registered over MQTT, the legacy five-node topology, and the local processes the dashboard launched."
        meta={
          counts ? (
            <Badge tone={counts.online > 0 ? "ok" : "bad"}>
              <Dot tone={counts.online > 0 ? "ok" : "bad"} pulse={counts.online > 0} />
              {counts.online}/{counts.total} online
            </Badge>
          ) : null
        }
      />

      <div className="grid gap-4 xl:grid-cols-4">
        <Panel className="xl:col-span-3">
          <PanelHead
            title="Worker roster"
            subtitle="Registration comes from retained MQTT metadata; heartbeat age determines online status."
            icon={<Cpu size={14} />}
            action={
              <div className="flex items-center gap-1.5">
                <input
                  className="input w-16 py-1"
                  type="number"
                  min={1}
                  max={20}
                  value={count}
                  onChange={(event) => setCount(Number(event.target.value))}
                  aria-label="Worker count"
                />
                <select
                  className="input w-28 py-1"
                  value={role}
                  onChange={(event) =>
                    setRole(event.target.value as "training" | "inference")
                  }
                  aria-label="Worker role"
                >
                  <option value="training">training</option>
                  <option value="inference">inference</option>
                </select>
                <button
                  className="btn btn-primary"
                  onClick={() => void launch()}
                  disabled={action.pending}
                  type="button"
                >
                  <Play size={12} /> Launch
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => void stopAll()}
                  disabled={action.pending}
                  type="button"
                >
                  <Square size={12} /> Stop all
                </button>
              </div>
            }
          />
          {action.error ? (
            <p className="border-b border-line px-4 py-2 text-[11px] text-bad-text">
              {action.error}
            </p>
          ) : null}
          {loading && !data ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-full" />
              <Skeleton className="h-5 w-3/4" />
            </div>
          ) : workers.length === 0 ? (
            <EmptyState
              icon={<Cpu size={15} />}
              title="No workers registered"
              message="Launch simulation workers or start a remote node. Registration is retained on the broker, but online status requires a fresh heartbeat."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                    <th className="px-4 py-2 font-medium">Worker</th>
                    <th className="px-4 py-2 font-medium">Role</th>
                    <th className="px-4 py-2 font-medium">Dataset / shard</th>
                    <th className="px-4 py-2 text-right font-medium">Samples</th>
                    <th className="px-4 py-2 font-medium">State</th>
                    <th className="px-4 py-2 text-right font-medium">Round</th>
                    <th className="px-4 py-2 text-right font-medium">Progress</th>
                    <th className="px-4 py-2 text-right font-medium">Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {workers.map((worker) => (
                    <tr
                      key={worker.id}
                      className={`border-b border-line/60 last:border-0 ${
                        worker.selected ? "bg-accent-dim/40" : ""
                      }`}
                    >
                      <td className="px-4 py-2">
                        <span className="mono text-ink-200">{worker.id}</span>
                        <div className="flex items-center gap-1.5">
                          <StatusPill status={worker.status} label={worker.status} />
                          {worker.selected ? <Badge tone="accent">selected</Badge> : null}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-ink-400">{worker.role}</td>
                      <td className="px-4 py-2 text-ink-400">
                        {worker.dataset}
                        <span className="mono ml-1 text-ink-600">
                          {worker.shard_index != null
                            ? `${worker.shard_index + 1}/${worker.shard_count ?? "?"}`
                            : ""}
                        </span>
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-300">
                        {formatInteger(worker.n_samples)}
                      </td>
                      <td className="px-4 py-2 text-ink-300">
                        {worker.state ?? "—"}
                        {worker.phase ? (
                          <div className="text-2xs text-ink-600">{worker.phase}</div>
                        ) : null}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {worker.current_round ?? "—"}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {worker.progress != null ? formatPercent(worker.progress) : "—"}
                      </td>
                      <td className="px-4 py-2 text-right text-ink-500">
                        {relativeTime(worker.last_seen)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHead title="Fleet summary" icon={<Layers size={14} />} />
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-b border-t border-line bg-line">
              <Metric label="Online" value={counts?.online ?? "—"} tone={counts?.online ? "ok" : "neutral"} />
              <Metric label="Offline" value={counts?.offline ?? "—"} />
              <Metric label="Selectable" value={counts?.available ?? "—"} tone="accent" />
              <Metric label="Busy" value={counts?.busy ?? "—"} />
            </div>
          </Panel>

          <Panel>
            <PanelHead title="Legacy nodes" subtitle="Configured Stage-4 topology" />
            <div className="max-h-72 overflow-y-auto p-4">
              {(data?.nodes ?? []).length === 0 ? (
                <p className="text-[11px] text-ink-500">No configured nodes.</p>
              ) : (
                data?.nodes.map((node) => (
                  <DataRow
                    key={node.id}
                    label={
                      <span className="inline-flex items-center gap-1.5">
                        <Dot
                          tone={
                            node.status === "online"
                              ? "ok"
                              : node.status === "stale"
                                ? "warn"
                                : node.status === "offline"
                                  ? "bad"
                                  : "neutral"
                          }
                        />
                        {node.id}
                        <span className="text-2xs text-ink-600">{node.role}</span>
                      </span>
                    }
                    value={node.status}
                    mono={false}
                  />
                ))
              )}
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel>
          <PanelHead title="Managed processes" subtitle="Launched by this dashboard instance" />
          {processes.length === 0 ? (
            <EmptyState title="No local processes" message="The dashboard can launch the broker, coordinator, and simulation workers here." />
          ) : (
            <div className="p-4">
              {processes.map((process) => (
                <DataRow
                  key={process.name}
                  label={
                    <span className="inline-flex items-center gap-1.5">
                      <Dot tone={process.running ? "ok" : "bad"} />
                      {process.name}
                      <span className="text-2xs text-ink-600">{process.kind}</span>
                    </span>
                  }
                  value={process.running ? `PID ${process.pid}` : "stopped"}
                />
              ))}
            </div>
          )}
        </Panel>

        <Panel>
          <PanelHead title="Crashes" subtitle="Recent non-zero exits captured by the process manager" icon={<TriangleAlert size={14} />} />
          {(data?.crashes ?? []).length === 0 ? (
            <div className="px-4 py-8 text-center text-[11px] text-ink-500">No crashes recorded.</div>
          ) : (
            <div className="max-h-64 overflow-y-auto p-4">
              {data?.crashes.map((crash) => (
                <div key={`${crash.name}-${crash.at}`} className="border-b border-line/60 py-2 last:border-0">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="mono text-ink-200">{crash.name}</span>
                    <span className="text-bad-text">exit {crash.exit_code}</span>
                  </div>
                  <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-inset p-2 text-2xs text-ink-500">
                    {crash.log_tail.slice(-4).join("\n")}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {error ? <p className="text-[11px] text-bad-text">{error}</p> : null}
    </div>
  );
}

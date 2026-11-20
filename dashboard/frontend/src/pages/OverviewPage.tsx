import { useMemo } from "react";
import {
  Boxes,
  Cpu,
  Gauge,
  Network,
  Radio,
  ServerCog,
  Timer,
} from "lucide-react";
import { useCommandCenter } from "../hooks/useCommandCenter";
import { pendingStages } from "../lib/stages";
import {
  formatBytes,
  formatDateTime,
  formatInteger,
  formatNumber,
  relativeTime,
  seconds,
} from "../lib/format";
import {
  Badge,
  DataRow,
  Dot,
  EmptyState,
  ErrorState,
  Metric,
  Panel,
  PanelHead,
  PageTitle,
  Skeleton,
  StatusPill,
} from "../components/ui";
import { StageRail } from "../components/StageRail";
import { ActivityFeed } from "../components/ActivityFeed";
import { SessionControl } from "../components/SessionControl";

export function OverviewPage() {
  const { status, error, loading, lastUpdated, socket, retryInMs, refresh } =
    useCommandCenter();

  const session = status?.session_view ?? null;
  const round = status?.current_round ?? null;
  const counts = status?.worker_counts;
  const infra = status?.infrastructure;
  const latest = status?.latest_model ?? null;
  const coordinator = status?.processes?.coordinator ?? null;
  const stages = round?.stages ?? pendingStages();

  const contributions = useMemo(() => {
    const rows = round?.contributions ?? [];
    if (rows.length > 0) return rows;
    return (round?.accepted ?? []).map((node) => ({
      node_id: node,
      n_samples: 0,
      n_val: 0,
      val_loss: null,
      weight: null,
    }));
  }, [round]);

  if (error && !status) {
    return (
      <div className="space-y-5">
        <PageTitle
          title="Operations"
          description="Live state of the AirFed coordinator, workers, and federated rounds."
        />
        <ErrorState message={error} onRetry={refresh} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageTitle
        title="Operations"
        description="One page for the whole run: what the coordinator is doing, which workers are live, and where the current round actually is."
        meta={
          <>
            <Badge tone={status?.broker.connected ? "ok" : "bad"}>
              <Dot
                tone={status?.broker.connected ? "ok" : "bad"}
                pulse={status?.broker.connected}
              />
              broker {status?.broker.connected ? "connected" : "unreachable"}
            </Badge>
            <Badge tone={socket === "open" ? "ok" : socket === "connecting" ? "warn" : "bad"}>
              stream {socket}
              {socket !== "open" && retryInMs
                ? ` · retry ${Math.round(retryInMs / 1000)}s`
                : ""}
            </Badge>
            <span className="mono text-2xs text-ink-600">
              synced {lastUpdated ? relativeTime(lastUpdated.toISOString()) : "—"}
            </span>
          </>
        }
      />

      {loading && !status ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-56 lg:col-span-2" />
          <Skeleton className="h-56" />
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHead
            title="Session control"
            subtitle={
              session
                ? (session.message ?? "Coordinator state")
                : "No session state has been published yet"
            }
            icon={<Network size={14} />}
            action={
              session ? (
                <span className="mono text-2xs text-ink-600">
                  {session.completed_rounds}
                  {session.total_rounds ? `/${session.total_rounds}` : ""} rounds
                </span>
              ) : null
            }
          />
          <div className="space-y-4 p-4">
            <SessionControl session={session} onDone={refresh} />

            <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-4">
              <Metric
                label="Elapsed"
                value={session?.elapsed_sec != null ? seconds(session.elapsed_sec) : "—"}
                hint={session?.started_utc ? `started ${formatDateTime(session.started_utc)}` : "not started"}
                tone={session?.active ? "accent" : "neutral"}
              />
              <Metric
                label="Coordinator round"
                value={round?.round ?? session?.round ?? "—"}
                hint={round ? round.phase_label : "no round observed"}
              />
              <Metric
                label="Heartbeat age"
                value={session?.age_sec != null ? `${session.age_sec.toFixed(1)}s` : "—"}
                hint={session?.stale ? "stale — coordinator may be gone" : "coordinator publishes every 5s"}
                tone={session?.stale ? "bad" : "neutral"}
              />
              <Metric
                label="Model"
                value={session?.latest_model_version ?? latest?.model_version ?? "—"}
                hint={latest?.created_utc ? formatDateTime(latest.created_utc) : "registry not written"}
                tone="accent"
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="label">Round stage</span>
                {round?.single_client ? (
                  <Badge tone="warn">single-client round — not cross-client FedAvg</Badge>
                ) : round?.aggregated ? (
                  <Badge tone="ok">FedAvg aggregated</Badge>
                ) : (
                  <span className="text-2xs text-ink-600">
                    {round ? `source ${round.source}` : "no authoritative round message"}
                  </span>
                )}
              </div>
              <StageRail stages={stages} timings={round?.stage_times} dense />
            </div>

            {round ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded border border-line bg-inset p-3">
                  <div className="label">Clients</div>
                  <div className="mono mt-1 text-[12px] text-ink-200">
                    {round.received}/{round.selected.length} reported
                  </div>
                  <div className="mt-1 truncate text-2xs text-ink-600">
                    {round.selected.length ? round.selected.join(", ") : "none selected"}
                  </div>
                </div>
                <div className="rounded border border-line bg-inset p-3">
                  <div className="label">Samples aggregated</div>
                  <div className="mono mt-1 text-[12px] text-ink-200">
                    {formatInteger(round.accepted_samples)}
                  </div>
                  <div className="mt-1 text-2xs text-ink-600">
                    {round.contributions?.length ?? 0} contribution(s)
                  </div>
                </div>
                <div className="rounded border border-line bg-inset p-3">
                  <div className="label">Aggregation</div>
                  <div className="mono mt-1 text-[12px] text-ink-200">
                    {round.aggregation_seconds != null
                      ? seconds(round.aggregation_seconds)
                      : "—"}
                  </div>
                  <div className="mt-1 text-2xs text-ink-600">
                    {formatBytes(round.bytes_up)} up · {formatBytes(round.bytes_down)} down
                  </div>
                </div>
              </div>
            ) : (
              <EmptyState
                title="No round telemetry yet"
                message="Round stages appear only after the coordinator publishes progress. Starting a session with at least one online worker will populate this rail."
              />
            )}
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHead title="Infrastructure" icon={<ServerCog size={14} />} />
            <div className="p-4">
              <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line">
                <Metric
                  label="Workers"
                  value={counts ? `${counts.online}/${counts.total}` : "—"}
                  hint={counts ? `${counts.available} selectable · ${counts.busy} busy` : "no registration"}
                  tone={counts && counts.online > 0 ? "ok" : "neutral"}
                />
                <Metric
                  label="MQTT quiet"
                  value={
                    infra?.broker.last_message_age_sec != null
                      ? `${infra.broker.last_message_age_sec.toFixed(0)}s`
                      : "—"
                  }
                  hint={infra?.observer.quiet ? "observer has seen no traffic" : "observer receiving"}
                  tone={infra?.observer.quiet ? "warn" : "neutral"}
                />
              </div>
              <div className="mt-3">
                <DataRow label="coordinator" value={coordinator?.running ? `PID ${coordinator.pid}` : "not managed"} />
                <DataRow
                  label="observer events"
                  value={formatInteger(status?.observer.events)}
                />
                <DataRow
                  label="registry"
                  value={status?.registry.available ? `${status.registry.round_count ?? 0} rounds` : "unavailable"}
                />
                <DataRow label="dataset" value={status?.system.dataset ?? "—"} mono={false} />
                <DataRow label="last broker msg" value={status?.broker.last_message_at ? relativeTime(status.broker.last_message_at) : "—"} mono={false} />
              </div>
              {infra && !infra.healthy ? (
                <p className="mt-3 rounded border border-warn/30 bg-warn-soft px-2.5 py-2 text-[11px] leading-relaxed text-warn-text">
                  {infra.broker.connected
                    ? "The observer is connected but session state is stale. Check that the coordinator runs with --control."
                    : `Broker unreachable: ${infra.broker.last_error ?? "no connection"}`}
                </p>
              ) : null}
            </div>
          </Panel>

          <Panel>
            <PanelHead
              title="Registered model"
              subtitle={latest?.model_version ? `round ${latest.round}` : "No model record"}
              icon={<Boxes size={14} />}
            />
            <div className="p-4">
              {latest ? (
                <>
                  <div className="flex items-center justify-between">
                    <span className="mono text-[16px] text-accent-text">
                      {latest.model_version ?? "—"}
                    </span>
                    <StatusPill status={latest.has_weights ? "complete" : "skipped"} label={latest.has_weights ? "weights on disk" : "metadata only"} />
                  </div>
                  <div className="mt-3">
                    <DataRow label="parameters" value={formatInteger(latest.parameters)} />
                    <DataRow label="weighted val loss" value={formatNumber(latest.weighted_val_loss, 6)} />
                    <DataRow label="samples / val" value={`${formatInteger(latest.n_samples)} / ${formatInteger(latest.n_val)}`} />
                    <DataRow label="created" value={formatDateTime(latest.created_utc)} mono={false} />
                  </div>
                </>
              ) : (
                <p className="text-[11px] text-ink-500">
                  The registry has no latest.json yet. A successful aggregation writes one.
                </p>
              )}
            </div>
          </Panel>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHead
            title="Round contributions"
            subtitle="Sample counts and FedAvg weights the coordinator actually received"
            icon={<Gauge size={14} />}
          />
          {contributions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[11px]">
                <thead>
                  <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                    <th className="px-4 py-2 font-medium">Worker</th>
                    <th className="px-4 py-2 text-right font-medium">Samples</th>
                    <th className="px-4 py-2 text-right font-medium">Val samples</th>
                    <th className="px-4 py-2 text-right font-medium">Val loss</th>
                    <th className="px-4 py-2 text-right font-medium">Weight</th>
                  </tr>
                </thead>
                <tbody className="mono">
                  {contributions.map((row) => (
                    <tr key={row.node_id} className="border-b border-line/60 last:border-0">
                      <td className="px-4 py-2 text-ink-200">{row.node_id}</td>
                      <td className="px-4 py-2 text-right text-ink-300">{formatInteger(row.n_samples)}</td>
                      <td className="px-4 py-2 text-right text-ink-400">{formatInteger(row.n_val)}</td>
                      <td className="px-4 py-2 text-right text-ink-400">{formatNumber(row.val_loss, 6)}</td>
                      <td className="px-4 py-2 text-right text-accent-text">
                        {row.weight != null ? row.weight.toFixed(3) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              icon={<Cpu size={15} />}
              title="No accepted updates in this round"
              message="Contributions appear after the coordinator validates uploaded weights. No values are inferred from selection alone."
            />
          )}
        </Panel>

        <Panel>
          <PanelHead
            title="Live activity"
            subtitle="Normalized MQTT events, newest first"
            icon={<Radio size={14} />}
          />
          <ActivityFeed items={status?.activity ?? []} limit={9} />
        </Panel>
      </div>

      <div className="flex flex-wrap items-center gap-4 border-t border-line pt-3 text-2xs text-ink-600">
        <span className="inline-flex items-center gap-1.5">
          <Timer size={11} /> round staleness {status?.observer.round_stale_after_sec ?? "—"}s
        </span>
        <span>source: {status?.data_source ?? "unavailable"}</span>
        <span>{status?.provenance.note}</span>
      </div>
    </div>
  );
}

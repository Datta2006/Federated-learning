import { useMemo } from "react";
import { GitMerge, History, ListTree, Network, Users } from "lucide-react";
import { useCommandCenter } from "../hooks/useCommandCenter";
import { useApi } from "../lib/useApi";
import { pendingStages } from "../lib/stages";
import type { GatewayFlPayload, RoundsPayload } from "../types";
import {
  Badge,
  DataRow,
  EmptyState,
  Metric,
  Panel,
  PanelHead,
  PageTitle,
  Sparkline,
  StatusPill,
} from "../components/ui";
import { StageRail } from "../components/StageRail";
import { formatBytes, formatInteger, formatNumber, formatTime, seconds } from "../lib/format";

export function FederatedPage() {
  const { status } = useCommandCenter();
  const { data: rounds } = useApi<RoundsPayload>("/api/rounds?limit=60", 5000);
  const { data: gatewayFl } = useApi<GatewayFlPayload>("/api/fl/gateways", 4000);
  const round = status?.current_round ?? null;
  const session = status?.session_view ?? null;
  const summaries = status?.round_summaries ?? [];

  const history = rounds?.history ?? [];
  const lossSeries = useMemo(
    () => [...history].reverse().map((row) => row.weighted_val_loss),
    [history],
  );

  return (
    <div className="space-y-5">
      <PageTitle
        title="Federated rounds"
        description="The coordinator's round DAG, rendered from its own progress and summary messages. Selection is not progress; only acknowledged updates advance a stage."
        meta={
          round ? (
            <>
              <Badge tone={round.is_live ? "accent" : "neutral"}>
                round {round.round} · {round.is_live ? "live" : round.status ?? round.phase}
              </Badge>
              {round.single_client ? <Badge tone="warn">single-client</Badge> : null}
            </>
          ) : (
            <Badge tone="neutral">no live round</Badge>
          )
        }
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHead
            title={round ? `Round ${round.round}` : "Current round"}
            subtitle={
              round
                ? `${round.phase_label} · ${round.selected.length} selected · ${round.received} reported`
                : "No coordinator round message has been observed"
            }
            icon={<GitMerge size={14} />}
            action={
              round ? (
                <StatusPill status={round.status ?? round.phase} />
              ) : null
            }
          />
          <div className="space-y-4 p-4">
            <StageRail stages={round?.stages ?? pendingStages()} timings={round?.stage_times} />

            <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line sm:grid-cols-4">
              <Metric
                label="Round time"
                value={round?.seconds != null ? seconds(round.seconds) : round?.idle_seconds != null ? `${round.idle_seconds.toFixed(0)}s idle` : "—"}
              />
              <Metric
                label="Aggregation"
                value={round?.aggregation_seconds != null ? seconds(round.aggregation_seconds) : "—"}
                hint={round?.single_client ? "copied single update" : "sample-weighted FedAvg"}
              />
              <Metric label="Samples" value={formatInteger(round?.accepted_samples)} />
              <Metric
                label="Val loss"
                value={formatNumber(round?.weighted_val_loss, 6)}
                hint="of the model workers evaluated"
              />
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded border border-line">
                <div className="border-b border-line px-3 py-2 text-2xs uppercase tracking-wide text-ink-600">
                  Selected clients
                </div>
                <div className="p-3">
                  {(round?.selected ?? []).length === 0 ? (
                    <p className="text-[11px] text-ink-500">No client selection published.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {round?.selected.map((node) => {
                        const ack = round.acks?.[node];
                        return (
                          <li key={node} className="flex items-center justify-between text-[11px]">
                            <span className="mono text-ink-200">{node}</span>
                            <StatusPill
                              status={ack ?? (round.upload_nodes.includes(node) ? "active" : "pending")}
                              label={ack ?? (round.upload_nodes.includes(node) ? "uploaded" : "waiting")}
                            />
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
              </div>

              <div className="rounded border border-line">
                <div className="border-b border-line px-3 py-2 text-2xs uppercase tracking-wide text-ink-600">
                  FedAvg contributions
                </div>
                <div className="p-3">
                  {(round?.contributions ?? []).length === 0 ? (
                    <p className="text-[11px] text-ink-500">
                      No accepted updates yet. Values are never inferred.
                    </p>
                  ) : (
                    <ul className="space-y-1.5">
                      {round?.contributions?.map((row) => (
                        <li key={row.node_id} className="text-[11px]">
                          <div className="flex items-center justify-between">
                            <span className="mono text-ink-200">{row.node_id}</span>
                            <span className="mono text-accent-text">
                              {row.weight != null ? row.weight.toFixed(3) : "—"}
                            </span>
                          </div>
                          <div className="text-2xs text-ink-600">
                            {formatInteger(row.n_samples)} samples · val {formatNumber(row.val_loss, 6)}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHead title="Timeline" subtitle="Stage transitions as published" icon={<ListTree size={14} />} />
            <div className="max-h-72 overflow-y-auto p-4">
              {(round?.timeline ?? []).length === 0 ? (
                <p className="text-[11px] text-ink-500">
                  No stage events for this round.
                </p>
              ) : (
                <ol className="space-y-2">
                  {round?.timeline?.map((entry, index) => (
                    <li key={`${entry.stage}-${index}`} className="flex gap-2 text-[11px]">
                      <span className="mono w-12 shrink-0 text-ink-600">
                        {formatTime(entry.at)}
                      </span>
                      <span className="min-w-0">
                        <span className="text-ink-200">{entry.label}</span>
                        <span className="mono ml-1.5 text-2xs text-ink-600">
                          {entry.status}
                        </span>
                        {entry.detail ? (
                          <div className="text-2xs text-ink-500">{entry.detail}</div>
                        ) : null}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="Session facts" icon={<Users size={14} />} />
            <div className="p-4">
              <DataRow label="session" value={session?.session_id ?? "—"} />
              <DataRow label="state" value={session?.state ?? "—"} mono={false} />
              <DataRow label="completed" value={`${session?.completed_rounds ?? 0}${session?.total_rounds ? ` / ${session.total_rounds}` : ""}`} />
              <DataRow label="accepted updates" value={formatInteger(session?.accepted_total)} />
              <DataRow label="up / down" value={`${formatBytes(round?.bytes_up)} / ${formatBytes(round?.bytes_down)}`} />
              <DataRow label="round source" value={round?.source ?? "—"} mono={false} />
            </div>
          </Panel>
        </div>
      </div>

      <Panel>
        <PanelHead
          title="Federated gateways"
          subtitle="Each gateway is an independent FL client on a disjoint shard of the historical training years. Weights and validation scalars only; raw rows never leave the gateway."
          icon={<Network size={14} />}
          action={
            <Badge tone={gatewayFl?.available ? "accent" : "neutral"}>
              {gatewayFl?.count ?? 0} clients
            </Badge>
          }
        />
        {(gatewayFl?.gateways ?? []).length === 0 ? (
          <EmptyState
            title="No gateway FL clients"
            message="Start them from the simulator API (POST /api/fl/gateways/start). Gateways then register as independent FL workers on their own MQTT connections."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                  <th className="px-4 py-2 font-medium">Gateway</th>
                  <th className="px-4 py-2 font-medium">Partition</th>
                  <th className="px-4 py-2 text-right font-medium">Local samples</th>
                  <th className="px-4 py-2 text-right font-medium">Val</th>
                  <th className="px-4 py-2 font-medium">State</th>
                  <th className="px-4 py-2 text-right font-medium">Round</th>
                  <th className="px-4 py-2 text-right font-medium">Val loss</th>
                  <th className="px-4 py-2 text-right font-medium">Agg. weight</th>
                  <th className="px-4 py-2 font-medium">Model</th>
                </tr>
              </thead>
              <tbody>
                {(gatewayFl?.gateways ?? []).map((client) => (
                  <tr
                    key={client.gateway_id}
                    className="border-b border-line/60 last:border-0"
                  >
                    <td className="mono px-4 py-2 text-ink-200">
                      <div>{client.gateway_id}</div>
                      <div className="text-2xs text-ink-600">
                        {client.worker_id}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-ink-400">
                      <div>
                        partition{" "}
                        {client.gateway_index != null
                          ? client.gateway_index + 1
                          : "—"}
                        /{client.gateway_count ?? "—"}
                        {client.years.length > 0
                          ? ` · ${client.years.join(", ")}`
                          : ""}
                      </div>
                      <div className="text-2xs text-ink-600">
                        shards{" "}
                        {client.shard_indices.length > 0
                          ? client.shard_indices.join(", ")
                          : "—"}{" "}
                        · {formatInteger(client.source_rows)} rows
                      </div>
                    </td>
                    <td className="mono px-4 py-2 text-right text-ink-300">
                      {formatInteger(client.n_samples)}
                      <div className="text-2xs text-ink-600">
                        {client.storage?.checkpoint_count ?? 0} checkpoints
                      </div>
                    </td>
                    <td className="mono px-4 py-2 text-right text-ink-400">
                      {formatInteger(client.n_val)}
                    </td>
                    <td className="px-4 py-2">
                      <StatusPill
                        status={
                          client.online === false
                            ? "offline"
                            : client.live_state ?? client.state
                        }
                      />
                      {client.last_error ? (
                        <div className="text-2xs text-bad-text">
                          {client.last_error}
                        </div>
                      ) : null}
                    </td>
                    <td className="mono px-4 py-2 text-right text-ink-400">
                      {client.current_round ?? "—"}
                      <div className="text-2xs text-ink-600">
                        {client.storage?.rounds_recorded ?? 0} done
                      </div>
                    </td>
                    <td className="mono px-4 py-2 text-right text-ink-300">
                      {formatNumber(client.last_contribution?.val_loss, 6)}
                    </td>
                    <td className="mono px-4 py-2 text-right text-accent-text">
                      {client.aggregation_weight != null
                        ? client.aggregation_weight.toFixed(3)
                        : "—"}
                    </td>
                    <td className="mono px-4 py-2 text-ink-500">
                      {client.latest_model_version ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel>
        <PanelHead
          title="Round history"
          subtitle="From the coordinator registry (rounds.csv). Loss is the weighted validation loss workers reported."
          icon={<History size={14} />}
          action={<Sparkline values={lossSeries} width={160} height={32} />}
        />
        {history.length === 0 ? (
          <EmptyState
            title="No registered rounds"
            message="A row is written only when a round reaches the registry. Nothing is synthesized for display."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                  <th className="px-4 py-2 font-medium">Round</th>
                  <th className="px-4 py-2 font-medium">Model</th>
                  <th className="px-4 py-2 text-right font-medium">Selected</th>
                  <th className="px-4 py-2 text-right font-medium">Received</th>
                  <th className="px-4 py-2 font-medium">Dropped</th>
                  <th className="px-4 py-2 text-right font-medium">Time</th>
                  <th className="px-4 py-2 text-right font-medium">Bytes up/down</th>
                  <th className="px-4 py-2 text-right font-medium">Val loss</th>
                </tr>
              </thead>
              <tbody className="mono">
                {[...history].reverse().map((row) => (
                  <tr key={row.round} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-2 text-ink-200">{row.round}</td>
                    <td className="px-4 py-2 text-accent-text">{row.model_version}</td>
                    <td className="px-4 py-2 text-right text-ink-400">{row.selected.length}</td>
                    <td className="px-4 py-2 text-right text-ink-300">{row.received}</td>
                    <td className="px-4 py-2 text-ink-500">
                      {row.dropped_nodes?.length ? row.dropped_nodes.join(", ") : "—"}
                    </td>
                    <td className="px-4 py-2 text-right text-ink-400">{seconds(row.round_time_sec)}</td>
                    <td className="px-4 py-2 text-right text-ink-400">
                      {formatBytes(row.bytes_up)} / {formatBytes(row.bytes_down)}
                    </td>
                    <td className="px-4 py-2 text-right text-ink-300">
                      {formatNumber(row.weighted_val_loss, 6)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {summaries.length > 0 ? (
        <Panel>
          <PanelHead title="Retained round summaries" subtitle="Coordinator-authored final records (newest last)" />
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                  <th className="px-4 py-2 font-medium">Round</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="px-4 py-2 text-right font-medium">Accepted</th>
                  <th className="px-4 py-2 text-right font-medium">Rejected</th>
                  <th className="px-4 py-2 text-right font-medium">Seconds</th>
                  <th className="px-4 py-2 font-medium">Mode</th>
                  <th className="px-4 py-2 font-medium">Version</th>
                </tr>
              </thead>
              <tbody>
                {summaries.map((summary) => (
                  <tr key={summary.round} className="border-b border-line/60 last:border-0">
                    <td className="mono px-4 py-2 text-ink-200">{summary.round}</td>
                    <td className="px-4 py-2"><StatusPill status={summary.status} /></td>
                    <td className="mono px-4 py-2 text-right text-ink-300">{summary.accepted.length}</td>
                    <td className="mono px-4 py-2 text-right text-ink-400">{Object.keys(summary.rejected).length}</td>
                    <td className="mono px-4 py-2 text-right text-ink-400">{summary.seconds.toFixed(1)}</td>
                    <td className="px-4 py-2">
                      {summary.single_client ? (
                        <Badge tone="warn">single-client</Badge>
                      ) : summary.aggregated ? (
                        <Badge tone="ok">FedAvg</Badge>
                      ) : (
                        <Badge tone="neutral">not aggregated</Badge>
                      )}
                    </td>
                    <td className="mono px-4 py-2 text-ink-500">{summary.model_version ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

import { useMemo, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, RefreshCw, ShieldCheck, Waves } from "lucide-react";
import { useApi } from "../lib/useApi";
import { useLiveFeed } from "../hooks/useLiveFeed";
import { formatBytes, formatInteger, formatTime, relativeTime } from "../lib/format";
import type { CommunicationPayload } from "../types";
import {
  Badge,
  EmptyState,
  ErrorState,
  Kpi,
  PageSkeleton,
  Panel,
  PanelHeader,
  StatusBadge,
  SummaryRow,
} from "../components/ui";
import { StageTrack } from "../components/StageTrack";

export function CommunicationPage() {
  const { data, error, loading, refresh } = useApi<CommunicationPayload>(
    "/api/communication?limit=150",
    2500,
  );
  const { status: socketStatus, revision } = useLiveFeed();
  const [filter, setFilter] = useState<"all" | "up" | "down">("all");

  const events = useMemo(() => {
    if (!data) return [];
    if (filter === "all") return data.events;
    return data.events.filter((event) => event.direction === filter);
  }, [data, filter]);

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

  const observed = data.observed;
  const checksumTotal = observed.checksum_ok + observed.checksum_bad;

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 pb-10 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            status={data.broker.connected ? "online" : "offline"}
            label={data.broker.connected ? "MQTT connected" : "MQTT disconnected"}
          />
          <Badge tone="mist">
            {data.broker.host}:{data.broker.port}
          </Badge>
          <Badge tone="blue">websocket {socketStatus}</Badge>
          {data.broker.last_error ? <Badge tone="red">{data.broker.last_error}</Badge> : null}
        </div>
        <div className="flex items-center gap-2 text-[11px] text-mist-500">
          <span>last message {relativeTime(data.broker.last_message_at)}</span>
          <button type="button" className="btn" onClick={refresh}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi label="Messages observed" value={formatInteger(observed.messages)} icon={<Waves size={15} />} tone="blue" hint={`${observed.chunks} chunks · ${formatBytes(observed.chunk_bytes)}`} />
        <Kpi label="Bytes up" value={formatBytes(observed.bytes_up)} icon={<ArrowUpRight size={15} />} tone="violet" hint="worker → coordinator" />
        <Kpi label="Bytes down" value={formatBytes(observed.bytes_down)} icon={<ArrowDownLeft size={15} />} tone="emerald" hint="coordinator → worker" />
        <Kpi
          label="Checksums"
          value={checksumTotal === 0 ? "—" : `${observed.checksum_ok}/${checksumTotal}`}
          icon={<ShieldCheck size={15} />}
          tone={observed.checksum_bad > 0 ? "red" : "emerald"}
          hint={`${observed.acks_accepted} accepted acks · ${observed.acks_rejected} rejected`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            title="Live round"
            subtitle={data.live_round ? `Round ${data.live_round.round} · ${data.live_round.is_live ? "live" : "inactive"}` : "No live round observed."}
            icon={<Waves size={15} />}
          />
          <div className="px-5 pb-5 pt-3">
            {!data.live_round ? (
              <EmptyState title="No live round" message="Start a federated session; round progress and acks stream here as retained MQTT telemetry." />
            ) : (
              <div className="space-y-3">
                <StageTrack stages={data.live_round.stages ?? []} />
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                  <SummaryRow label="selected" value={formatInteger(data.live_round.selected.length)} />
                  <SummaryRow label="received" value={formatInteger(data.live_round.received)} />
                  <SummaryRow label="bytes up" value={formatBytes(data.live_round.bytes_up)} />
                  <SummaryRow label="bytes down" value={formatBytes(data.live_round.bytes_down)} />
                </div>
              </div>
            )}
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Model transfer"
            subtitle="The float32 weight vector remains the only model-update path."
            icon={<ShieldCheck size={15} />}
          />
          <div className="grid gap-2.5 px-5 pb-5 pt-3 sm:grid-cols-2">
            <SummaryRow label="model version" value={data.model_transfer.model_version ?? "—"} />
            <SummaryRow label="parameters" value={formatInteger(data.model_transfer.parameters)} />
            <SummaryRow label="transfer bytes" value={formatBytes(data.model_transfer.bytes)} />
            <SummaryRow label="chunk size" value={formatBytes(data.model_transfer.chunk_size)} />
            <SummaryRow label="chunks" value={formatInteger(data.model_transfer.chunks)} />
            <SummaryRow label="source" value={data.model_transfer.source} />
          </div>
          {data.last_model_announce ? (
            <div className="border-t border-ink-700/60 px-5 py-3 text-[11px] text-mist-500">
              <div className="label">last announce</div>
              <div className="mono mt-1 text-mist-200">{data.last_model_announce.model_version ?? "—"}</div>
              <div className="mt-1">
                round {data.last_model_announce.federated_round ?? "—"} · {formatInteger(data.last_model_announce.chunks)} chunks ·{" "}
                {formatBytes(data.last_model_announce.size)} · at {formatTime(data.last_model_announce.at)}
              </div>
            </div>
          ) : null}
        </Panel>
      </div>

      <Panel className="overflow-hidden">
        <PanelHeader
          title="Event stream"
          subtitle={`Observed MQTT traffic · revision ${revision} · retained messages are marked`}
          icon={<Waves size={15} />}
          action={
            <select className="input w-auto py-1" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}>
              <option value="all">all directions</option>
              <option value="up">worker → coordinator</option>
              <option value="down">coordinator → worker</option>
            </select>
          }
        />
        {events.length === 0 ? (
          <EmptyState title="No events" message="Start the broker, coordinator, and workers to observe MQTT traffic. Nothing here is synthesized." />
        ) : (
          <div className="max-h-[520px] overflow-auto">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 border-y border-ink-700/70 bg-ink-850 text-mist-500">
                <tr>
                  <th className="px-4 py-2 font-medium">time</th>
                  <th className="px-3 py-2 font-medium">dir</th>
                  <th className="px-3 py-2 font-medium">kind</th>
                  <th className="px-3 py-2 font-medium">node</th>
                  <th className="px-3 py-2 font-medium">round</th>
                  <th className="px-3 py-2 font-medium">status</th>
                  <th className="px-3 py-2 font-medium">size</th>
                  <th className="px-3 py-2 font-medium">checksum</th>
                  <th className="px-3 py-2 font-medium">detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id} className="border-b border-ink-700/40 last:border-0">
                    <td className="px-4 py-2 mono whitespace-nowrap text-mist-400">{formatTime(event.at)}</td>
                    <td className="px-3 py-2">
                      {event.direction === "up" ? (
                        <span className="inline-flex items-center gap-1 text-signal-violet"><ArrowUpRight size={12} />up</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-signal-emerald"><ArrowDownLeft size={12} />down</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-mist-200">{event.kind}</td>
                    <td className="px-3 py-2 mono text-mist-300">{event.node_id ?? "—"}</td>
                    <td className="px-3 py-2 mono text-mist-300">{event.round ?? "—"}</td>
                    <td className="px-3 py-2">
                      {event.status ? <Badge tone={event.status === "accepted" || event.status === "completed" ? "emerald" : event.status === "rejected" || event.status === "failed" ? "red" : "mist"}>{event.status}</Badge> : <span className="text-mist-500">—</span>}
                    </td>
                    <td className="px-3 py-2 mono text-mist-300">{formatBytes(event.size_bytes)}</td>
                    <td className="px-3 py-2">
                      {event.checksum_ok === null ? (
                        <span className="text-mist-500">—</span>
                      ) : (
                        <Badge tone={event.checksum_ok ? "emerald" : "red"}>
                          {event.checksum_ok ? "ok" : "bad"}
                        </Badge>
                      )}
                    </td>
                    <td className="px-3 py-2 text-mist-400">
                      {event.detail}
                      {event.retained ? <span className="ml-1 text-[9px] uppercase text-mist-600">retained</span> : null}
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
          title="Topic contract"
          subtitle="MQTT topics used by the dynamic worker/coordinator protocol."
          icon={<Waves size={15} />}
        />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead className="border-y border-ink-700/70 bg-ink-800/40 text-mist-500">
              <tr>
                <th className="px-4 py-2 font-medium">topic</th>
                <th className="px-3 py-2 font-medium">direction</th>
                <th className="px-3 py-2 font-medium">purpose</th>
              </tr>
            </thead>
            <tbody>
              {data.topic_contract.map((item) => (
                <tr key={item.topic} className="border-b border-ink-700/40 last:border-0">
                  <td className="px-4 py-2 mono text-mist-200">{item.topic}</td>
                  <td className="px-3 py-2">
                    <Badge tone={item.direction === "up" ? "violet" : "emerald"}>{item.direction}</Badge>
                  </td>
                  <td className="px-3 py-2 text-mist-400">{item.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.acks.rejected_events.length > 0 ? (
          <div className="border-t border-ink-700/60 px-5 py-3">
            <div className="label mb-1">recent rejected updates</div>
            <div className="flex flex-wrap gap-1.5">
              {data.acks.rejected_events.map((event) => (
                <Badge key={event.id} tone="red">
                  {event.node_id ?? "?"} · r{event.round ?? "?"} · {event.detail}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

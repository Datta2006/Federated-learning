import { Activity, ArrowDown, ArrowUp, Radio, ScrollText } from "lucide-react";
import { useApi } from "../lib/useApi";
import type { CommunicationPayload } from "../types";
import {
  Badge,
  DataRow,
  Dot,
  EmptyState,
  Metric,
  Panel,
  PanelHeader,
  PageTitle,
  Sparkline,
} from "../components/ui";
import { formatBytes, formatInteger, formatTime, relativeTime } from "../lib/format";
import { useReducedMotion } from "../components/motion/ReducedMotion";
import { PageEnter } from "../components/motion/PageTransition";

export function CommunicationPage() {
  const { data, error } = useApi<CommunicationPayload>("/api/communication?limit=150", 4000);
  const observed = data?.observed;
  const events = data?.events ?? [];
  const history = data?.history ?? [];

  const reducedMotion = useReducedMotion();

  return (
    <PageEnter>
      <div className="space-y-5">
        <PageTitle
          title="Communication"
          description="What the dashboard's own MQTT subscriber observed: bytes, chunks, checksum verdicts, and acknowledgements. Chunk bodies are verified and discarded."
          meta={
            <Badge tone={data?.broker.connected ? "ok" : "bad"}>
              <Dot tone={data?.broker.connected ? "ok" : "bad"} />
              {data?.broker.connected ? "broker connected" : "broker unreachable"}
            </Badge>
          }
        />

        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-panel border border-line bg-line lg:grid-cols-5">
          <Metric label="Messages observed" value={formatInteger(observed?.messages)} />
          <Metric
            label="Up"
            value={formatBytes(observed?.bytes_up)}
            hint="worker → coordinator"
            tone="info"
          />
          <Metric
            label="Down"
            value={formatBytes(observed?.bytes_down)}
            hint="coordinator → workers"
            tone="accent"
          />
          <Metric
            label="Chunks"
            value={formatInteger(observed?.chunks)}
            hint={`${formatBytes(observed?.chunk_bytes)} verified`}
          />
          <Metric
            label="Acks"
            value={`${observed?.acks_accepted ?? 0} / ${observed?.acks_rejected ?? 0}`}
            hint="accepted / rejected"
            tone={observed?.acks_rejected ? "bad" : "ok"}
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2">
            <PanelHeader
              title="Observed traffic"
              subtitle="Newest first. Retained replays are deduplicated."
              icon={<Radio size={14} />}
            />
            {events.length === 0 ? (
              <EmptyState
                icon={<Activity size={15} />}
                title="No messages observed yet"
                message="Start the broker and a session. The observer only counts traffic it actually received since connecting."
              />
            ) : (
              <div className="max-h-[460px] overflow-auto">
                <table className="w-full border-collapse text-[11px]">
                  <thead className="sticky top-0 bg-panel">
                    <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                      <th className="px-4 py-2 font-medium">Time</th>
                      <th className="px-4 py-2 font-medium">Dir</th>
                      <th className="px-4 py-2 font-medium">Kind</th>
                      <th className="px-4 py-2 font-medium">Node</th>
                      <th className="px-4 py-2 text-right font-medium">Bytes</th>
                      <th className="px-4 py-2 font-medium">Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((event) => (
                      <tr key={event.id} className="border-b border-line/60 last:border-0">
                        <td className="mono px-4 py-1.5 text-ink-600">{formatTime(event.at)}</td>
                        <td className="px-4 py-1.5">
                          {event.direction === "up" ? (
                            <ArrowUp size={12} className="text-info" />
                          ) : event.direction === "down" ? (
                            <ArrowDown size={12} className="text-accent" />
                          ) : (
                            <span className="text-ink-600">—</span>
                          )}
                        </td>
                        <td className="mono px-4 py-1.5 text-ink-300">{event.kind}</td>
                        <td className="mono whitespace-nowrap px-4 py-1.5 text-ink-400">{event.node_id ?? "—"}</td>
                        <td className="mono px-4 py-1.5 text-right text-ink-500">
                          {formatInteger(event.size_bytes)}
                        </td>
                        <td className="px-4 py-1.5 text-ink-400">
                          {event.detail}
                          {event.checksum_ok === false ? (
                            <Badge tone="bad" className="ml-2">checksum mismatch</Badge>
                          ) : null}
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
              <PanelHeader title="Broker" />
              <div className="p-4">
                <DataRow label="host" value={`${data?.broker.host ?? "—"}:${data?.broker.port ?? "—"}`} />
                <DataRow label="base topic" value={data?.broker.base_topic ?? "—"} />
                <DataRow label="connected" value={data?.broker.connected_at ? relativeTime(data.broker.connected_at) : "—"} mono={false} />
                <DataRow label="last message" value={data?.broker.last_message_at ? relativeTime(data.broker.last_message_at) : "—"} mono={false} />
                <DataRow label="error" value={data?.broker.last_error ?? "none"} mono={false} />
              </div>
            </Panel>

            <Panel>
              <PanelHeader title="Round transfer history" icon={<ScrollText size={14} />} />
              <div className="p-4">
                <Sparkline
                  values={history.map((row) => row.bytes_up + row.bytes_down)}
                  width={260}
                  height={44}
                />
                <div className="mt-3">
                  {history.slice(-6).reverse().map((row) => (
                    <DataRow
                      key={row.round}
                      label={`round ${row.round} · ${row.received}/${row.selected}`}
                      value={`${formatBytes(row.bytes_up)} / ${formatBytes(row.bytes_down)}`}
                    />
                  ))}
                </div>
              </div>
            </Panel>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <Panel>
            <PanelHeader title="Topic contract" subtitle="The MQTT surface this system depends on" />
            <div className="max-h-72 overflow-auto p-4">
              {(data?.topic_contract ?? []).map((topic) => (
                <div key={topic.topic} className="border-b border-line/60 py-2 last:border-0">
                  <div className="flex items-center justify-between gap-3">
                    <span className="mono truncate text-[11px] text-ink-300">{topic.topic}</span>
                    <Badge tone={topic.direction === "up" ? "info" : "accent"}>
                      {topic.direction}
                    </Badge>
                  </div>
                  <p className="mt-1 text-2xs leading-relaxed text-ink-600">{topic.purpose}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Model transfer" />
            <div className="p-4">
              <DataRow label="model version" value={data?.model_transfer.model_version ?? "—"} />
              <DataRow label="parameters" value={formatInteger(data?.model_transfer.parameters)} />
              <DataRow label="float32 bytes" value={formatBytes(data?.model_transfer.bytes)} />
              <DataRow label="chunk size" value={formatBytes(data?.model_transfer.chunk_size)} />
              <DataRow label="chunks" value={formatInteger(data?.model_transfer.chunks)} />
              <DataRow label="last announce" value={data?.last_model_announce?.at ? relativeTime(data.last_model_announce.at) : "—"} mono={false} />
              <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
                {data?.provenance.note}
              </p>
            </div>
          </Panel>
        </div>
      </div>
    </PageEnter>
  );
}
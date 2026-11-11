import { useApi } from "../lib/useApi";
import { formatBytes, formatInteger } from "../lib/format";
import type { CommunicationPayload, StatusPayload } from "../types";

/**
 * Connection and aggregation health derived from `/api/status` plus the
 * optional `/api/communication` totals. Read-only, like the rest of the page.
 */
export function ConnectionHealthCard({ payload }: { payload: StatusPayload }) {
  const broker = payload.broker;
  const round = payload.current_round;
  const { data: comm } = useApi<CommunicationPayload>("/api/communication", 5000);
  const observed = comm?.observed;

  const acks = round?.acks ?? {};
  const acceptedAcks = Object.values(acks).filter((status) => status === "accepted").length;
  const rejectedAcks = Object.values(acks).filter((status) => status === "rejected").length;
  const messages = observed?.messages ?? payload.observer.events;
  const checksumOk = observed?.checksum_ok ?? 0;
  const checksumBad = observed?.checksum_bad ?? 0;
  const chunkBytes = observed?.chunk_bytes ?? 0;
  const bytesUp = round?.bytes_up ?? observed?.bytes_up ?? 0;
  const bytesDown = round?.bytes_down ?? observed?.bytes_down ?? 0;

  return (
    <section id="overview-health" className="mt-6 panel p-5">
      <h3 className="text-sm font-semibold text-mist-100">Connection & aggregation health</h3>
      <ul className="mt-3 space-y-2 text-[12px] text-mist-300">
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Broker</span>
          <span className="font-mono text-mist-200">
            {broker.connected ? "connected" : "disconnected"} · {broker.host}:
            {broker.port ?? "?"} ·{" "}
            <span className="text-signal-violet">{broker.base_topic ?? "—"}</span>
          </span>
        </li>
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Observer events</span>
          <span className="font-mono text-mist-200">{formatInteger(messages)}</span>
        </li>
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Round ack counts</span>
          <span className="font-mono text-mist-200">
            {acceptedAcks} accepted · {rejectedAcks} rejected
          </span>
        </li>
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Checksum ok / bad</span>
          <span className="font-mono text-mist-200">
            {formatInteger(checksumOk)} / {formatInteger(checksumBad)}
          </span>
        </li>
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Chunk bytes</span>
          <span className="font-mono text-mist-200">{formatBytes(chunkBytes)}</span>
        </li>
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Round bytes up / down</span>
          <span className="font-mono text-mist-200">
            {formatBytes(bytesUp)} / {formatBytes(bytesDown)}
          </span>
        </li>
      </ul>
    </section>
  );
}

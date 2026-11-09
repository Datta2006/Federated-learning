import { Kpi, StatusBadge } from "./ui";
import type { StatusPayload } from "../types";

/**
 * Derived from `ConnectionHealth` shape — pulls nothing from telemetry directly.
 * Shows broker connection, ack counts, bytes up/down.
 */
export function ConnectionHealthCard({ payload }: { payload: StatusPayload }) {
  const broker = payload.broker;
  const rounds = payload.current_round;
  const acks = (rounds?.acks ?? {}) as Record<string, string>;
  const acceptedAcks = Object.values(acks).filter((s) => s === "accepted").length;
  const rejectedAcks = Object.values(acks).filter((s) => s === "rejected").length;
  const messages = rounds?.messages ?? 0;
  const chunkBytes = rounds?.chunk_bytes ?? 0;
  const checksumOk = rounds?.checksum_ok ?? 0;
  const checksumBad = rounds?.checksum_bad ?? 0;

  return (
    <section id="overview-health" className="mt-10 panel p-5">
      <h3 className="text-sm font-semibold text-mist-100">Connection & aggregation health</h3>
      <ul className="mt-3 space-y-2 text-[12px] text-mist-300">
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Broker</span>
          <span className="font-mono text-mist-200">
            {broker.connected ? "connected" : "disconnected"} ·{" "}
            {broker.host}:{broker.port ?? "?"} ·{" "}
            <span className="text-signal-violet">{broker.base_topic ?? "—"}</span>
          </span>
        </li>
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Observer events</span>
          <span className="font-mono text-mist-200">{messages}</span>
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
            {checksumOk} / {checksumBad}
          </span>
        </li>
        <li className="flex items-center justify-between gap-4">
          <span className="text-mist-500">Chunk bytes</span>
          <span className="font-mono text-mist-200">
            {totalChunkBytes ? `${formatBytesLocal(totalChunkBytes)} total` : "—"}
          </span>
        </li>
      </ul>
    </section>
  );
}

function formatBytesLocal(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value < 1024) return `${Math.round(value)} B`;
  const units = ["KiB", "MiB", "GiB"];
  let v = value / 1024;
  let unit = 0;
  while (v >= 1024 && unit < units.length - 1) {
    v /= 1024;
    unit += 1;
  }
  return `${v.toFixed(1)} ${units[unit]}`;
}
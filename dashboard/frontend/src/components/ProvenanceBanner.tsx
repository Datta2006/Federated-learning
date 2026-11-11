import { Badge, StatusBadge } from "./ui";
import type { StatusPayload } from "../types";

/**
 * One-line data-source banner. Shows live_mqtt / registry_only / unavailable,
 * plus broker host/port and base topic.
 */
export function ProvenanceBanner({ payload }: { payload: StatusPayload }) {
  const broker = payload.broker;
  const sourceTone =
    payload.data_source === "live_mqtt"
      ? "emerald"
      : payload.data_source === "registry_only"
        ? "blue"
        : "red";
  return (
    <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-[11px] text-mist-400">
        <span className="text-mist-200">source:</span>
        <Badge tone={sourceTone}>{payload.data_source}</Badge>
      </div>
      {payload.data_source !== "unavailable" && (
        <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-mist-300">
          {broker.connected ? (
            <StatusBadge status="online" />
          ) : (
            <StatusBadge status="offline" />
          )}
          <span>
            {broker.host}:{broker.port ?? "?"}
          </span>
          <span className="text-mist-500">/ {broker.base_topic ?? "—"}</span>
        </div>
      )}
    </header>
  );
}

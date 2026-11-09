import { Badge, Dot, StatusBadge } from "./ui";
import type { NodeView } from "../types";

interface NodeCardProps {
  node: NodeView;
}

/**
 * One card per node. Owns its own status, role, year, and last-seen
 * timestamps. Pulls everything from NodeView so there is no input path
 * that bypasses the telemetry state machine.
 */
export function NodeCard({ node }: NodeCardProps) {
  const roleTone = node.role === "training" ? "violet" : "blue";
  const lastSeen = node.last_seen ?? "never";
  const lastHealth = node.last_health ?? "—";
  const reason = node.reason ? ` (${node.reason})` : "";
  const reported = node.reported_state ?? node.status;

  return (
    <article className="panel flex h-full flex-col gap-3 p-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="chip bg-ink-700 text-mist-100">{node.id}</span>
        <Badge tone={roleTone} className="text-[10px]">
          {node.role}
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        <StatusBadge status={node.status} label={reported} />
        {node.retained ? (
          <span className="chip bg-ink-800 text-mist-500 text-[9px]">retained</span>
        ) : null}
      </div>

      <dl className="space-y-1 text-[11px] text-mist-400">
        <div className="flex justify-between">
          <dt className="text-mist-500">year</dt>
          <dd className="mono text-mist-200">{node.year ?? "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-mist-500">last seen</dt>
          <dd className="mono text-right text-mist-200">{lastSeen}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-mist-500">last health</dt>
          <dd className="mono text-right text-mist-200">{lastHealth}</dd>
        </div>
      </dl>

      {node.source === "none" ? (
        <span className="chip bg-ink-800 text-mist-500 text-[9px]">no mqtt</span>
      ) : (
        <span className="chip bg-signal-emeraldDim/40 text-signal-emerald/80 text-[9px]">
          <Dot tone="emerald" />
          mqtt
        </span>
      )}

      {reason ? (
        <p className="text-[10px] text-mist-500">{reason}</p>
      ) : null}
    </article>
  );
}
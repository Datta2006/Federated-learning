import { Badge, Dot, StatusBadge } from "./ui";
import type { NodeView } from "../types";

export function NodeTopology({ nodes }: { nodes: NodeView[] }) {
  const online = nodes.filter((node) => node.status === "online").length;
  const training = nodes.filter((node) => node.role === "training").length;
  const inference = nodes.filter((node) => node.role === "inference").length;

  return (
    <section id="overview-topology" className="panel p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-mist-100">Node topology</h2>
        <span className="text-[11px] text-mist-500">
          {online}/{nodes.length} online · {training} training · {inference} inference
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
        {nodes.map((node) => (
          <NodeCard key={node.id} node={node} />
        ))}
      </div>
    </section>
  );
}

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
import { usePoll } from "../hooks/usePoll";
import { useAction } from "../hooks/useAction";
import type { NetworkSnapshot } from "../types";
import { formatDateTime, formatNumber } from "../lib/format";
import { Badge, Dot, Empty, Panel, Stat } from "../components/primitives";

export function LiveNetworkTopologyPage() {
  const snapshot = usePoll<NetworkSnapshot>("/api/network/topology", 8000);
  const action = useAction();

  const simulation = snapshot.data?.simulation;
  const topology = snapshot.data?.topology;
  const counts = topology?.counts;
  const positions = new Map<string, { x: number; y: number }>();
  topology?.nodes.forEach((node) => positions.set(node.node_id, node.position));

  // Crop the square simulator coordinate space to the nodes it actually uses,
  // so the diagram does not waste most of the card on empty margins.
  const nodePoints = topology?.nodes.map((node) => node.position) ?? [];
  const pad = 6;
  const viewBox =
    nodePoints.length > 0
      ? [
          Math.min(...nodePoints.map((point) => point.x)) - pad,
          Math.min(...nodePoints.map((point) => point.y)) - pad,
          Math.max(...nodePoints.map((point) => point.x)) -
            Math.min(...nodePoints.map((point) => point.x)) +
            pad * 2,
          Math.max(...nodePoints.map((point) => point.y)) -
            Math.min(...nodePoints.map((point) => point.y)) +
            pad * 2,
        ].join(" ")
      : "0 0 100 100";

  const start = async () => {
    await action.run("/api/network/simulation/start", {});
    snapshot.refresh();
  };
  const stop = async () => {
    await action.run("/api/network/simulation/stop", {});
    snapshot.refresh();
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Network topology</h1>
          <p className="page-sub">
            Gateways and sensors defined by the simulator. This is synthetic network structure, not
            live physical hardware.
          </p>
        </div>
        <div className="toolbar">
          <Badge tone={simulation?.running ? "ok" : "neutral"}>
            <Dot tone={simulation?.running ? "ok" : "neutral"} />
            {simulation?.state ?? "unknown"}
          </Badge>
          <button
            className="btn btn-primary"
            type="button"
            disabled={action.pending || simulation?.running}
            onClick={() => void start()}
          >
            Start
          </button>
          <button
            className="btn btn-danger"
            type="button"
            disabled={action.pending || !simulation?.running}
            onClick={() => void stop()}
          >
            Stop
          </button>
        </div>
      </div>

      {action.error && <div className="notice notice-bad">{action.error}</div>}
      {snapshot.error && <div className="notice notice-bad">Topology API: {snapshot.error}</div>}

      <div className="stat-grid">
        <Stat label="Gateways" value={counts?.gateways ?? "—"} sub={`${counts?.online_gateways ?? 0} online`} />
        <Stat label="Sensors" value={counts?.sensors ?? "—"} sub={`${counts?.online_sensors ?? 0} online`} />
        <Stat label="Links" value={counts?.links ?? "—"} sub={`${counts?.available_links ?? 0} available`} />
        <Stat
          label="Simulated time"
          value={simulation ? formatDateTime(simulation.simulated_time) : "—"}
          sub={simulation ? `tick ${simulation.tick_count}` : "not running"}
        />
      </div>

      <Panel
        title="Topology map"
        subtitle={topology?.name ?? "Waiting for topology"}
        footer={
          <div className="chart-legend">
            <span>
              <span className="dot dot-accent" style={{ display: "inline-block", marginRight: 6 }} />
              gateway
            </span>
            <span>
              <span className="dot dot-ok" style={{ display: "inline-block", marginRight: 6 }} />
              sensor online
            </span>
            <span>
              <span className="dot dot-bad" style={{ display: "inline-block", marginRight: 6 }} />
              sensor offline
            </span>
          </div>
        }
      >
        {!topology || topology.nodes.length === 0 ? (
          <Empty title="No topology returned" hint="Start the network simulator or check the topology API." />
        ) : (
          <div className="topology-map">
            <svg
              viewBox={viewBox}
              preserveAspectRatio="xMidYMid meet"
              role="img"
              aria-label="Network topology map"
            >
              {topology.links.map((link) => {
                const from = positions.get(link.source);
                const to = positions.get(link.destination);
                if (!from || !to) return null;
                return (
                  <line
                    key={link.link_id}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                    stroke={link.available ? "var(--line-strong)" : "var(--bad)"}
                    strokeWidth={0.45}
                    strokeDasharray={link.available ? undefined : "1.5 1.5"}
                    opacity={0.9}
                  />
                );
              })}
              {topology.nodes.map((node) => {
                const gateway = node.node_type === "gateway";
                const color = node.available
                  ? gateway
                    ? "var(--accent)"
                    : "var(--ok)"
                  : "var(--bad)";
                return (
                  <g key={node.node_id}>
                    {gateway ? (
                      <rect
                        x={node.position.x - 1.7}
                        y={node.position.y - 1.7}
                        width={3.4}
                        height={3.4}
                        rx={0.6}
                        fill={color}
                      />
                    ) : (
                      <circle cx={node.position.x} cy={node.position.y} r={1.1} fill={color} />
                    )}
                    <text
                      x={node.position.x}
                      y={node.position.y - (gateway ? 3 : 2.2)}
                      textAnchor="middle"
                      fontSize={1.9}
                      fill="var(--muted)"
                      stroke="var(--surface-2)"
                      strokeWidth={0.3}
                      paintOrder="stroke"
                      fontFamily="var(--font-mono)"
                    >
                      {node.node_id}
                    </text>
                    <title>
                      {node.name} · {node.node_type} · {node.available ? "online" : "offline"}
                    </title>
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </Panel>

      <div className="cols-2">
        <Panel title="Nodes" subtitle="Positions, availability, and link counts" bodyTight>
          {!topology ? (
            <Empty title="No nodes" hint="The simulator has not returned a topology." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Node</th>
                    <th>Type</th>
                    <th>State</th>
                    <th className="right">Neighbours</th>
                    <th>Location</th>
                  </tr>
                </thead>
                <tbody>
                  {topology.nodes.map((node) => (
                    <tr key={node.node_id}>
                      <td className="primary mono">{node.node_id}</td>
                      <td>{node.node_type}</td>
                      <td>
                        <Badge tone={node.available ? "ok" : "bad"}>
                          <Dot tone={node.available ? "ok" : "bad"} />
                          {node.available ? "online" : "offline"}
                        </Badge>
                      </td>
                      <td className="num">{node.neighbors.length}</td>
                      <td className="small muted">{node.position.location ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Gateways" subtitle="Local storage and health as reported by the simulator" bodyTight>
          {!topology ? (
            <Empty title="No gateways" hint="Start the network simulator." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Gateway</th>
                    <th className="right">Sensors</th>
                    <th className="right">Storage</th>
                    <th>Health</th>
                    <th className="right">CPU</th>
                  </tr>
                </thead>
                <tbody>
                  {topology.gateways.map((gateway) => (
                    <tr key={gateway.gateway_id}>
                      <td className="primary mono">{gateway.gateway_id}</td>
                      <td className="num">{gateway.connected_sensor_count}</td>
                      <td className="num">{formatNumber(gateway.local_storage.used_pct, 1)}%</td>
                      <td>
                        <Badge tone={gateway.health.status === "healthy" ? "ok" : "warn"}>
                          {gateway.health.status}
                        </Badge>
                      </td>
                      <td className="num">{formatNumber(gateway.health.cpu_load_pct, 0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

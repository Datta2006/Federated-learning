import { useMemo, useState, useEffect } from "react";
import {
  Activity,
  ArrowRight,
  Compass,
  Gauge,
  Play,
  RotateCcw,
  Square,
  Waypoints,
  Timer,
  Route,
  GitBranch,
} from "lucide-react";
import { useApi } from "../lib/useApi";
import { useAction } from "../hooks/useAction";
import { apiGet } from "../lib/api";
import type {
  NetworkGatewayNode,
  NetworkLink,
  NetworkSensorNode,
  NetworkSnapshot,
  RPLStateResponse,
  DODAGSummary,
  TrickleStateResponse,
  RPLRouteResponse,
  RPLParentCandidate,
  RPLRouteEntry,
} from "../types";
import {
  Badge,
  DataRow,
  Dot,
  Metric,
  Panel,
  PanelHead,
  PageTitle,
  Skeleton,
  StatusPill,
} from "../components/ui";
import { formatDateTime, formatInteger, formatNumber } from "../lib/format";

const CANVAS_W = 100;
const CANVAS_H = 70;

function clampPosition(value: number, max: number): number {
  return Math.max(4, Math.min(max - 4, value));
}

function linkTone(link: NetworkLink): string {
  if (!link.available) return "text-ink-600";
  if (link.quality >= 0.85) return "text-ok";
  if (link.quality >= 0.65) return "text-accent";
  return "text-warn";
}

function TopologyCanvas({
  sensors,
  gateways,
  links,
  selected,
  rplState,
  routeData,
  onSelect,
}: {
  sensors: NetworkSensorNode[];
  gateways: NetworkGatewayNode[];
  links: NetworkLink[];
  selected: string | null;
  rplState: RPLStateResponse | null;
  routeData: RPLRouteResponse | null;
  onSelect: (nodeId: string) => void;
}) {
  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const node of [...gateways, ...sensors]) {
      map.set(node.node_id, {
        x: clampPosition(node.position.x, CANVAS_W),
        y: clampPosition(node.position.y, CANVAS_H),
      });
    }
    return map;
  }, [gateways, sensors]);

  // Build RPL route edges from rplState
  const rplEdges = useMemo(() => {
    const edges: Array<{ from: string; to: string; type: "preferred" | "candidate" | "route"; dodagId: string }> = [];
    if (!rplState?.dodag_states) return edges;

    for (const [dodagId, nodeState] of Object.entries(rplState.dodag_states)) {
      // Preferred parent edge
      if (nodeState.preferred_parent) {
        edges.push({
          from: nodeState.node_id,
          to: nodeState.preferred_parent,
          type: "preferred",
          dodagId,
        });
      }
      // Candidate parent edges
      for (const candidate of nodeState.parent_candidates ?? []) {
        if (!candidate.is_preferred) {
          edges.push({
            from: nodeState.node_id,
            to: candidate.parent_id,
            type: "candidate",
            dodagId,
          });
        }
      }
    }
    return edges;
  }, [rplState]);

  // Complete route edges for selected node
  const routeEdges = useMemo(() => {
    const edges: Array<{ from: string; to: string }> = [];
    if (!routeData?.route || routeData.route.length < 2) return edges;
    for (let i = 0; i < routeData.route.length - 1; i++) {
      edges.push({
        from: routeData.route[i],
        to: routeData.route[i + 1],
      });
    }
    return edges;
  }, [routeData]);

  // Rank labels for nodes
  const rankLabels = useMemo(() => {
    const labels: Record<string, { rank: number; parent: string | null }> = {};
    if (!rplState?.dodag_states) return labels;
    for (const [, nodeState] of Object.entries(rplState.dodag_states)) {
      if (nodeState.rank) {
        labels[nodeState.node_id] = {
          rank: nodeState.rank.rank,
          parent: nodeState.rank.parent_id,
        };
      }
    }
    return labels;
  }, [rplState]);

  return (
    <svg
      viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
      className="h-[420px] w-full rounded-b bg-inset"
      role="img"
      aria-label="Simulated network topology with RPL routes"
    >
      <defs>
        <marker
          id="link-arrow"
          viewBox="0 0 6 6"
          refX="5"
          refY="3"
          markerWidth="4"
          markerHeight="4"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L6,3 L0,6 z" fill="currentColor" />
        </marker>
        <marker
          id="rpl-arrow"
          viewBox="0 0 8 8"
          refX="7"
          refY="4"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
        </marker>
        <marker
          id="route-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
      </defs>

      {/* Physical links */}
      {links.map((link) => {
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
            stroke="currentColor"
            strokeWidth={0.18 + link.quality * 0.5}
            strokeOpacity={link.available ? 0.65 : 0.25}
            strokeDasharray={link.available ? undefined : "1.4 1"}
            markerEnd={link.bidirectional ? undefined : "url(#link-arrow)"}
            className={linkTone(link)}
          />
        );
      })}

      {/* RPL Candidate Parent edges (dashed gray) */}
      {rplEdges
        .filter((e) => e.type === "candidate")
        .map((edge) => {
          const from = positions.get(edge.from);
          const to = positions.get(edge.to);
          if (!from || !to) return null;
          return (
            <line
              key={`candidate-${edge.from}-${edge.to}-${edge.dodagId}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="currentColor"
              strokeWidth={0.6}
              strokeOpacity={0.5}
              strokeDasharray="2 2"
              markerEnd="url(#rpl-arrow)"
              className="text-ink-500"
            />
          );
        })}

      {/* RPL Preferred Parent edges (solid blue) */}
      {rplEdges
        .filter((e) => e.type === "preferred")
        .map((edge) => {
          const from = positions.get(edge.from);
          const to = positions.get(edge.to);
          if (!from || !to) return null;
          return (
            <line
              key={`preferred-${edge.from}-${edge.to}-${edge.dodagId}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="currentColor"
              strokeWidth={1.2}
              strokeOpacity={0.9}
              markerEnd="url(#rpl-arrow)"
              className="text-accent"
            />
          );
        })}

      {/* Complete Route edges (thick accent with arrow) */}
      {routeEdges.map((edge, idx) => {
        const from = positions.get(edge.from);
        const to = positions.get(edge.to);
        if (!from || !to) return null;
        return (
          <line
            key={`route-${edge.from}-${edge.to}-${idx}`}
            x1={from.x}
            y1={from.y}
            x2={to.x}
            y2={to.y}
            stroke="currentColor"
            strokeWidth={2.0}
            strokeOpacity={1.0}
            markerEnd="url(#route-arrow)"
            className="text-accent"
            style={{ filter: "drop-shadow(0 0 2px currentColor)" }}
          />
        );
      })}

      {gateways.map((gateway) => {
        const point = positions.get(gateway.node_id);
        if (!point) return null;
        const rankInfo = rankLabels[gateway.node_id];
        return (
          <g
            key={gateway.node_id}
            onClick={() => onSelect(gateway.node_id)}
            className="cursor-pointer"
          >
            <rect
              x={point.x - 2.6}
              y={point.y - 2.6}
              width={5.2}
              height={5.2}
              rx={0.9}
              className={
                selected === gateway.node_id
                  ? "fill-accent text-accent"
                  : gateway.available
                    ? "fill-ok text-ink-100"
                    : "fill-bad text-ink-500"
              }
              stroke="currentColor"
              strokeWidth={0.4}
            />
            {/* Rank label for gateway (root = 0) */}
            {rankInfo && (
              <text
                x={point.x}
                y={point.y - 4.5}
                textAnchor="middle"
                className="fill-accent"
                style={{ fontSize: 1.8, fontWeight: 600 }}
              >
                R:{rankInfo.rank}
              </text>
            )}
            <text
              x={point.x}
              y={point.y + 5.6}
              textAnchor="middle"
              className="fill-ink-400"
              style={{ fontSize: 2.2 }}
            >
              {gateway.node_id}
            </text>
            <text
              x={point.x}
              y={point.y + 8}
              textAnchor="middle"
              className="fill-ink-600"
              style={{ fontSize: 1.8 }}
            >
              {gateway.connected_sensor_count} sensors
            </text>
          </g>
        );
      })}

      {sensors.map((sensor) => {
        const point = positions.get(sensor.node_id);
        if (!point) return null;
        const rankInfo = rankLabels[sensor.node_id];
        return (
          <g
            key={sensor.node_id}
            onClick={() => onSelect(sensor.node_id)}
            className="cursor-pointer"
          >
            <circle
              cx={point.x}
              cy={point.y}
              r={selected === sensor.node_id ? 2.5 : 1.9}
              className={
                sensor.available
                  ? selected === sensor.node_id
                    ? "fill-accent"
                    : "fill-ink-300"
                  : "fill-bad"
              }
              stroke="currentColor"
              strokeWidth={0.35}
              strokeOpacity={0.5}
            />
            {selected === sensor.node_id ? (
              <circle
                cx={point.x}
                cy={point.y}
                r={3.8}
                fill="none"
                stroke="currentColor"
                strokeWidth={0.35}
                className="text-accent"
              />
            ) : null}
            {/* Rank label for sensor */}
            {rankInfo && (
              <text
                x={point.x}
                y={point.y - 5.5}
                textAnchor="middle"
                className="fill-accent"
                style={{ fontSize: 1.8, fontWeight: 600 }}
              >
                R:{rankInfo.rank}
              </text>
            )}
            <text
              x={point.x}
              y={point.y - 3.2}
              textAnchor="middle"
              className="fill-ink-500"
              style={{ fontSize: 1.7 }}
            >
              {sensor.node_id.replace("sensor-", "S")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function NetworkPage() {
  const { data, error, loading, refresh } = useApi<NetworkSnapshot>(
    "/api/network/topology",
    3000,
  );
  const action = useAction();
  const [selected, setSelected] = useState<string | null>(null);
  const [rplState, setRplState] = useState<RPLStateResponse | null>(null);
  const [trickleState, setTrickleState] = useState<TrickleStateResponse | null>(null);
  const [routeData, setRouteData] = useState<RPLRouteResponse | null>(null);
  const [dodagSummaries, setDodagSummaries] = useState<DODAGSummary[]>([]);
  const [rplLoading, setRplLoading] = useState(false);

  const topology = data?.topology;
  const simulation = data?.simulation;
  const sensors = topology?.sensors ?? [];
  const gateways = topology?.gateways ?? [];
  const links = topology?.links ?? [];
  const counts = topology?.counts;

  const selectedSensor = sensors.find((node) => node.node_id === selected);
  const selectedGateway = gateways.find((node) => node.node_id === selected);

  // Fetch RPL state when a node is selected
  useEffect(() => {
    if (!selected) {
      setRplState(null);
      setTrickleState(null);
      setRouteData(null);
      return;
    }

    setRplLoading(true);
    const fetchRplData = async () => {
      try {
        const [rplRes, dodagRes] = await Promise.all([
          apiGet<RPLStateResponse>(`/api/network/rpl/state/${selected}`),
          apiGet<DODAGSummary[]>(`/api/network/rpl/dodags`),
        ]);
        setRplState(rplRes);
        setDodagSummaries(dodagRes);

        // Get Trickle state for each DODAG this node participates in
        if (rplRes?.dodag_states) {
          for (const dodagId of Object.keys(rplRes.dodag_states)) {
            try {
              const trickleRes = await apiGet<TrickleStateResponse>(
                `/api/network/trickle/state/${selected}/${dodagId}`
              );
              setTrickleState(trickleRes);
              break; // Use first DODAG's Trickle state
            } catch {
              // Trickle state not available for this DODAG, continue
            }
          }
        }

        // Try to get route to gateway for sensors
        if (selectedSensor?.gateway_id) {
          try {
            const routeRes = await apiGet<RPLRouteResponse>(
              `/api/network/rpl/route/${selected}/${selectedSensor.gateway_id}`
            );
            setRouteData(routeRes);
          } catch {
            setRouteData({ route: [], type: "none", error: "No route found" });
          }
        } else if (selectedGateway) {
          // For gateway, show downward routes to its sensors
          try {
            const routeRes = await apiGet<RPLRouteResponse>(
              `/api/network/rpl/route/${selected}/${sensors[0]?.node_id || ""}`
            );
            setRouteData(routeRes);
          } catch {
            setRouteData({ route: [], type: "none", error: "No sensors found" });
          }
        }
      } catch (err) {
        console.error("Failed to fetch RPL data:", err);
      } finally {
        setRplLoading(false);
      }
    };

    fetchRplData();
  }, [selected, selectedSensor?.gateway_id, selectedGateway]);

  const run = async (path: string, body?: unknown) => {
    const response = await action.run(path, body);
    if (response) refresh();
  };

  // Get the DODAG state for the selected node
  const nodeRplState = rplState?.dodag_states
    ? Object.values(rplState.dodag_states)[0]
    : null;

  const preferredParent = nodeRplState?.preferred_parent;
  const parentCandidates = nodeRplState?.parent_candidates ?? [];
  const routingTable = nodeRplState?.routing_table ?? [];
  const rank = nodeRplState?.rank;

  return (
    <div className="space-y-5">
      <PageTitle
        title="Network simulator"
        description="AirFed Stack 1: simulated sensor and gateway graph with RPL routing. Links are configured simulated adjacency; routes are RPL-discovered."
        meta={
          simulation ? (
            <Badge tone={simulation.running ? "ok" : "neutral"}>
              <Dot tone={simulation.running ? "ok" : "neutral"} pulse={simulation.running} />
              {simulation.state}
            </Badge>
          ) : null
        }
      />

      <div className="grid gap-4 xl:grid-cols-4">
        <Panel className="xl:col-span-3">
          <PanelHead
            title="Topology"
            subtitle="Logical positions only. Click a node to inspect RPL state. Solid lines = physical links, Dashed arrows = RPL routes."
            icon={<Waypoints size={14} />}
            action={
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  className="btn btn-primary"
                  onClick={() => void run("/api/network/simulation/start")}
                  disabled={action.pending || simulation?.running}
                  type="button"
                >
                  <Play size={12} /> Start
                </button>
                <button
                  className="btn"
                  onClick={() => void run("/api/network/simulation/stop")}
                  disabled={action.pending || !simulation?.running}
                  type="button"
                >
                  <Square size={12} /> Stop
                </button>
                <button
                  className="btn"
                  onClick={() => void run("/api/network/simulation/advance", { seconds: 10 })}
                  disabled={action.pending}
                  type="button"
                >
                  <ArrowRight size={12} /> Advance 10s
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => void run("/api/network/simulation/reset")}
                  disabled={action.pending}
                  type="button"
                >
                  <RotateCcw size={12} /> Reset
                </button>
              </div>
            }
          />
          {action.error ? (
            <p className="border-b border-line px-4 py-2 text-[11px] text-bad-text">
              {action.error}
            </p>
          ) : null}
          {loading && !topology ? (
            <div className="p-4">
              <Skeleton className="h-[380px] w-full" />
            </div>
          ) : (
            <TopologyCanvas
              sensors={sensors}
              gateways={gateways}
              links={links}
              selected={selected}
              rplState={rplState}
              routeData={routeData}
              onSelect={(nodeId) =>
                setSelected((current) => (current === nodeId ? null : nodeId))
              }
            />
          )}
          <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-2 text-2xs text-ink-600">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-sm bg-ok" /> gateway
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-ink-300" /> sensor
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 bg-ok" /> good physical link
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 bg-warn" /> weak physical link
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 bg-accent" /> RPL route
            </span>
            <span>dashed = unavailable · solid arrow = directional · RPL = preferred parent</span>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHead title="Simulation clock" icon={<Gauge size={14} />} />
            <div className="p-4">
              <DataRow label="Simulated time" value={formatDateTime(simulation?.simulated_time)} />
              <DataRow label="Ticks" value={formatInteger(simulation?.tick_count)} />
              <DataRow label="Readings" value={formatInteger(simulation?.reading_total)} />
              <DataRow
                label="Interval"
                value={`${formatNumber(simulation?.config.interval_seconds, 0)}s`}
              />
              <DataRow label="Seed" value={simulation?.config.seed ?? "—"} />
            </div>
          </Panel>

          <Panel>
            <PanelHead title="Graph" icon={<Compass size={14} />} />
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded-b border-t border-line bg-line">
              <Metric label="Gateways" value={counts?.gateways ?? "—"} tone="ok" />
              <Metric label="Sensors" value={counts?.sensors ?? "—"} />
              <Metric label="Links" value={counts?.links ?? "—"} tone="accent" />
              <Metric label="Online links" value={counts?.available_links ?? "—"} />
            </div>
          </Panel>

          {/* RPL DODAGs Panel */}
          {dodagSummaries.length > 0 && (
            <Panel>
              <PanelHead title="DODAGs" icon={<GitBranch size={14} />} subtitle="Destination-Oriented Directed Acyclic Graphs" />
              <div className="p-4 space-y-3">
                {dodagSummaries.map((dodag) => (
                  <div key={dodag.dodag_id} className="border border-line rounded p-3">
                    <div className="flex items-center justify-between">
                      <span className="mono text-[11px] text-ink-200">{dodag.dodag_id}</span>
                      <Badge tone="ok">{dodag.mode}</Badge>
                    </div>
                    <div className="mt-1.5 grid grid-cols-2 gap-2 text-2xs text-ink-500">
                      <span>Root: <span className="mono">{dodag.root_id}</span></span>
                      <span>Nodes: {dodag.node_count}</span>
                      <span>Rank factor: {dodag.rank_factor}</span>
                      <span>MinHopRankInc: {dodag.min_hop_rank_increase}</span>
                      <span>OCP: {dodag.ocp}</span>
                      <span>Version: {dodag.version_number}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHead
            title="Sensor readings"
            subtitle="Smooth simulated series, generated per sensor. Every value is labelled SIMULATED."
            icon={<Activity size={14} />}
          />
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                  <th className="px-4 py-2 font-medium">Sensor</th>
                  <th className="px-4 py-2 font-medium">Gateway</th>
                  <th className="px-4 py-2 text-right font-medium">PM2.5</th>
                  <th className="px-4 py-2 text-right font-medium">PM10</th>
                  <th className="px-4 py-2 text-right font-medium">Temp</th>
                  <th className="px-4 py-2 text-right font-medium">Humidity</th>
                  <th className="px-4 py-2 text-right font-medium">Battery</th>
                  <th className="px-4 py-2 font-medium">State</th>
                </tr>
              </thead>
              <tbody>
                {sensors.map((sensor) => {
                  const reading = sensor.latest_reading;
                  return (
                    <tr
                      key={sensor.node_id}
                      onClick={() => setSelected(sensor.node_id)}
                      className={`cursor-pointer border-b border-line/60 last:border-0 ${
                        selected === sensor.node_id ? "bg-accent-dim/40" : ""
                      }`}
                    >
                      <td className="px-4 py-2">
                        <span className="mono text-ink-200">{sensor.node_id}</span>
                        <div className="text-2xs text-ink-600">{sensor.name}</div>
                      </td>
                      <td className="px-4 py-2 text-ink-400">{sensor.gateway_id ?? "—"}</td>
                      <td className="mono px-4 py-2 text-right text-ink-200">
                        {reading ? formatNumber(reading.pm25) : "—"}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {reading ? formatNumber(reading.pm10) : "—"}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {reading ? `${formatNumber(reading.temperature_c)}°C` : "—"}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {reading ? `${formatNumber(reading.humidity_pct)}%` : "—"}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {formatNumber(sensor.battery_level, 0)}%
                      </td>
                      <td className="px-4 py-2">
                        <StatusPill
                          status={sensor.available ? "online" : "offline"}
                          label={sensor.available ? "online" : "offline"}
                        />
                        {reading ? (
                          <div className="mt-0.5 text-2xs text-ink-600">{reading.label}</div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHead
              title="Gateways"
              subtitle="Distinct gateway nodes with local storage and health."
            />
            <div className="space-y-3 p-4">
              {gateways.map((gateway) => (
                <button
                  key={gateway.node_id}
                  type="button"
                  onClick={() => setSelected(gateway.node_id)}
                  className={`w-full rounded border px-3 py-2 text-left ${
                    selected === gateway.node_id
                      ? "border-accent/40 bg-accent-dim/40"
                      : "border-line bg-raise"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="mono text-[11px] text-ink-200">{gateway.node_id}</span>
                    <StatusPill status={gateway.health.status} />
                  </div>
                  <div className="mt-1.5 flex items-center justify-between text-2xs text-ink-500">
                    <span>{gateway.connected_sensor_count} assigned sensors</span>
                    <span>{formatNumber(gateway.local_storage.used_pct, 0)}% storage</span>
                  </div>
                </button>
              ))}
            </div>
          </Panel>

          {/* RPL State Panel for Selected Node */}
          <Panel>
            <PanelHead
              title={selected ? "RPL State" : "Selected node"}
              subtitle={selected ? `RPL routing state for ${selected}` : "Select a node to view RPL state."}
              icon={<Route size={14} />}
            />
            {selected && rplLoading ? (
              <div className="p-4 flex items-center justify-center">
                <Skeleton className="h-4 w-24" />
              </div>
            ) : selected && nodeRplState ? (
              <div className="p-4 space-y-4">
                {/* Rank Info */}
                <div className="border border-line rounded p-3 bg-raise">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium text-ink-300">Rank</span>
                    <Badge tone="accent">{rank?.rank ?? "INFINITE"}</Badge>
                  </div>
                  {rank && (
                    <div className="mt-2 grid grid-cols-2 gap-2 text-2xs text-ink-500">
                      <span>Parent: <span className="mono">{rank.parent_id ?? "ROOT"}</span></span>
                      <span>Path ETX: {formatNumber(rank.path_etx, 2)}</span>
                      <span>Hops: {rank.hop_count}</span>
                      <span>Updated: {new Date(rank.calculated_at).toLocaleTimeString()}</span>
                    </div>
                  )}
                </div>

                {/* Preferred Parent */}
                <div className="border border-line rounded p-3 bg-raise">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium text-ink-300">Preferred Parent</span>
                    {preferredParent ? (
                      <Badge tone="ok">{preferredParent}</Badge>
                    ) : (
                      <Badge tone="neutral">ROOT</Badge>
                    )}
                  </div>
                </div>

                {/* Candidate Parents */}
                {parentCandidates.length > 0 && (
                  <div className="border border-line rounded p-3 bg-raise">
                    <span className="text-[11px] font-medium text-ink-300">Candidate Parents</span>
                    <table className="w-full text-[10px] mt-2">
                      <thead>
                        <tr className="border-b border-line text-left text-2xs uppercase text-ink-600">
                          <th className="px-2 py-1">Parent</th>
                          <th className="px-2 py-1 text-right">Rank</th>
                          <th className="px-2 py-1 text-right">ETX</th>
                          <th className="px-2 py-1 text-right">Path ETX</th>
                          <th className="px-2 py-1 text-right">Quality</th>
                        </tr>
                      </thead>
                      <tbody>
                        {parentCandidates.map((c: RPLParentCandidate) => (
                          <tr
                            key={c.parent_id}
                            className={`border-b border-line/40 last:border-0 ${
                              c.is_preferred ? "bg-accent-dim/30" : ""
                            }`}
                          >
                            <td className="px-2 py-1 mono">
                              {c.parent_id} {c.is_preferred && <span className="text-accent ml-1">★</span>}
                            </td>
                            <td className="px-2 py-1 text-right mono">{c.rank}</td>
                            <td className="px-2 py-1 text-right mono">{formatNumber(c.etx, 2)}</td>
                            <td className="px-2 py-1 text-right mono">{formatNumber(c.path_etx, 2)}</td>
                            <td className="px-2 py-1 text-right mono">{formatNumber(c.link_quality, 2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Routing Table */}
                {routingTable.length > 0 && (
                  <div className="border border-line rounded p-3 bg-raise">
                    <span className="text-[11px] font-medium text-ink-300">Routing Table</span>
                    <table className="w-full text-[10px] mt-2">
                      <thead>
                        <tr className="border-b border-line text-left text-2xs uppercase text-ink-600">
                          <th className="px-2 py-1">Destination</th>
                          <th className="px-2 py-1">Next Hop</th>
                          <th className="px-2 py-1 text-right">ETX</th>
                          <th className="px-2 py-1 text-right">Hops</th>
                          <th className="px-2 py-1">Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {routingTable.map((r: RPLRouteEntry) => (
                          <tr key={`${r.destination}-${r.next_hop}`} className="border-b border-line/40 last:border-0">
                            <td className="px-2 py-1 mono">{r.destination}</td>
                            <td className="px-2 py-1 mono">{r.next_hop}</td>
                            <td className="px-2 py-1 text-right mono">{formatNumber(r.path_etx, 2)}</td>
                            <td className="px-2 py-1 text-right mono">{r.hop_count}</td>
                            <td className="px-2 py-1">
                              <Badge
                                tone={r.is_upward ? "ok" : r.is_downward ? "accent" : "neutral"}
                              >
                                {r.is_upward ? "↑" : r.is_downward ? "↓" : "?"}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Complete Route to Gateway */}
                {routeData && routeData.route.length > 0 && (
                  <div className="border border-line rounded p-3 bg-raise">
                    <span className="text-[11px] font-medium text-ink-300">
                      Complete Route ({routeData.type})
                    </span>
                    <div className="mt-2 flex flex-wrap items-center gap-1 text-[11px]">
                      {routeData.route.map((nodeId, idx) => (
                        <span key={nodeId} className="flex items-center gap-1">
                          <span className="mono text-ink-200">{nodeId}</span>
                          {idx < routeData.route.length - 1 && (
                            <span className="text-ink-500">{routeData.type === "upward" ? "↑" : "↓"}</span>
                          )}
                        </span>
                      ))}
                    </div>
                    {routeData.error && (
                      <div className="mt-2 text-[10px] text-warn">{routeData.error}</div>
                    )}
                  </div>
                )}
              </div>
            ) : selected ? (
              <div className="p-4 space-y-4">
                <p className="px-4 py-6 text-[11px] text-ink-500">
                  No RPL state available for {selected}. Run simulation to build DODAGs.
                </p>
                {selectedSensor && (
                  <button
                    className="w-full btn btn-primary"
                    onClick={async () => {
                      if (selectedSensor.gateway_id) {
                        await action.run("/api/network/rpl/join/" + selected, {
                          dodag_id: selectedSensor.gateway_id,
                        });
                        refresh();
                      }
                    }}
                  >
                    Join DODAG
                  </button>
                )}
              </div>
            ) : (
              <p className="px-4 py-6 text-[11px] text-ink-500">
                Select a sensor or gateway in the topology or table.
              </p>
            )}
          </Panel>

          {/* Trickle State Panel */}
          {trickleState && (
            <Panel>
              <PanelHead
                title="Trickle Timer"
                subtitle={selected ? `Trickle state for ${trickleState.node_id} in ${trickleState.dodag_id}` : ""}
                icon={<Timer size={14} />}
              />
              <div className="p-4 space-y-3">
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div>
                    <span className="text-ink-500">Interval: </span>
                    <span className="mono font-medium">{formatNumber(trickleState.interval, 1)}s</span>
                  </div>
                  <div>
                    <span className="text-ink-500">Counter (c): </span>
                    <span className="mono font-medium">{trickleState.c}/{trickleState.params.k}</span>
                  </div>
                  <div>
                    <span className="text-ink-500">Doublings: </span>
                    <span className="mono font-medium">{trickleState.doubled_count}/{trickleState.params.max_doublings}</span>
                  </div>
                  <div>
                    <span className="text-ink-500">Time to TX: </span>
                    <span className="mono font-medium">
                      {trickleState.time_until_tx !== null
                        ? formatNumber(trickleState.time_until_tx, 1) + "s"
                        : "SUPPRESSED"}
                    </span>
                  </div>
                  <div>
                    <span className="text-ink-500">Interval End: </span>
                    <span className="mono font-medium">
                      {formatNumber(trickleState.time_until_interval_end, 1)}s
                    </span>
                  </div>
                  <div>
                    <span className="text-ink-500">Status: </span>
                    <Badge tone={trickleState.is_suppressed ? "warn" : "ok"}>
                      {trickleState.is_suppressed ? "SUPPRESSED" : "ACTIVE"}
                    </Badge>
                  </div>
                </div>

                <div className="border-t border-line pt-3 text-[10px] text-ink-500">
                  <span className="font-medium">Params: </span>
                  Imin={trickleState.params.imin}s, Imax=2^{trickleState.params.imax}, k={trickleState.params.k}, max_doublings={trickleState.params.max_doublings}
                </div>

                {trickleState.last_tx_time && (
                  <div className="text-[10px] text-ink-500">
                    Last TX: {new Date(trickleState.last_tx_time * 1000).toLocaleTimeString()}
                  </div>
                )}
              </div>
            </Panel>
          )}
        </div>
      </div>

      {error ? <p className="text-[11px] text-bad-text">{error}</p> : null}
    </div>
  );
}

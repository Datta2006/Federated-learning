import { useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Compass,
  Gauge,
  Play,
  RotateCcw,
  Square,
  Waypoints,
} from "lucide-react";
import { useApi } from "../lib/useApi";
import { useAction } from "../hooks/useAction";
import type {
  NetworkGatewayNode,
  NetworkLink,
  NetworkSensorNode,
  NetworkSnapshot,
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
  onSelect,
}: {
  sensors: NetworkSensorNode[];
  gateways: NetworkGatewayNode[];
  links: NetworkLink[];
  selected: string | null;
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

  return (
    <svg
      viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
      className="h-[420px] w-full rounded-b bg-inset"
      role="img"
      aria-label="Simulated network topology"
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
      </defs>

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

      {gateways.map((gateway) => {
        const point = positions.get(gateway.node_id);
        if (!point) return null;
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

  const topology = data?.topology;
  const simulation = data?.simulation;
  const sensors = topology?.sensors ?? [];
  const gateways = topology?.gateways ?? [];
  const links = topology?.links ?? [];
  const counts = topology?.counts;

  const selectedSensor = sensors.find((node) => node.node_id === selected);
  const selectedGateway = gateways.find((node) => node.node_id === selected);

  const run = async (path: string, body?: unknown) => {
    const response = await action.run(path, body);
    if (response) refresh();
  };

  return (
    <div className="space-y-5">
      <PageTitle
        title="Network simulator"
        description="AirFed Stack 1: simulated sensor and gateway graph. Links are configured simulated adjacency, not RPL-discovered routes. Readings are synthetic and are not connected to the trained model."
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
            subtitle="Logical positions only. Click a node to inspect it."
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
              <span className="h-0.5 w-5 bg-ok" /> good link
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 bg-warn" /> weak link
            </span>
            <span>dashed = unavailable · arrow = directional</span>
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

          <Panel>
            <PanelHead title="Selected node" subtitle="Only simulated graph state is shown." />
            {selectedSensor ? (
              <div className="p-4">
                <DataRow label="ID" value={selectedSensor.node_id} />
                <DataRow label="Gateway" value={selectedSensor.gateway_id ?? "—"} />
                <DataRow label="Neighbors" value={selectedSensor.neighbors.length} />
                <DataRow label="Battery" value={`${formatNumber(selectedSensor.battery_level, 1)}%`} />
                <DataRow label="Readings" value={formatInteger(selectedSensor.reading_count)} />
                <DataRow label="Last seen" value={selectedSensor.last_seen ?? "—"} />
              </div>
            ) : selectedGateway ? (
              <div className="p-4">
                <DataRow label="ID" value={selectedGateway.node_id} />
                <DataRow label="Sensors" value={selectedGateway.connected_sensor_count} />
                <DataRow label="Neighbors" value={selectedGateway.neighbors.length} />
                <DataRow label="CPU" value={`${formatNumber(selectedGateway.health.cpu_load_pct, 0)}%`} />
                <DataRow
                  label="Storage"
                  value={`${formatNumber(selectedGateway.local_storage.used_mb, 0)} / ${formatNumber(selectedGateway.local_storage.capacity_mb, 0)} MB`}
                />
                <DataRow label="Uptime" value={`${formatNumber(selectedGateway.health.uptime_sec, 0)}s`} />
              </div>
            ) : (
              <p className="px-4 py-6 text-[11px] text-ink-500">
                Select a sensor or gateway in the topology or table.
              </p>
            )}
          </Panel>
        </div>
      </div>

      {error ? <p className="text-[11px] text-bad-text">{error}</p> : null}
    </div>
  );
}

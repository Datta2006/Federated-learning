import { useState } from "react";
import { usePoll } from "../hooks/usePoll";
import { useAction } from "../hooks/useAction";
import type {
  NetworkSimulationStatus,
  NetworkSnapshot,
  ProcessStatus,
  WorkersPayload,
} from "../types";
import { formatDateTime, formatNumber, relativeTime } from "../lib/format";
import { Badge, Dot, Empty, Field, Panel, Stat, StatusBadge } from "../components/primitives";

export function SimulationLabPage() {
  const simulator = usePoll<NetworkSimulationStatus>("/api/network/status", 4000);
  const topology = usePoll<NetworkSnapshot>("/api/network/topology", 8000);
  const workers = usePoll<WorkersPayload>("/api/workers", 4000);
  const processes = usePoll<ProcessStatus>("/api/processes", 4000);
  const action = useAction<Record<string, unknown>>();

  const [workerCount, setWorkerCount] = useState(3);
  const [role, setRole] = useState<"training" | "inference">("training");
  const [dummy, setDummy] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const sim = simulator.data;
  const net = topology.data?.topology;
  const counts = net?.counts;
  const workerCounts = workers.data?.counts;
  const processList = processes.data?.processes ?? [];

  const run = async (path: string, body: unknown, label: string) => {
    setMessage(null);
    const result = await action.run(path, body);
    if (result) {
      setMessage(label);
      simulator.refresh();
      topology.refresh();
      workers.refresh();
      processes.refresh();
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Simulation lab</h1>
          <p className="page-sub">
            The field-network simulator is synthetic and separate from the trained model. Worker
            processes are real child processes that register over MQTT.
          </p>
        </div>
        <div className="toolbar">
          <button
            className="btn btn-primary"
            type="button"
            disabled={action.pending || sim?.running}
            onClick={() => void run("/api/network/simulation/start", {}, "Network simulator started")}
          >
            Start simulator
          </button>
          <button
            className="btn btn-danger"
            type="button"
            disabled={action.pending || !sim?.running}
            onClick={() => void run("/api/network/simulation/stop", {}, "Network simulator stopped")}
          >
            Stop simulator
          </button>
        </div>
      </div>

      {action.error && <div className="notice notice-bad">{action.error}</div>}
      {message && <div className="notice notice-ok">{message}</div>}

      <div className="stat-grid">
        <Stat
          label="Simulator"
          value={sim?.state ?? "unknown"}
          sub={sim?.topology_name ?? "no topology reported"}
        />
        <Stat
          label="Simulated time"
          value={sim ? formatDateTime(sim.simulated_time) : "—"}
          sub={sim ? `tick ${sim.tick_count}` : "not running"}
        />
        <Stat
          label="Sensor readings"
          value={formatNumber(sim?.reading_total ?? 0, 0)}
          sub={`${counts?.online_sensors ?? 0}/${counts?.sensors ?? 0} sensors online`}
        />
        <Stat
          label="Worker clients"
          value={`${workerCounts?.online ?? 0}/${workerCounts?.total ?? 0}`}
          sub={`${workerCounts?.available ?? 0} available · ${workerCounts?.busy ?? 0} busy`}
        />
      </div>

      <Panel
        title="Field network"
        subtitle={net?.description ?? "Waiting for the topology API."}
        actions={<Badge tone={sim?.running ? "ok" : "neutral"}>{sim?.running ? "simulating" : "stopped"}</Badge>}
        footer={sim?.note}
        bodyTight
      >
        {!net ? (
          <Empty title="Topology unavailable" hint="The network simulator did not return a topology." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Node</th>
                  <th>Type</th>
                  <th>Gateway</th>
                  <th>State</th>
                  <th>Detail</th>
                  <th className="right">Latest PM2.5</th>
                </tr>
              </thead>
              <tbody>
                {net.nodes.map((node) => {
                  const gateway = node.node_type === "gateway";
                  return (
                    <tr key={node.node_id}>
                      <td>
                        <div className="primary">{node.name}</div>
                        <div className="mono tiny faint">{node.node_id}</div>
                      </td>
                      <td>
                        <Badge tone={gateway ? "accent" : "neutral"}>{node.node_type}</Badge>
                      </td>
                      <td className="mono">
                        {gateway ? "—" : (node as { gateway_id: string | null }).gateway_id ?? "—"}
                      </td>
                      <td>
                        <Badge tone={node.available ? "ok" : "bad"}>
                          <Dot tone={node.available ? "ok" : "bad"} />
                          {node.available ? "online" : "offline"}
                        </Badge>
                      </td>
                      <td className="small muted">
                        {gateway
                          ? `${(node as { connected_sensor_count: number }).connected_sensor_count} sensors · ${(node as { health: { status: string } }).health.status}`
                          : `battery ${formatNumber((node as { battery_level: number }).battery_level, 0)}%`}
                      </td>
                      <td className="num">
                        {gateway
                          ? "—"
                          : formatNumber(
                              (node as { latest_reading: { pm25: number } | null }).latest_reading?.pm25 ?? null,
                              1,
                            )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="cols">
        <Panel
          title="Launch workers"
          subtitle="Spawns simulator worker processes through the backend process manager."
        >
          <div className="form-grid" style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}>
            <Field label="Count">
              <input
                className="input"
                type="number"
                min={1}
                max={20}
                value={workerCount}
                onChange={(event) => setWorkerCount(Number(event.target.value))}
              />
            </Field>
            <Field label="Role">
              <select
                className="select"
                value={role}
                onChange={(event) => setRole(event.target.value as "training" | "inference")}
              >
                <option value="training">training</option>
                <option value="inference">inference</option>
              </select>
            </Field>
            <Field label="Prefix">
              <input className="input" type="text" value="sim" readOnly />
            </Field>
          </div>
          <label className="check" style={{ marginTop: 12 }}>
            <input type="checkbox" checked={dummy} onChange={(event) => setDummy(event.target.checked)} />
            <span>
              <strong>Demo weights</strong> — skip TensorFlow and send dummy model weights.
            </span>
          </label>
          <div className="toolbar" style={{ marginTop: 14 }}>
            <button
              className="btn btn-primary"
              type="button"
              disabled={action.pending}
              onClick={() =>
                void run(
                  "/api/workers/launch",
                  { count: workerCount, role, simulation: true, dummy, prefix: "sim" },
                  `Launched ${workerCount} simulated worker${workerCount === 1 ? "" : "s"}`,
                )
              }
            >
              Launch workers
            </button>
            <button
              className="btn btn-danger"
              type="button"
              disabled={action.pending}
              onClick={() => void run("/api/workers/stop", {}, "All workers stopped")}
            >
              Stop all workers
            </button>
          </div>
        </Panel>

        <Panel title="Worker processes" subtitle="Child processes managed by the API" bodyTight>
          {processList.length === 0 ? (
            <Empty title="No child processes" hint="Launch workers to see broker, coordinator, and worker processes here." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Process</th>
                    <th>Kind</th>
                    <th>State</th>
                    <th className="right">PID</th>
                  </tr>
                </thead>
                <tbody>
                  {processList.map((process) => (
                    <tr key={`${process.kind}-${process.name}`}>
                      <td className="primary mono">{process.name}</td>
                      <td>{process.kind}</td>
                      <td>
                        <StatusBadge status={process.running ? "running" : "stopped"} />
                      </td>
                      <td className="num">{process.pid || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      {(workers.data?.workers.length ?? 0) > 0 && (
        <Panel title="Registered workers" subtitle="MQTT registration and heartbeat state" bodyTight>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Worker</th>
                  <th>Role</th>
                  <th>Dataset</th>
                  <th>State</th>
                  <th>Model</th>
                  <th className="right">Samples</th>
                  <th className="right">Last seen</th>
                </tr>
              </thead>
              <tbody>
                {workers.data?.workers.map((worker) => (
                  <tr key={worker.worker_id}>
                    <td className="primary mono">{worker.worker_id}</td>
                    <td>{worker.role}</td>
                    <td>{worker.dataset}</td>
                    <td>
                      <Badge tone={worker.online ? "ok" : "bad"}>
                        <Dot tone={worker.online ? "ok" : "bad"} />
                        {worker.state ?? worker.status}
                      </Badge>
                    </td>
                    <td className="mono">{worker.model_version ?? "—"}</td>
                    <td className="num">{worker.n_samples}</td>
                    <td className="num">{relativeTime(worker.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}

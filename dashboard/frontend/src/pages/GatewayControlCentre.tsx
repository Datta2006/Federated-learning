import { useState } from "react";
import { usePoll } from "../hooks/usePoll";
import { useAction } from "../hooks/useAction";
import type { GatewayFlPayload } from "../types";
import { formatBytes, formatNumber, relativeTime } from "../lib/format";
import { Badge, Dot, Empty, Field, Panel, Stat } from "../components/primitives";

export function GatewayControlCentrePage() {
  const poll = usePoll<GatewayFlPayload>("/api/fl/gateways", 5000);
  const action = useAction();
  const [count, setCount] = useState(3);
  const [windowHours, setWindowHours] = useState(24);
  const [message, setMessage] = useState<string | null>(null);

  const data = poll.data;
  const gateways = data?.gateways ?? [];
  const online = gateways.filter((gateway) => gateway.online).length;
  const last = data?.last_round ?? null;

  const start = async () => {
    setMessage(null);
    const result = await action.run("/api/fl/gateways/start", {
      gateway_count: count,
      window_hours: windowHours,
    });
    if (result) {
      setMessage(`Started ${count} gateway client${count === 1 ? "" : "s"}`);
      poll.refresh();
    }
  };

  const stop = async () => {
    setMessage(null);
    const result = await action.run("/api/fl/gateways/stop", {});
    if (result) {
      setMessage("Gateway clients stopped");
      poll.refresh();
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Federated gateways</h1>
          <p className="page-sub">
            Gateway clients join the coordinator as independent FL clients with private data shards.
            A client is live only when the resumed MQTT state says so.
          </p>
        </div>
        <div className="toolbar">
          <Badge tone={online > 0 ? "ok" : "neutral"}>
            <Dot tone={online > 0 ? "ok" : "neutral"} />
            {online} online
          </Badge>
          <button className="btn btn-sm" type="button" onClick={poll.refresh}>
            Refresh
          </button>
        </div>
      </div>

      {action.error && <div className="notice notice-bad">{action.error}</div>}
      {message && <div className="notice notice-ok">{message}</div>}
      {poll.error && <div className="notice notice-bad">Gateway API: {poll.error}</div>}

      <div className="stat-grid">
        <Stat label="Gateway clients" value={data?.count ?? gateways.length} sub={`${online} online`} />
        <Stat
          label="Latest model"
          value={data?.latest_model?.model_version ?? "—"}
          sub={data?.latest_model ? `round ${data.latest_model.round ?? "—"}` : "no model yet"}
        />
        <Stat label="Registry rounds" value={data?.round_count ?? "—"} sub="recorded by coordinator" />
        <Stat
          label="Last round loss"
          value={last?.weighted_val_loss === null || last?.weighted_val_loss === undefined ? "—" : formatNumber(last.weighted_val_loss, 4)}
          sub={last ? `round ${last.round}` : "no round summary"}
        />
      </div>

      <div className="cols">
        <Panel
          title="Gateway clients"
          subtitle={data?.note ?? "Joined simulator state and live MQTT heartbeats."}
          bodyTight
          actions={<span className="tiny faint">{gateways.length} clients</span>}
        >
          {gateways.length === 0 ? (
            <Empty
              title="No gateway clients running"
              hint="Start gateway clients below. They will register with the coordinator over MQTT and appear here."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Gateway</th>
                    <th>Worker</th>
                    <th>State</th>
                    <th>Years</th>
                    <th className="right">Samples</th>
                    <th className="right">Round</th>
                    <th className="right">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {gateways.map((gateway) => (
                    <tr key={gateway.gateway_id}>
                      <td className="primary mono">{gateway.gateway_id}</td>
                      <td className="mono">{gateway.worker_id}</td>
                      <td>
                        <Badge tone={gateway.online ? "ok" : "bad"}>
                          <Dot tone={gateway.online ? "ok" : "bad"} />
                          {gateway.live_state ?? gateway.state}
                        </Badge>
                      </td>
                      <td className="mono">{gateway.years?.join(", ") || "—"}</td>
                      <td className="num">{formatNumber(gateway.n_samples, 0)}</td>
                      <td className="num">{gateway.current_round ?? "—"}</td>
                      <td className="num">
                        {gateway.aggregation_weight === null || gateway.aggregation_weight === undefined
                          ? "—"
                          : formatNumber(gateway.aggregation_weight, 3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Start or stop clients" subtitle="POSTed to the simulator FL client manager.">
          <div className="form-grid" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
            <Field label="Client count">
              <input
                className="input"
                type="number"
                min={1}
                max={20}
                value={count}
                onChange={(event) => setCount(Number(event.target.value))}
              />
            </Field>
            <Field label="Window (hours)">
              <input
                className="input"
                type="number"
                min={1}
                max={168}
                value={windowHours}
                onChange={(event) => setWindowHours(Number(event.target.value))}
              />
            </Field>
          </div>
          <div className="toolbar" style={{ marginTop: 14 }}>
            <button className="btn btn-primary" type="button" disabled={action.pending} onClick={() => void start()}>
              Start clients
            </button>
            <button className="btn btn-danger" type="button" disabled={action.pending} onClick={() => void stop()}>
              Stop clients
            </button>
          </div>
          <div className="notice" style={{ marginTop: 14 }}>
            Gateway clients connect to the same broker as the coordinator. Start the broker and
            coordinator first in the Simulation Lab if they are not running.
          </div>
        </Panel>
      </div>

      <div className="cols-2">
        <Panel title="Last round" subtitle="Summary reported by the coordinator" bodyTight>
          {!last ? (
            <Empty title="No round summary yet" hint="A gateway round appears after clients train and upload once." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Round</th>
                    <th>Status</th>
                    <th className="right">Selected</th>
                    <th className="right">Accepted</th>
                    <th className="right">Loss</th>
                    <th className="right">Bytes up</th>
                    <th className="right">Seconds</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="primary mono">{last.round}</td>
                    <td>{last.status}</td>
                    <td className="num">{last.selected?.length ?? 0}</td>
                    <td className="num">{last.accepted?.length ?? 0}</td>
                    <td className="num">{formatNumber(last.weighted_val_loss, 4)}</td>
                    <td className="num">{formatBytes(last.bytes_up)}</td>
                    <td className="num">{formatNumber(last.seconds, 1)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Partitions" subtitle="Configured gateway shard partitions" bodyTight>
          {!data?.partitions || Object.keys(data.partitions).length === 0 ? (
            <Empty title="No partitions configured" hint="Partitions are reported by the simulator FL engine." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Gateway</th>
                    <th className="right">Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.partitions).map(([name, samples]) => (
                    <tr key={name}>
                      <td className="primary mono">{name}</td>
                      <td className="num">{formatNumber(samples, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Recent contributions" subtitle="From the most recent round summary" bodyTight>
        {!last?.contributions?.length ? (
          <Empty title="No contributions recorded" hint="The coordinator reports contribution weights per client." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Node</th>
                  <th className="right">Samples</th>
                  <th className="right">Val samples</th>
                  <th className="right">Val loss</th>
                  <th className="right">Weight</th>
                </tr>
              </thead>
              <tbody>
                {last.contributions.map((row) => (
                  <tr key={row.node_id}>
                    <td className="primary mono">{row.node_id}</td>
                    <td className="num">{row.n_samples}</td>
                    <td className="num">{row.n_val}</td>
                    <td className="num">{formatNumber(row.val_loss, 4)}</td>
                    <td className="num">{formatNumber(row.weight, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {last?.observed_at ? (
          <div className="panel-foot">observed {relativeTime(new Date(last.observed_at * 1000).toISOString())}</div>
        ) : null}
      </Panel>
    </div>
  );
}

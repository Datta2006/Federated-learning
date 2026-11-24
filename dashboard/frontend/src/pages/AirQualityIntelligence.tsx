import { useState } from "react";
import { usePoll } from "../hooks/usePoll";
import type { AirQualityPayload } from "../types";
import { formatNumber, formatTime, relativeTime } from "../lib/format";
import { ChartLegend, LineChart } from "../components/charts/LineChart";
import { Badge, Empty, Panel, Stat } from "../components/primitives";

function lastValue(points: AirQualityPayload["series"], key: "actual" | "predicted" | "temp" | "rh") {
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const point = points[index];
    if (point && point[key] !== null && point[key] !== undefined) return point[key];
  }
  return null;
}

export function AirQualityIntelligencePage() {
  const [node, setNode] = useState<string>("");
  const query = node ? `/api/air-quality?limit=240&node=${encodeURIComponent(node)}` : "/api/air-quality?limit=240";
  const poll = usePoll<AirQualityPayload>(query, 10000);

  const data = poll.data;
  const points = data?.series ?? [];
  const nodes = data?.available_nodes ?? [];
  const actual = lastValue(points, "actual");
  const predicted = lastValue(points, "predicted");
  const temp = lastValue(points, "temp");
  const rh = lastValue(points, "rh");
  const units = data?.units ?? { pm25: "µg/m³", temp: "°C", rh: "%" };

  const series = [
    { name: "Actual PM2.5", color: "var(--ink-2)", values: points.map((point) => point.actual) },
    { name: "Predicted PM2.5", color: "var(--accent)", values: points.map((point) => point.predicted), dashed: true },
  ];
  const labels = points.map((point) => formatTime(point.ts));

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Air quality</h1>
          <p className="page-sub">
            Historical observations and predictions for one node. Predictions are offline FedAvg (or
            the persistence reference) for the replay window — not a live sensor feed.
          </p>
        </div>
        <div className="toolbar">
          <label className="field" style={{ minWidth: 180 }}>
            <span className="field-label">Node</span>
            <select className="select" value={node || data?.node || ""} onChange={(event) => setNode(event.target.value)}>
              {nodes.length === 0 && data?.node && <option value={data.node}>{data.node}</option>}
              {nodes.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id} · {item.year}
                  {item.predictions_available ? " · predictions" : ""}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-sm" type="button" onClick={poll.refresh} style={{ marginTop: 16 }}>
            Refresh
          </button>
        </div>
      </div>

      {poll.error && <div className="notice notice-bad">Air-quality API: {poll.error}</div>}
      {data?.prediction_stale && (
        <div className="notice notice-warn">The prediction artifact is stale relative to the latest model version.</div>
      )}

      <div className="stat-grid">
        <Stat label="Actual PM2.5" value={actual === null ? "—" : formatNumber(actual, 1)} sub={units.pm25} />
        <Stat label="Predicted PM2.5" value={predicted === null ? "—" : formatNumber(predicted, 1)} sub={data?.prediction_label ?? "no prediction"} />
        <Stat label="Temperature" value={temp === null ? "—" : formatNumber(temp, 1)} sub={units.temp} />
        <Stat label="Humidity" value={rh === null ? "—" : formatNumber(rh, 1)} sub={units.rh} />
      </div>

      <Panel
        title={`Node ${data?.node ?? "—"} · ${data?.year ?? "—"}`}
        subtitle={data?.prediction_source ? `prediction source: ${data.prediction_source}` : "Waiting for the air-quality API"}
        actions={
          data ? (
            <Badge tone={data.prediction_source === "fedavg_offline" ? "accent" : "neutral"}>
              {data.prediction_source ?? "unknown"}
            </Badge>
          ) : null
        }
        footer={data?.actual_note}
      >
        {points.length === 0 ? (
          <Empty title="No series returned" hint="The dataset or prediction artifacts are not available for this node." />
        ) : (
          <>
            <ChartLegend series={series} />
            <LineChart series={series} labels={labels} caption={`PM2.5 for ${data?.node ?? "node"}`} />
          </>
        )}
      </Panel>

      <div className="cols">
        <Panel title="Recent points" subtitle="Last ten rows of the returned series" bodyTight>
          {points.length === 0 ? (
            <Empty title="No rows" hint="Nothing to display." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th className="right">Actual</th>
                    <th className="right">Filled</th>
                    <th className="right">Predicted</th>
                    <th className="right">Temp</th>
                    <th className="right">RH</th>
                  </tr>
                </thead>
                <tbody>
                  {points.slice(-10).reverse().map((point) => (
                    <tr key={point.ts}>
                      <td className="mono">{formatTime(point.ts)}</td>
                      <td className="num">{formatNumber(point.actual, 1)}</td>
                      <td className="num">{formatNumber(point.actual_filled, 1)}</td>
                      <td className="num">{formatNumber(point.predicted, 1)}</td>
                      <td className="num">{formatNumber(point.temp, 1)}</td>
                      <td className="num">{formatNumber(point.rh, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Provenance" subtitle="What this view is and is not">
          {!data ? (
            <Empty title="No metadata" hint="The API did not return a payload." />
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              <dl className="kv">
                <div><dt>Node</dt><dd className="mono">{data.node}</dd></div>
                <div><dt>Year</dt><dd className="mono">{data.year}</dd></div>
                <div><dt>Mode</dt><dd className="mono">{data.mode}</dd></div>
                <div><dt>Dataset</dt><dd className="mono small">{data.dataset?.name}</dd></div>
                <div><dt>Range</dt><dd className="mono small">{data.range?.points ?? 0} points</dd></div>
                <div><dt>Model version</dt><dd className="mono">{data.latest_model_version ?? "—"}</dd></div>
                <div><dt>Prediction</dt><dd>{data.prediction_label}</dd></div>
                <div><dt>Artifact age</dt><dd>{data.predictions?.created_utc ? relativeTime(data.predictions.created_utc) : "—"}</dd></div>
              </dl>
              <p className="small muted">{data.note}</p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

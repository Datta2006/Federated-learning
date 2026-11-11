import { useState } from "react";
import { CloudSun, Droplets, RefreshCw, Thermometer, Wind } from "lucide-react";
import { useApi } from "../lib/useApi";
import { formatDateTime, formatNumber, titleCase } from "../lib/format";
import type { AirQualityPayload } from "../types";
import {
  Badge,
  EmptyState,
  ErrorState,
  Kpi,
  PageSkeleton,
  Panel,
  PanelHeader,
  SourceTag,
  SummaryRow,
} from "../components/ui";
import { LineChart } from "../components/LineChart";

export function AirQualityPage() {
  const [node, setNode] = useState<string | null>(null);
  const query = `/api/air-quality?limit=240${node ? `&node=${encodeURIComponent(node)}` : ""}`;
  const air = useApi<AirQualityPayload>(query, 15000);

  if (air.loading && !air.data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <PageSkeleton rows={2} />
      </div>
    );
  }
  if (air.error && !air.data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <ErrorState message={air.error} onRetry={air.refresh} />
      </div>
    );
  }
  if (!air.data) return null;

  const data = air.data;
  const series = data.series;
  const points = series.map((point) => ({
    x: new Date(point.ts).getTime(),
    actual: point.actual_filled ?? point.actual,
    predicted: point.predicted,
    temp: point.temp,
    rh: point.rh,
    ts: point.ts,
  }));
  const actualValues = points.map((point) => ({ x: point.x, y: point.actual }));
  const predictedValues = points.map((point) => ({ x: point.x, y: point.predicted }));
  const latest = points[points.length - 1];
  const xLabels = points.length
    ? [points[0].ts, points[Math.floor(points.length / 2)].ts, points[points.length - 1].ts].map((value) =>
        new Date(value).toLocaleDateString(undefined, { month: "short", day: "2-digit" }),
      )
    : [];

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 pb-10 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <SourceTag kind="offline">historical replay</SourceTag>
          <Badge tone={data.prediction_source === "fedavg_offline" ? "emerald" : "amber"}>
            {data.prediction_label}
          </Badge>
          {data.prediction_stale ? <Badge tone="amber">model older than data</Badge> : null}
        </div>
        <div className="flex items-center gap-2">
          <select
            className="input w-auto py-1"
            value={node ?? data.node}
            onChange={(event) => setNode(event.target.value)}
          >
            {data.available_nodes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} · {item.year}
              </option>
            ))}
          </select>
          <button type="button" className="btn" onClick={air.refresh}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Latest PM2.5"
          value={latest?.actual === null || latest?.actual === undefined ? "—" : formatNumber(latest.actual, 1)}
          hint={`${data.units.pm25} · observed`}
          icon={<Wind size={15} />}
          tone="blue"
        />
        <Kpi
          label="Model prediction"
          value={latest?.predicted === null || latest?.predicted === undefined ? "—" : formatNumber(latest.predicted, 1)}
          hint={data.model_version ? `model ${data.model_version}` : "no model prediction"}
          icon={<CloudSun size={15} />}
          tone="violet"
        />
        <Kpi
          label="Temperature"
          value={latest?.temp === null || latest?.temp === undefined ? "—" : formatNumber(latest.temp, 1)}
          hint={data.units.temp}
          icon={<Thermometer size={15} />}
          tone="amber"
        />
        <Kpi
          label="Humidity"
          value={latest?.rh === null || latest?.rh === undefined ? "—" : formatNumber(latest.rh, 1)}
          hint={data.units.rh}
          icon={<Droplets size={15} />}
          tone="emerald"
        />
      </div>

      {series.length === 0 ? (
        <Panel>
          <EmptyState
            title="No replay points"
            message="The dataset or prediction file did not yield a series for this node. Check the air-quality settings and data path."
          />
        </Panel>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel>
            <PanelHeader
              title="Observed PM2.5"
              subtitle={`${data.node} · ${titleCase(data.prediction_source)} · ${data.range.points} replay points`}
              icon={<Wind size={15} />}
            />
            <div className="px-4 pb-4 pt-3">
              <LineChart values={actualValues} yLabel={data.units.pm25} tone="#60a5fa" xLabels={xLabels} />
            </div>
          </Panel>
          <Panel>
            <PanelHeader
              title="Federated prediction"
              subtitle={data.predictions.available ? `source: ${data.predictions.source}` : "No prediction file"}
              icon={<CloudSun size={15} />}
            />
            <div className="px-4 pb-4 pt-3">
              <LineChart values={predictedValues} yLabel={data.units.pm25} tone="#a78bfa" xLabels={xLabels} />
            </div>
          </Panel>
        </div>
      )}

      <Panel>
        <PanelHeader title="Provenance" subtitle="What this view does and does not claim." icon={<CloudSun size={15} />} />
        <div className="grid gap-3 px-5 pb-5 pt-3 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryRow label="node" value={data.node} />
          <SummaryRow label="year" value={data.year} />
          <SummaryRow label="range start" value={formatDateTime(data.range.start)} />
          <SummaryRow label="range end" value={formatDateTime(data.range.end)} />
        </div>
        <p className="px-5 pb-5 text-[11px] leading-relaxed text-mist-500">{data.note}</p>
        <p className="px-5 pb-5 text-[11px] leading-relaxed text-mist-500">{data.actual_note}</p>
        <div className="flex flex-wrap gap-1.5 px-5 pb-5">
          {data.available_nodes.map((item) => (
            <Badge key={item.id} tone={item.predictions_available ? "emerald" : "mist"}>
              {item.id}: {item.predictions_available ? "predictions" : "observed only"}
            </Badge>
          ))}
        </div>
      </Panel>
    </div>
  );
}

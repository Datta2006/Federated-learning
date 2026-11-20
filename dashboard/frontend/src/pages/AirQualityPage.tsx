import { useState } from "react";
import { Wind } from "lucide-react";
import { useApi } from "../lib/useApi";
import type { AirQualityPayload, AirPoint } from "../types";
import {
  Badge,
  DataRow,
  EmptyState,
  Metric,
  Panel,
  PanelHead,
  PageTitle,
} from "../components/ui";
import { formatDateTime, formatNumber, formatTime } from "../lib/format";

function SeriesChart({ points }: { points: AirPoint[] }) {
  const width = 900;
  const height = 240;
  const pad = 8;
  const values = points
    .flatMap((point) => [point.actual, point.predicted])
    .filter((value): value is number => value !== null);
  if (points.length < 2 || values.length < 2) {
    return (
      <div className="flex h-56 items-center justify-center text-[11px] text-ink-500">
        Not enough replay points to draw a series.
      </div>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = (width - pad * 2) / (points.length - 1);
  const pathFor = (key: "actual" | "predicted") => {
    let drawing = false;
    return points
      .map((point, index) => {
        const value = point[key];
        if (value === null) {
          drawing = false;
          return "";
        }
        const x = pad + index * step;
        const y = height - pad - ((value - min) / span) * (height - pad * 2);
        const command = drawing ? "L" : "M";
        drawing = true;
        return `${command}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  };
  return (
    <div className="overflow-hidden">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-60 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label="Observed and predicted PM2.5"
      >
        {[0.25, 0.5, 0.75].map((fraction) => (
          <line
            key={fraction}
            x1={0}
            x2={width}
            y1={height * fraction}
            y2={height * fraction}
            stroke="#23272c"
            strokeWidth={1}
          />
        ))}
        <path d={pathFor("actual")} fill="none" stroke="#7cb8e8" strokeWidth={1.4} />
        <path d={pathFor("predicted")} fill="none" stroke="#f5a524" strokeWidth={1.4} />
      </svg>
      <div className="flex items-center gap-4 px-4 pb-3 text-2xs text-ink-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-info" /> observed
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-accent" /> predicted
        </span>
        <span className="ml-auto mono">
          {formatTime(points[0]?.ts)} → {formatTime(points[points.length - 1]?.ts)}
        </span>
      </div>
    </div>
  );
}

export function AirQualityPage() {
  const [node, setNode] = useState<string | undefined>(undefined);
  const query = `/api/air-quality?limit=240${node ? `&node=${encodeURIComponent(node)}` : ""}`;
  const { data, error } = useApi<AirQualityPayload>(query, 30000);

  const series = data?.series ?? [];
  const last = [...series].reverse().find((point) => point.actual !== null);
  const lastPrediction = [...series].reverse().find((point) => point.predicted !== null);

  return (
    <div className="space-y-5">
      <PageTitle
        title="Air quality"
        description="Historical PM2.5 replay from the Beijing dataset. Predictions are labelled by source; this is not a live sensor feed."
        meta={
          <>
            {data ? (
              <Badge tone={data.prediction_source === "fedavg_offline" ? "ok" : "warn"}>
                {data.prediction_label}
              </Badge>
            ) : null}
            <select
              className="input w-32 py-1"
              value={node ?? data?.node ?? ""}
              onChange={(event) => setNode(event.target.value)}
              aria-label="Air-quality node"
            >
              {(data?.available_nodes ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id} · {item.year}
                </option>
              ))}
            </select>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-panel border border-line bg-line lg:grid-cols-4">
        <Metric
          label="Latest observed"
          value={formatNumber(last?.actual, 1)}
          hint={last ? `${data?.units.pm25 ?? "µg/m³"} · ${formatDateTime(last.ts)}` : "no observation"}
          tone="info"
        />
        <Metric
          label="Latest prediction"
          value={formatNumber(lastPrediction?.predicted, 1)}
          hint={data?.model_version ? `model ${data.model_version}` : "reference baseline"}
          tone="accent"
        />
        <Metric
          label="Temperature"
          value={formatNumber(last?.temp, 1)}
          hint={data?.units.temp ?? "°C"}
        />
        <Metric
          label="Humidity"
          value={formatNumber(last?.rh, 0)}
          hint={data?.units.rh ?? "%"}
        />
      </div>

      <Panel>
        <PanelHead
          title={`${data?.node ?? "node"} · PM2.5 replay`}
          subtitle={
            data
              ? `${data.range.points} points · ${formatDateTime(data.range.start)} → ${formatDateTime(data.range.end)}`
              : "Loading series…"
          }
          icon={<Wind size={14} />}
        />
        {series.length === 0 ? (
          <EmptyState
            title="No series for this node"
            message={error ?? "The dataset or prediction export did not yield rows for this node."}
          />
        ) : (
          <SeriesChart points={series} />
        )}
      </Panel>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHead title="Prediction provenance" />
          <div className="space-y-3 p-4">
            <p className="text-[12px] leading-relaxed text-ink-300">{data?.note}</p>
            <p className="text-[11px] leading-relaxed text-ink-500">{data?.actual_note}</p>
            {data?.prediction_stale ? (
              <p className="rounded border border-warn/30 bg-warn-soft px-3 py-2 text-[11px] text-warn-text">
                The active model version is newer than the prediction export. Treat this
                series as historical, not as the output of the latest model.
              </p>
            ) : null}
          </div>
        </Panel>
        <Panel>
          <PanelHead title="Series facts" />
          <div className="p-4">
            <DataRow label="node" value={data?.node ?? "—"} />
            <DataRow label="dataset" value={data?.dataset.name ?? "—"} mono={false} />
            <DataRow label="mode" value={data?.mode ?? "—"} />
            <DataRow label="prediction source" value={data?.prediction_source ?? "—"} mono={false} />
            <DataRow label="model version" value={data?.model_version ?? "—"} />
            <DataRow label="horizon" value={data?.predictions.horizon_hours ? `${data.predictions.horizon_hours}h` : "—"} />
          </div>
        </Panel>
      </div>
    </div>
  );
}

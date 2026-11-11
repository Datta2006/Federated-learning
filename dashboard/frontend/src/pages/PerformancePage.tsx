import { useState } from "react";
import { BarChart3, Boxes, RefreshCw, Trophy } from "lucide-react";
import { useApi } from "../lib/useApi";
import {
  formatDateTime,
  formatInteger,
  formatNumber,
  formatR2,
} from "../lib/format";
import type { MetricsPayload, ModelPayload } from "../types";
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

type SortKey = "rmse_raw_mean" | "mae_raw_mean" | "r2_raw_mean";

export function PerformancePage() {
  const metrics = useApi<MetricsPayload>("/api/metrics", 10000);
  const model = useApi<ModelPayload>("/api/model", 10000);
  const [sortKey, setSortKey] = useState<SortKey>("rmse_raw_mean");

  if (metrics.loading && !metrics.data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <PageSkeleton rows={2} />
      </div>
    );
  }
  if (metrics.error && !metrics.data) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <ErrorState message={metrics.error} onRetry={metrics.refresh} />
      </div>
    );
  }
  if (!metrics.data) return null;

  const data = metrics.data;
  const rows = [...data.comparison].sort((a, b) => {
    const left = a[sortKey] ?? Number.POSITIVE_INFINITY;
    const right = b[sortKey] ?? Number.POSITIVE_INFINITY;
    return sortKey === "r2_raw_mean" ? right - left : left - right;
  });
  const best = data.comparison.find((row) => row.requested_method === "ours_federated") ??
    data.comparison.find((row) => row.method === "federated") ??
    data.comparison[0];
  const lossPoints = data.loss_history
    .filter((row) => row.weighted_val_loss !== null)
    .map((row) => ({ x: row.round, y: row.weighted_val_loss }));

  return (
    <div className="mx-auto max-w-6xl space-y-4 px-4 pb-10 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SourceTag kind="offline">stage 4 evaluation</SourceTag>
          <Badge tone={data.available ? "emerald" : "amber"}>
            {data.available ? "results available" : "no results file"}
          </Badge>
        </div>
        <button type="button" className="btn" onClick={metrics.refresh}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Headline"
          value={data.headline || "—"}
          hint={data.notes}
          icon={<Trophy size={15} />}
          tone="violet"
        />
        <Kpi
          label="Methods compared"
          value={formatInteger(data.comparison.length)}
          hint={`${data.all_methods.length} total, ${data.seed_results.length} seed runs`}
          icon={<BarChart3 size={15} />}
          tone="blue"
        />
        <Kpi
          label="Federated RMSE"
          value={best ? formatNumber(best.rmse_raw_mean, 3) : "—"}
          hint={best ? `${best.label} · MAE ${formatNumber(best.mae_raw_mean, 3)}` : "—"}
          icon={<Boxes size={15} />}
          tone="emerald"
        />
        <Kpi
          label="Latest federated loss"
          value={formatNumber(data.loss_summary.latest, 6)}
          hint={data.loss_summary.note}
          icon={<Trophy size={15} />}
          tone="amber"
        />
      </div>

      <Panel>
        <PanelHeader
          title="Validation loss per federated round"
          subtitle="Comes from the coordinator registry, not from the dashboard. Missing rounds stay gaps."
          icon={<BarChart3 size={15} />}
        />
        <div className="px-4 pb-4 pt-3">
          <LineChart
            values={lossPoints}
            yLabel="weighted validation loss"
            tone="#f59e0b"
            xLabels={lossPoints.length ? [String(lossPoints[0].x), String(lossPoints[lossPoints.length - 1].x)] : []}
          />
        </div>
      </Panel>

      <Panel className="overflow-hidden">
        <PanelHeader
          title="Method comparison"
          subtitle="Offline Stage 4 results by seed. Click a metric to sort."
          icon={<BarChart3 size={15} />}
          action={
            <select className="input w-auto py-1" value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
              <option value="rmse_raw_mean">sort by RMSE</option>
              <option value="mae_raw_mean">sort by MAE</option>
              <option value="r2_raw_mean">sort by R²</option>
            </select>
          }
        />
        {rows.length === 0 ? (
          <EmptyState
            title="No comparison results"
            message="Run the Stage 4 evaluation to populate results.csv, then reload this page."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px]">
              <thead className="border-y border-ink-700/70 bg-ink-800/40 text-mist-500">
                <tr>
                  <th className="px-4 py-2 font-medium">method</th>
                  <th className="px-3 py-2 font-medium">RMSE (raw)</th>
                  <th className="px-3 py-2 font-medium">MAE (raw)</th>
                  <th className="px-3 py-2 font-medium">R² (raw)</th>
                  <th className="px-3 py-2 font-medium">RMSE (clipped)</th>
                  <th className="px-3 py-2 font-medium">seeds</th>
                  <th className="px-3 py-2 font-medium">params</th>
                  <th className="px-3 py-2 font-medium">train time</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.method}-${row.requested_method}`} className="border-b border-ink-700/40 last:border-0">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: row.color || "#64748b" }} />
                        <span className="font-medium text-mist-100">{row.label}</span>
                      </div>
                      <div className="text-[10px] text-mist-500">{row.description}</div>
                    </td>
                    <td className="px-3 py-2.5 mono text-mist-200">
                      {formatNumber(row.rmse_raw_mean, 3)}
                      {row.rmse_raw_std !== null ? <span className="text-mist-500"> ± {formatNumber(row.rmse_raw_std, 3)}</span> : null}
                    </td>
                    <td className="px-3 py-2.5 mono text-mist-300">{formatNumber(row.mae_raw_mean, 3)}</td>
                    <td className="px-3 py-2.5 mono text-mist-300">{formatR2(row.r2_raw_mean)}</td>
                    <td className="px-3 py-2.5 mono text-mist-300">{formatNumber(row.rmse_clipped_mean, 3)}</td>
                    <td className="px-3 py-2.5 mono text-mist-300">{row.n_seeds ?? "—"}</td>
                    <td className="px-3 py-2.5 mono text-mist-300">{formatInteger(row.parameters)}</td>
                    <td className="px-3 py-2.5 mono text-mist-300">
                      {row.train_seconds_mean === null ? "—" : `${formatNumber(row.train_seconds_mean, 1)} s`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel>
        <PanelHeader
          title="Model registry"
          subtitle="latest.json / best.json written by the coordinator. Best = lowest weighted validation loss."
          icon={<Boxes size={15} />}
          action={<button type="button" className="btn" onClick={model.refresh}><RefreshCw size={13} /> Refresh</button>}
        />
        {model.data ? (
          <>
            <div className="grid gap-3 px-5 pb-3 pt-3 sm:grid-cols-2 lg:grid-cols-4">
              <SummaryRow label="registry source" value={model.data.source ?? "—"} />
              <SummaryRow label="rounds" value={formatInteger(model.data.round_count)} />
              <SummaryRow label="current round" value={formatInteger(model.data.current_round)} />
              <SummaryRow label="parameters" value={formatInteger(model.data.transfer.parameters)} />
            </div>
            <div className="grid gap-3 px-5 pb-5 sm:grid-cols-2">
              <div className="rounded-lg border border-ink-700/60 bg-ink-800/40 px-3 py-2.5">
                <div className="label">latest</div>
                <div className="mono mt-1 text-sm text-mist-100">{model.data.latest?.model_version ?? "—"}</div>
                <div className="mt-1 text-[11px] text-mist-500">
                  round {model.data.latest?.round ?? "—"} · loss {formatNumber(model.data.latest?.weighted_val_loss, 6)} ·{" "}
                  {formatDateTime(model.data.latest?.created_utc)}
                </div>
              </div>
              <div className="rounded-lg border border-ink-700/60 bg-ink-800/40 px-3 py-2.5">
                <div className="label">best</div>
                <div className="mono mt-1 text-sm text-signal-emerald">{model.data.best?.model_version ?? "—"}</div>
                <div className="mt-1 text-[11px] text-mist-500">
                  round {model.data.best?.round ?? "—"} · loss {formatNumber(model.data.best?.weighted_val_loss, 6)} ·{" "}
                  {formatDateTime(model.data.best?.created_utc)}
                </div>
              </div>
            </div>
          </>
        ) : (
          <p className="px-5 py-4 text-[12px] text-mist-500">Model registry unavailable.</p>
        )}
      </Panel>
    </div>
  );
}

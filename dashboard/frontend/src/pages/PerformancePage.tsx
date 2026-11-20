import { useMemo } from "react";
import { BarChart3, FlaskConical, LineChart as LineIcon, Target } from "lucide-react";
import { useApi } from "../lib/useApi";
import type { MetricsPayload } from "../types";
import {
  Badge,
  EmptyState,
  Metric,
  Panel,
  PanelHead,
  PageTitle,
  Sparkline,
  StatusPill,
} from "../components/ui";
import { formatNumber } from "../lib/format";

export function PerformancePage() {
  const { data, error } = useApi<MetricsPayload>("/api/metrics", 15000);

  const rows = data?.comparison ?? [];
  const best = useMemo(() => {
    const scored = rows.filter((row) => row.rmse_clipped_mean !== null);
    if (scored.length === 0) return null;
    return scored.reduce((winner, row) =>
      (row.rmse_clipped_mean ?? Infinity) < (winner.rmse_clipped_mean ?? Infinity)
        ? row
        : winner,
    );
  }, [rows]);

  return (
    <div className="space-y-5">
      <PageTitle
        title="Performance"
        description="Offline evaluation from the project's existing experiment files. These are not live training metrics and are never recomputed in the browser."
        meta={
          <Badge tone={data?.available ? "ok" : "neutral"}>
            {data?.available ? "artifacts found" : "artifacts missing"}
          </Badge>
        }
      />

      {data?.headline ? (
        <div className="rounded-panel border border-line bg-panel px-4 py-3 text-[12px] text-ink-300">
          {data.headline}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <Panel>
          <PanelHead title="Best baseline" icon={<Target size={14} />} />
          <div className="p-4">
            <div className="text-[15px] text-ink-100">{best?.label ?? "—"}</div>
            <div className="mt-2 grid grid-cols-3 gap-2">
              <div>
                <div className="label">RMSE</div>
                <div className="mono mt-1 text-[13px] text-ink-200">
                  {formatNumber(best?.rmse_clipped_mean, 3)}
                </div>
              </div>
              <div>
                <div className="label">MAE</div>
                <div className="mono mt-1 text-[13px] text-ink-200">
                  {formatNumber(best?.mae_clipped_mean, 3)}
                </div>
              </div>
              <div>
                <div className="label">R²</div>
                <div className="mono mt-1 text-[13px] text-ink-200">
                  {formatNumber(best?.r2_clipped_mean, 4)}
                </div>
              </div>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-500">
              {best?.description ?? "No comparison rows were available."}
            </p>
          </div>
        </Panel>

        <Panel>
          <PanelHead title="Federated validation loss" icon={<LineIcon size={14} />} />
          <div className="p-4">
            <Sparkline
              values={(data?.loss_history ?? []).map((row) => row.weighted_val_loss)}
              width={280}
              height={56}
            />
            <div className="mt-3 flex items-baseline justify-between text-[11px]">
              <span className="text-ink-500">latest</span>
              <span className="mono text-ink-200">
                {formatNumber(data?.loss_summary.latest, 6)}
              </span>
            </div>
            <div className="mt-1 flex items-baseline justify-between text-[11px]">
              <span className="text-ink-500">best</span>
              <span className="mono text-ok-text">
                {formatNumber(data?.loss_summary.best, 6)}
              </span>
            </div>
            <p className="mt-3 text-[11px] text-ink-500">{data?.loss_summary.note}</p>
          </div>
        </Panel>

        <Panel>
          <PanelHead title="Artifact sources" icon={<FlaskConical size={14} />} />
          <div className="space-y-2 p-4 text-[11px]">
            {Object.entries(
              (data?.sources ?? {}) as Record<string, string | null>,
            ).map(([name, path]) => (
              <div key={name} className="flex items-start justify-between gap-3">
                <span className="text-ink-500">{name}</span>
                <span className="mono truncate text-right text-ink-400" title={path ?? ""}>
                  {path ?? "missing"}
                </span>
              </div>
            ))}
            <StatusPill
              status={data?.active_registry.latest_model_version ? "complete" : "pending"}
              label={`active registry ${data?.active_registry.latest_model_version ?? "none"}`}
            />
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHead
          title="Method comparison"
          subtitle="Mean across seeds. Clipped metrics are the paper's evaluation convention."
          icon={<BarChart3 size={14} />}
        />
        {rows.length === 0 ? (
          <EmptyState
            title="No comparison data"
            message="results.csv and results_by_seed.csv were not found. The dashboard will not invent benchmark numbers."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[11px]">
              <thead>
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                  <th className="px-4 py-2 font-medium">Method</th>
                  <th className="px-4 py-2 text-right font-medium">Seeds</th>
                  <th className="px-4 py-2 text-right font-medium">RMSE (raw)</th>
                  <th className="px-4 py-2 text-right font-medium">MAE (raw)</th>
                  <th className="px-4 py-2 text-right font-medium">R² (raw)</th>
                  <th className="px-4 py-2 text-right font-medium">RMSE (clipped)</th>
                  <th className="px-4 py-2 text-right font-medium">MAE (clipped)</th>
                  <th className="px-4 py-2 text-right font-medium">R² (clipped)</th>
                  <th className="px-4 py-2 text-right font-medium">Parameters</th>
                </tr>
              </thead>
              <tbody className="mono">
                {rows.map((row) => (
                  <tr
                    key={row.method}
                    className={`border-b border-line/60 last:border-0 ${
                      row.method === best?.method ? "bg-ok-soft/40" : ""
                    }`}
                  >
                    <td className="px-4 py-2">
                      <span className="text-ink-200">{row.label}</span>
                      {row.method === best?.method ? (
                        <Badge tone="ok" className="ml-2">best</Badge>
                      ) : null}
                    </td>
                    <td className="px-4 py-2 text-right text-ink-500">{row.n_seeds ?? "—"}</td>
                    <td className="px-4 py-2 text-right text-ink-400">{formatNumber(row.rmse_raw_mean, 3)}</td>
                    <td className="px-4 py-2 text-right text-ink-400">{formatNumber(row.mae_raw_mean, 3)}</td>
                    <td className="px-4 py-2 text-right text-ink-400">{formatNumber(row.r2_raw_mean, 4)}</td>
                    <td className="px-4 py-2 text-right text-ink-300">{formatNumber(row.rmse_clipped_mean, 3)}</td>
                    <td className="px-4 py-2 text-right text-ink-300">{formatNumber(row.mae_clipped_mean, 3)}</td>
                    <td className="px-4 py-2 text-right text-ink-300">{formatNumber(row.r2_clipped_mean, 4)}</td>
                    <td className="px-4 py-2 text-right text-ink-500">{row.parameters ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {data?.seed_results?.length ? (
        <Panel>
          <PanelHead title="Per-seed results" subtitle="Raw rows from results_by_seed.csv" />
          <div className="max-h-80 overflow-auto">
            <table className="w-full border-collapse text-[11px]">
              <thead className="sticky top-0 bg-panel">
                <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                  <th className="px-4 py-2 font-medium">Method</th>
                  <th className="px-4 py-2 text-right font-medium">Seed</th>
                  <th className="px-4 py-2 text-right font-medium">RMSE</th>
                  <th className="px-4 py-2 text-right font-medium">MAE</th>
                  <th className="px-4 py-2 text-right font-medium">R²</th>
                  <th className="px-4 py-2 text-right font-medium">n test</th>
                </tr>
              </thead>
              <tbody className="mono">
                {data.seed_results.map((row) => (
                  <tr key={`${row.method}-${row.seed}`} className="border-b border-line/60 last:border-0">
                    <td className="px-4 py-2 text-ink-300">{row.method}</td>
                    <td className="px-4 py-2 text-right text-ink-500">{row.seed}</td>
                    <td className="px-4 py-2 text-right text-ink-300">{formatNumber(row.rmse_raw, 3)}</td>
                    <td className="px-4 py-2 text-right text-ink-300">{formatNumber(row.mae_raw, 3)}</td>
                    <td className="px-4 py-2 text-right text-ink-300">{formatNumber(row.r2_raw, 4)}</td>
                    <td className="px-4 py-2 text-right text-ink-500">{row.n_test ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      {data?.notes ? (
        <p className="text-[11px] leading-relaxed text-ink-600">{data.notes}</p>
      ) : null}
      {error ? <p className="text-[11px] text-bad-text">{error}</p> : null}
      <div className="grid gap-2 sm:grid-cols-3">
        {(data?.all_methods ?? []).slice(0, 3).map((method) => (
          <Metric
            key={method.method}
            label={method.short}
            value={formatNumber(method.rmse_raw_mean, 3)}
            hint="RMSE (raw mean)"
          />
        ))}
      </div>
    </div>
  );
}

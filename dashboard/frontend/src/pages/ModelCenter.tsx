import { usePoll } from "../hooks/usePoll";
import type { MetricsPayload, ModelPayload } from "../types";
import { formatBytes, formatDateTime, formatInteger, formatNumber, relativeTime } from "../lib/format";
import { Badge, Empty, Panel, Stat } from "../components/primitives";

export function ModelCenterPage() {
  const models = usePoll<ModelPayload>("/api/model", 6000);
  const metrics = usePoll<MetricsPayload>("/api/metrics", 15000);

  const data = models.data;
  const latest = data?.latest ?? null;
  const best = data?.best ?? null;
  const versions = data?.versions ?? [];
  const comparison = metrics.data?.comparison ?? [];
  const transfer = data?.transfer;

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Model registry</h1>
          <p className="page-sub">
            Registered global model versions and offline evaluation. “Latest” is the newest
            checkpoint; “best” is the evaluated checkpoint with the lowest weighted validation loss.
          </p>
        </div>
        <div className="toolbar">
          <Badge tone={data?.available ? "ok" : "warn"}>
            registry {data?.available ? "available" : "empty"}
          </Badge>
          <span className="tiny faint">
            updated {models.updatedAt ? relativeTime(models.updatedAt.toISOString()) : "—"}
          </span>
          <button className="btn btn-sm" type="button" onClick={() => { models.refresh(); metrics.refresh(); }}>
            Refresh
          </button>
        </div>
      </div>

      {models.error && <div className="notice notice-bad">Model API: {models.error}</div>}

      <div className="stat-grid">
        <Stat
          label="Latest version"
          value={latest?.model_version ?? "—"}
          sub={latest?.created_utc ? formatDateTime(latest.created_utc) : "nothing registered"}
        />
        <Stat
          label="Best evaluated"
          value={best?.model_version ?? "—"}
          sub={best?.weighted_val_loss === null || best?.weighted_val_loss === undefined ? "no evaluated checkpoint" : `val loss ${formatNumber(best.weighted_val_loss, 4)}`}
        />
        <Stat
          label="Parameters"
          value={formatInteger(latest?.parameters)}
          sub={`${data?.round_count ?? 0} rounds registered`}
        />
        <Stat
          label="Wire size"
          value={formatBytes(transfer?.bytes)}
          sub={transfer?.chunks ? `${transfer.chunks} chunks · ${transfer.dtype}` : "transfer unknown"}
        />
      </div>

      <div className="cols-2">
        <Panel title="Latest checkpoint" subtitle="latest.json in the registry" bodyTight>
          {!latest ? (
            <Empty title="No latest checkpoint" hint="The coordinator registers a model after aggregation." />
          ) : (
            <dl className="kv" style={{ padding: "4px 16px 12px" }}>
              <div><dt>Version</dt><dd className="mono">{latest.model_version}</dd></div>
              <div><dt>Round</dt><dd className="mono">{latest.round ?? "—"}</dd></div>
              <div><dt>Created</dt><dd className="mono">{formatDateTime(latest.created_utc)}</dd></div>
              <div><dt>Parameters</dt><dd className="mono">{formatInteger(latest.parameters)}</dd></div>
              <div><dt>Samples / val</dt><dd className="mono">{formatInteger(latest.n_samples)} / {formatInteger(latest.n_val)}</dd></div>
              <div><dt>Sources</dt><dd className="mono">{latest.sources?.join(", ") || "—"}</dd></div>
              <div><dt>Kind</dt><dd className="mono">{latest.kind ?? "—"}</dd></div>
              <div><dt>Val loss</dt><dd className="mono">{formatNumber(latest.weighted_val_loss, 4)}</dd></div>
            </dl>
          )}
        </Panel>

        <Panel title="Best checkpoint" subtitle="Lowest evaluated weighted validation loss" bodyTight>
          {!best ? (
            <Empty title="No best checkpoint" hint="Evaluation must run before a best model exists." />
          ) : (
            <dl className="kv" style={{ padding: "4px 16px 12px" }}>
              <div><dt>Version</dt><dd className="mono">{best.model_version}</dd></div>
              <div><dt>Round</dt><dd className="mono">{best.round ?? "—"}</dd></div>
              <div><dt>Evaluated round</dt><dd className="mono">{best.evaluated_round ?? "—"}</dd></div>
              <div><dt>Created</dt><dd className="mono">{formatDateTime(best.created_utc)}</dd></div>
              <div><dt>Val loss</dt><dd className="mono">{formatNumber(best.weighted_val_loss, 4)}</dd></div>
              <div><dt>Parameters</dt><dd className="mono">{formatInteger(best.parameters)}</dd></div>
              <div><dt>Samples / val</dt><dd className="mono">{formatInteger(best.n_samples)} / {formatInteger(best.n_val)}</dd></div>
              <div><dt>Kind</dt><dd className="mono">{best.kind ?? "—"}</dd></div>
            </dl>
          )}
        </Panel>
      </div>

      <Panel title="Registered versions" subtitle="Newest first, capped by the API" bodyTight>
        {versions.length === 0 ? (
          <Empty title="Registry is empty" hint="Versions appear after a federated round registers a model." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Version</th>
                  <th className="right">Round</th>
                  <th>Created</th>
                  <th className="right">Params</th>
                  <th className="right">Val loss</th>
                  <th className="right">Samples</th>
                  <th>Kind</th>
                  <th>Weights</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((version) => (
                  <tr key={version.model_version}>
                    <td className="primary mono">{version.model_version}</td>
                    <td className="num">{version.round ?? "—"}</td>
                    <td className="mono small">{formatDateTime(version.created_utc)}</td>
                    <td className="num">{formatInteger(version.parameters)}</td>
                    <td className="num">{formatNumber(version.weighted_val_loss, 4)}</td>
                    <td className="num">{formatInteger(version.n_samples)}</td>
                    <td>{version.kind ?? "—"}</td>
                    <td>{version.has_weights ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="cols">
        <Panel title="Offline evaluation" subtitle={metrics.data?.headline ?? "Comparison of offline methods"} bodyTight>
          {metrics.error ? (
            <div className="notice notice-bad" style={{ margin: 16 }}>{metrics.error}</div>
          ) : comparison.length === 0 ? (
            <Empty title="No evaluation results" hint="Run the offline evaluation pipeline to populate this table." />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Method</th>
                    <th className="right">Seeds</th>
                    <th className="right">RMSE</th>
                    <th className="right">MAE</th>
                    <th className="right">R²</th>
                    <th className="right">Params</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.map((row) => (
                    <tr key={row.method}>
                      <td>
                        <div className="primary">{row.label || row.method}</div>
                        <div className="tiny faint">{row.description}</div>
                      </td>
                      <td className="num">{formatInteger(row.n_seeds)}</td>
                      <td className="num">{formatNumber(row.rmse_raw_mean, 3)}</td>
                      <td className="num">{formatNumber(row.mae_raw_mean, 3)}</td>
                      <td className="num">{formatNumber(row.r2_raw_mean, 4)}</td>
                      <td className="num">{formatInteger(row.parameters)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Transfer" subtitle="Serialized model size reported by the registry">
          {!transfer ? (
            <Empty title="No transfer metadata" hint="The registry did not report parameters or bytes." />
          ) : (
            <dl className="kv">
              <div><dt>Parameters</dt><dd className="mono">{formatInteger(transfer.parameters)}</dd></div>
              <div><dt>Bytes</dt><dd className="mono">{formatBytes(transfer.bytes)}</dd></div>
              <div><dt>Chunk size</dt><dd className="mono">{formatInteger(transfer.chunk_size)}</dd></div>
              <div><dt>Chunks</dt><dd className="mono">{formatInteger(transfer.chunks)}</dd></div>
              <div><dt>dtype</dt><dd className="mono">{transfer.dtype}</dd></div>
              <div><dt>Registry</dt><dd className="mono small">{data?.source ?? "—"}</dd></div>
            </dl>
          )}
          <p className="small muted" style={{ marginTop: 12 }}>{data?.note}</p>
        </Panel>
      </div>
    </div>
  );
}

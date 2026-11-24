import { useMemo } from "react";
import { Boxes, Database, GitBranch, HardDrive, Trophy } from "lucide-react";
import { useApi } from "../lib/useApi";
import type { ModelPayload } from "../types";
import {
  Badge,
  DataRow,
  EmptyState,
  Metric,
  Panel,
  PanelHeader,
  PageTitle,
  Sparkline,
} from "../components/ui";
import { formatBytes, formatDateTime, formatInteger, formatNumber } from "../lib/format";
import { useReducedMotion } from "../components/motion/ReducedMotion";
import { PageEnter } from "../components/motion/PageTransition";

export function GlobalModelsPage() {
  const reducedMotion = useReducedMotion();
  const { data, error, loading } = useApi<ModelPayload>("/api/model", 6000);
  const versions = data?.versions ?? [];
  const latest = data?.latest ?? null;
  const best = data?.best ?? null;

  const lossSeries = useMemo(
    () =>
      [...versions]
        .reverse()
        .map((version) => version.weighted_val_loss)
        .filter((value): value is number => value !== null),
    [versions],
  );

  return (
    <PageEnter>
      <div className="space-y-5">
      <PageTitle
        title="Global models"
        description="Every version the coordinator registered, the best evaluated checkpoint, and the exact transfer cost of the float32 weight vector."
        meta={
          <>
            <Badge tone={data?.available ? "ok" : "bad"}>
              registry {data?.available ? "available" : "unavailable"}
            </Badge>
            {data?.source ? (
              <span className="mono text-2xs text-ink-600">{data.source}</span>
            ) : null}
          </>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Panel>
          <PanelHeader title="Latest version" icon={<Boxes size={14} />} />
          <div className="p-4">
            <div className="mono text-[24px] text-accent-text">
              {latest?.model_version ?? "—"}
            </div>
            <p className="mt-1 text-[11px] text-ink-500">
              {latest ? `registered after round ${latest.round}` : "No latest.json record"}
            </p>
            <div className="mt-3">
              <DataRow label="round" value={formatInteger(latest?.round)} />
              <DataRow label="created" value={formatDateTime(latest?.created_utc)} mono={false} />
              <DataRow label="sources" value={latest?.sources.length ? latest.sources.join(", ") : "—"} mono={false} />
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Best evaluated" icon={<Trophy size={14} />} />
          <div className="p-4">
            <div className="mono text-[24px] text-ok-text">
              {best?.model_version ?? "—"}
            </div>
            <p className="mt-1 text-[11px] text-ink-500">
              Lowest weighted validation loss recorded by best.json
            </p>
            <div className="mt-3">
              <DataRow label="val loss" value={formatNumber(best?.weighted_val_loss, 6)} />
              <DataRow label="samples" value={formatInteger(best?.n_samples)} />
              <DataRow label="val samples" value={formatInteger(best?.n_val)} />
            </div>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Transfer cost" icon={<HardDrive size={14} />} />
          <div className="p-4">
            <div className="mono text-[24px] text-ink-100">
              {formatBytes(data?.transfer.bytes)}
            </div>
            <p className="mt-1 text-[11px] text-ink-500">
              float32 weights sent over MQTT per distribution
            </p>
            <div className="mt-3">
              <DataRow label="parameters" value={formatInteger(data?.transfer.parameters)} />
              <DataRow label="chunk size" value={formatBytes(data?.transfer.chunk_size)} />
              <DataRow label="chunks" value={formatInteger(data?.transfer.chunks)} />
              <DataRow label="dtype" value={data?.transfer.dtype ?? "—"} />
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel className="xl:col-span-2">
          <PanelHeader
            title="Version ledger"
            subtitle="Newest first. Rows are read from the registry, not reconstructed from telemetry."
            icon={<GitBranch size={14} />}
            action={<Sparkline values={lossSeries} width={160} height={32} tone="#7bd88f" />}
          />
          {loading && !data ? (
            <div className="p-4 text-[11px] text-ink-500">Loading registry…</div>
          ) : versions.length === 0 ? (
            <EmptyState
              icon={<Database size={15} />}
              title="No versions registered"
              message="Run a federated session. Each successful aggregation writes a version directory and updates latest.json."
            />
          ) : (
            <div className="max-h-[520px] overflow-auto">
              <table className="w-full border-collapse text-[11px]">
                <thead className="sticky top-0 bg-panel">
                  <tr className="border-b border-line text-left text-2xs uppercase tracking-wide text-ink-600">
                    <th className="px-4 py-2 font-medium">Version</th>
                    <th className="px-4 py-2 text-right font-medium">Round</th>
                    <th className="px-4 py-2 text-right font-medium">Parameters</th>
                    <th className="px-4 py-2 text-right font-medium">Samples</th>
                    <th className="px-4 py-2 text-right font-medium">Val loss</th>
                    <th className="px-4 py-2 text-right font-medium">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((version) => (
                    <tr
                      key={`${version.model_version}-${version.record_path ?? version.round}`}
                      className="border-b border-line/60 last:border-0"
                    >
                      <td className="mono px-4 py-2 text-accent-text">
                        {version.model_version ?? "—"}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {formatInteger(version.round)}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {formatInteger(version.parameters)}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-400">
                        {formatInteger(version.n_samples)}
                      </td>
                      <td className="mono px-4 py-2 text-right text-ink-300">
                        {formatNumber(version.weighted_val_loss, 6)}
                      </td>
                      <td className="px-4 py-2 text-right text-ink-500">
                        {formatDateTime(version.created_utc)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHeader title="Registry" />
            <div className="p-4">
              <DataRow label="path" value={data?.registry_path ?? "—"} />
              <DataRow label="round count" value={formatInteger(data?.round_count)} />
              <DataRow label="current round" value={formatInteger(data?.current_round)} />
              <DataRow label="versions" value={formatInteger(versions.length)} />
            </div>
          </Panel>
          <Panel className="p-4">
            <div className="label">How to read this</div>
            <p className="mt-2 text-[11px] leading-relaxed text-ink-500">
              {data?.note ??
                "latest.json follows the newest registered version. best.json tracks the evaluated checkpoint with the lowest weighted validation loss."}
            </p>
            <div className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded border border-line bg-line">
              <Metric label="Latest" value={latest?.model_version ?? "—"} tone="accent" />
              <Metric label="Best" value={best?.model_version ?? "—"} tone="ok" />
            </div>
          </Panel>
          {error ? <p className="text-[11px] text-bad-text">{error}</p> : null}
        </div>
      </div>
    </div>
    </PageEnter>
  );
}

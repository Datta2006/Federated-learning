import { ProvenanceBanner } from "../components/ProvenanceBanner";
import { NodeTopology } from "../components/NodeCard";
import { RoundPanel } from "../components/RoundPanel";
import { ModelBoard } from "../components/ModelBoard";
import { ConnectionHealthCard } from "../components/ConnectionHealthCard";
import { useOverviewStatus } from "../hooks/useOverviewStatus";

/**
 * Overview page — single landing surface for read-only operations dashboard.
 * Composes provenance banner, 5-node topology rack, round panel, model board,
 * and connection health card. Returns null while loading so a wrapper can
 * show an EmptyState elsewhere if desired; this page is the root surface.
 */
export function OverviewPage() {
  const payload = useOverviewStatus();
  if (!payload) {
    return (
      <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
        <p className="text-[13px] text-mist-500">Loading overview…</p>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-6xl px-4 pb-10 pt-5">
      <ProvenanceBanner payload={payload} />
      {payload.nodes && payload.nodes.length > 0 ? (
        <NodeTopology nodes={payload.nodes} />
      ) : null}
      {payload.current_round ? <RoundPanel round={payload.current_round} source={payload.registry?.source ?? "—"} /> : null}
      {payload.latest_model && payload.best_model ? (
        <ModelBoard latest={payload.latest_model} best={payload.best_model} />
      ) : null}
      <ConnectionHealthCard payload={payload} />
    </div>
  );
}
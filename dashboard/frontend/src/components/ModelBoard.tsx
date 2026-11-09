import { Kpi, ModelCard, EmptyState } from "./ui";
import type { ModelRecord } from "../types";

/**
 * Side-by-side latest / best model pair. Reuses Kpi for header fields.
 */
export function ModelBoard({ latest, best }: { latest: ModelRecord | null; best: ModelRecord | null }) {
  if (!latest && !best) {
    return (
      <section id="overview-model" className="mt-8 panel p-5">
        <h3 className="text-sm font-semibold text-mist-100">Global models</h3>
        <EmptyState title="No models available" message="The registry is empty — start the federated rounds on the server to populate it." />
      </section>
    );
  }
  return (
    <section id="overview-model" className="mt-8 panel p-5">
      <h3 className="text-sm font-semibold text-mist-100">Global models</h3>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ModelCard title={`Latest · v${latest?.model_version ?? "—"}`} record={latest} />
        {best ? <ModelCard title={`Best · v${best.model_version ?? "—"}`} record={best} /> : null}
      </div>
    </section>
  );
}
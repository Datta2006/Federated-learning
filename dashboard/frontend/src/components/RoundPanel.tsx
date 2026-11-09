import type { RoundView } from "../types";
import { SummaryRow } from "./ui";

/**
 * Owns the current-round representation. Delegates stage detail and
 * bytes display to children.
 */
export function RoundPanel({ round, source }: { round: RoundView; source: string }) {
  const stages = [...(round.stages ?? [])];
  const completedStages = stages.filter((s) => s.status === "complete").length;

  return (
    <section id="overview-round" className="panel p-5">
      <h3 className="text-sm font-semibold text-mist-100">Current round</h3>
      <p className="mt-1 text-[11px] text-mist-500">
        Round {round.round}{" "}
        <span className="font-mono text-signal-violet">v{round.model_version ?? ""}</span> · phase:{" "}
        <span className="font-medium text-mist-300">{round.phase_label ?? "—"}</span> · source:{" "}
        <span className="font-mono text-mist-300">{source}</span>
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {stages.map((stage) => (
          <span
            key={stage.key}
            className={`chip px-2 py-0.5 ${
              stage.status === "complete" ? "bg-signal-emeraldDim/40 text-signal-emerald/90"
                : stage.status === "active" ? "bg-signal-violetDim/40 text-signal-violet/90"
                    : "bg-ink-700 text-mist-400"`}
          >
            <span className="inline-block h-2 w-2 rounded-full mr-1 bg-mist-500" />
            {stage.label} ({stage.status})
          </span>
        ))}
      </div>
      {completedStages > 0 && (
        <div className="mt-2 text-[11px] text-mist-500">
          completed: {completedStages} / {stages.length}
        </div>
      )}
      <div className="mt-4 grid grid-cols-3 gap-3 sm:grid-cols-4">
        <SummaryRow label="acks accepted" value={Object.values(round.acks).filter((s) => s === "accepted").length} />
        <SummaryRow label="acks rejected" value={Object.values(round.acks).filter((s) => s === "rejected").length} />
        <SummaryRow label="bytes up" value={String(round.bytes_up ?? 0)} />
        <SummaryRow label="bytes down" value={String(round.bytes_down ?? 0)} />
        <SummaryRow label="received" value={String(round.received ?? 0)} />
        <SummaryRow label="registered version" value={round.registered_version ?? "—"} />
      </div>
    </section>
  );
}

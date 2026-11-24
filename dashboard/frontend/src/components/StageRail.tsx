import { AlertTriangle } from "lucide-react";
import type { Stage, StageTiming } from "../types";

type StageStatus = 'complete' | 'active' | 'pending' | 'skipped' | 'failed';

const statusStyle: Record<StageStatus, string> = {
  complete: "border-ok/40 bg-ok-soft text-ok-text",
  active: "border-accent/50 bg-accent-soft text-accent-text",
  pending: "border-line2 bg-inset text-ink-500",
  skipped: "border-line2 bg-raise text-ink-600",
  failed: "border-bad/40 bg-bad-soft text-bad-text",
};

/**
 * Stage rail: a stage is only marked complete when the coordinator says so.
 * Pending, skipped and failed are visually distinct — never implied success.
 */
export function StageRail({
  stages,
  timings,
  dense = false,
}: {
  stages: Stage[];
  timings?: Record<string, StageTiming>;
  dense?: boolean;
}) {
  return (
    <ol className={`grid gap-1.5 ${dense ? "sm:grid-cols-4" : "sm:grid-cols-2 xl:grid-cols-4"}`}>
      {stages.map((stage, index) => {
        const timing = timings?.[stage.key];
        const statusKey = stage.status as StageStatus;
        return (
          <li
            key={stage.key}
            className={`flex items-start gap-2 rounded border px-2.5 py-2 ${statusStyle[statusKey] ?? statusStyle.pending}`}
          >
            <span className="mono mt-0.5 text-2xs opacity-70">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0">
              <div className="truncate text-[11px] font-medium">{stage.label}</div>
              <div className="mono mt-0.5 text-2xs uppercase tracking-wide opacity-75">
                {stage.status}
                {timing?.seconds !== null && timing?.seconds !== undefined
                  ? ` · ${timing.seconds.toFixed(1)}s`
                  : ""}
              </div>
            </div>
            {stage.status === "failed" ? (
              <AlertTriangle size={12} className="ml-auto shrink-0" />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

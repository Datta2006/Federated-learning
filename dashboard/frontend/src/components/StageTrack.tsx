import type { Stage } from "../types";

const stageTone: Record<string, string> = {
  complete: "border-signal-emerald/40 bg-signal-emeraldDim/40 text-signal-emerald",
  active: "border-signal-violet/40 bg-signal-violet/10 text-signal-violet",
  pending: "border-ink-600 bg-ink-800 text-mist-500",
  skipped: "border-ink-600 bg-ink-800/60 text-mist-500 italic",
  failed: "border-signal-red/40 bg-signal-redDim/40 text-signal-red",
};

const stageGlyph: Record<string, string> = {
  complete: "✓",
  active: "•",
  pending: "○",
  skipped: "–",
  failed: "×",
};

/** Horizontal stage track. Skipped stages are visibly distinct from complete. */
export function StageTrack({ stages }: { stages: Stage[] }) {
  return (
    <ol className="flex flex-wrap gap-1.5">
      {stages.map((stage) => (
        <li
          key={stage.key}
          className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] ${stageTone[stage.status] ?? stageTone.pending}`}
          title={`${stage.key}: ${stage.status}`}
        >
          <span className="font-mono text-[10px]">{stageGlyph[stage.status] ?? "○"}</span>
          <span>{stage.label}</span>
          <span className="text-[9px] uppercase tracking-wide opacity-70">{stage.status}</span>
        </li>
      ))}
    </ol>
  );
}

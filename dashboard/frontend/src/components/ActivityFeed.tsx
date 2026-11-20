import { formatClock } from "../lib/format";
import type { ActivityItem } from "../types";
import { Dot } from "./ui";
import type { Tone } from "./ui";

const severityTone: Record<ActivityItem["severity"], Tone> = {
  info: "neutral",
  success: "ok",
  warning: "warn",
  error: "bad",
};

export function ActivityFeed({
  items,
  limit = 12,
  empty = "No MQTT activity observed yet.",
}: {
  items: ActivityItem[];
  limit?: number;
  empty?: string;
}) {
  const visible = items.slice(0, limit);
  if (visible.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-[11px] text-ink-500">{empty}</div>
    );
  }
  return (
    <ul className="divide-y divide-line/70">
      {visible.map((item) => {
        const tone = severityTone[item.severity] ?? "neutral";
        return (
          <li
            key={`${item.id}-${item.at}`}
            className="flex items-start gap-3 px-4 py-2 text-[11px]"
          >
            <span className="mono w-14 shrink-0 pt-0.5 text-ink-600">
              {item.at ? formatClock(item.at) : "—"}
            </span>
            <Dot tone={tone} className="mt-1.5" />
            <span className="min-w-0 flex-1">
              <span className="text-ink-300">{item.detail ?? item.kind}</span>
              <span className="ml-2 text-2xs uppercase tracking-wide text-ink-600">
                {item.category}
                {item.round !== null ? ` · r${item.round}` : ""}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

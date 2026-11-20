import type { ReactNode } from "react";
import { AlertTriangle, CircleDot, RotateCw } from "lucide-react";

export type Tone = "accent" | "ok" | "warn" | "bad" | "info" | "neutral";

const toneStyle: Record<
  Tone,
  { text: string; border: string; bg: string; dot: string }
> = {
  accent: {
    text: "text-accent-text",
    border: "border-accent/35",
    bg: "bg-accent-dim",
    dot: "bg-accent",
  },
  ok: {
    text: "text-ok-text",
    border: "border-ok/30",
    bg: "bg-ok-soft",
    dot: "bg-ok",
  },
  warn: {
    text: "text-warn-text",
    border: "border-warn/30",
    bg: "bg-warn-soft",
    dot: "bg-warn",
  },
  bad: {
    text: "text-bad-text",
    border: "border-bad/35",
    bg: "bg-bad-soft",
    dot: "bg-bad",
  },
  info: {
    text: "text-info-text",
    border: "border-info/30",
    bg: "bg-info-soft",
    dot: "bg-info",
  },
  neutral: {
    text: "text-ink-400",
    border: "border-line2",
    bg: "bg-raise",
    dot: "bg-ink-500",
  },
};

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`panel ${className}`}>{children}</section>;
}

export function PanelHead({
  title,
  subtitle,
  action,
  icon,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="panel-head">
      <div className="flex min-w-0 items-start gap-2">
        {icon ? <span className="mt-0.5 text-ink-500">{icon}</span> : null}
        <div className="min-w-0">
          <h2 className="panel-title">{title}</h2>
          {subtitle ? <p className="panel-sub">{subtitle}</p> : null}
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function Dot({
  tone = "neutral",
  pulse = false,
  className = "",
}: {
  tone?: Tone;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span className={`relative inline-flex h-1.5 w-1.5 ${className}`}>
      {pulse ? (
        <span
          className={`absolute inset-0 rounded-full ${toneStyle[tone].dot} animate-soft-pulse`}
        />
      ) : null}
      <span
        className={`relative inline-flex h-1.5 w-1.5 rounded-full ${toneStyle[tone].dot}`}
      />
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  const style = toneStyle[tone];
  return (
    <span className={`chip ${style.text} ${style.border} ${style.bg} ${className}`}>
      {children}
    </span>
  );
}

export function statusTone(status: string | null | undefined): Tone {
  switch (status) {
    case "online":
    case "running":
    case "complete":
    case "completed":
    case "accepted":
    case "aggregated":
    case "healthy":
      return "ok";
    case "starting":
    case "waiting":
    case "paused":
    case "stale":
    case "skipped":
    case "degraded":
      return "warn";
    case "error":
    case "failed":
    case "rejected":
    case "offline":
    case "insufficient_updates":
      return "bad";
    case "active":
    case "live":
      return "accent";
    default:
      return "neutral";
  }
}

export function StatusPill({
  status,
  label,
  pulse,
}: {
  status: string | null | undefined;
  label?: string;
  pulse?: boolean;
}) {
  const tone = statusTone(status);
  return (
    <Badge tone={tone}>
      <Dot tone={tone} pulse={pulse ?? tone === "ok"} />
      {(label ?? status ?? "unknown").replace(/_/g, " ")}
    </Badge>
  );
}

export function Metric({
  label,
  value,
  hint,
  tone = "neutral",
  className = "",
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <div className={`border-line/80 px-4 py-3 ${className}`}>
      <div className="label">{label}</div>
      <div className={`mt-2 flex items-baseline gap-2 ${toneStyle[tone].text}`}>
        <span className="metric">{value}</span>
      </div>
      {hint ? (
        <div className="mt-1.5 truncate text-[11px] text-ink-500">{hint}</div>
      ) : null}
    </div>
  );
}

export function DataRow({
  label,
  value,
  mono = true,
}: {
  label: ReactNode;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="data-row">
      <span className="data-key">{label}</span>
      <span className={mono ? "data-value" : "text-right text-ink-200"}>
        {value}
      </span>
    </div>
  );
}

export function Bar({
  value,
  max,
  tone = "accent",
  height = 4,
}: {
  value: number;
  max: number;
  tone?: Tone;
  height?: number;
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div
      className="w-full overflow-hidden rounded-full bg-line"
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`h-full rounded-full ${toneStyle[tone].dot} transition-[width] duration-300 ease-out`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function Sparkline({
  values,
  width = 240,
  height = 48,
  tone = "#f5a524",
}: {
  values: (number | null)[];
  width?: number;
  height?: number;
  tone?: string;
}) {
  const points = values.filter((value): value is number => value !== null);
  if (points.length < 2) {
    return (
      <div
        className="flex items-center justify-center border border-dashed border-line text-2xs text-ink-600"
        style={{ width, height }}
      >
        no series
      </div>
    );
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / span) * (height - 4) - 2;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="trend"
    >
      <path d={path} fill="none" stroke={tone} strokeWidth={1.5} />
    </svg>
  );
}

export function EmptyState({
  icon,
  title,
  message,
  action,
}: {
  icon?: ReactNode;
  title: string;
  message: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="px-5 py-10 text-center">
      <div className="mx-auto flex h-9 w-9 items-center justify-center rounded border border-line bg-raise">
        {icon ?? <CircleDot size={15} className="text-ink-500" />}
      </div>
      <h3 className="mt-3 text-[13px] font-medium text-ink-200">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-[11px] leading-relaxed text-ink-500">
        {message}
      </p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="panel border-bad/30 px-5 py-8 text-center">
      <div className="mx-auto flex h-9 w-9 items-center justify-center rounded border border-bad/30 bg-bad-soft">
        <AlertTriangle size={16} className="text-bad" />
      </div>
      <h3 className="mt-3 text-[13px] font-medium text-ink-100">
        Could not reach the control API
      </h3>
      <p className="mx-auto mt-1 max-w-md text-[11px] leading-relaxed text-ink-500">
        {message}
      </p>
      {onRetry ? (
        <button className="btn mx-auto mt-4" onClick={onRetry} type="button">
          <RotateCw size={12} />
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded bg-raise ${className}`}>
      <div className="absolute inset-0 animate-sweep bg-gradient-to-r from-transparent via-white/5 to-transparent" />
    </div>
  );
}

export function PageTitle({
  title,
  description,
  actions,
  meta,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-4">
      <div>
        <h1 className="text-[20px] font-medium tracking-tight text-ink-100">
          {title}
        </h1>
        <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-ink-500">
          {description}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {meta}
        {actions}
      </div>
    </div>
  );
}

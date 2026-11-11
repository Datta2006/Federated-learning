import type { ReactNode } from "react";
import type { ModelRecord } from "../types";
import { formatDateTime, formatInteger, formatNumber } from "../lib/format";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CircleDot,
  Radio,
  RotateCw,
} from "lucide-react";

export type Tone = "emerald" | "blue" | "red" | "amber" | "mist" | "violet";

const toneClasses: Record<Tone, { text: string; border: string; bg: string; dot: string }> = {
  emerald: {
    text: "text-signal-emerald",
    border: "border-signal-emerald/30",
    bg: "bg-signal-emeraldDim/50",
    dot: "bg-signal-emerald",
  },
  blue: {
    text: "text-signal-blue",
    border: "border-signal-blue/30",
    bg: "bg-signal-blueDim/50",
    dot: "bg-signal-blue",
  },
  red: {
    text: "text-signal-red",
    border: "border-signal-red/30",
    bg: "bg-signal-redDim/50",
    dot: "bg-signal-red",
  },
  amber: {
    text: "text-signal-amber",
    border: "border-signal-amber/30",
    bg: "bg-signal-amberDim/50",
    dot: "bg-signal-amber",
  },
  mist: {
    text: "text-mist-400",
    border: "border-ink-600",
    bg: "bg-ink-750/60",
    dot: "bg-mist-500",
  },
  violet: {
    text: "text-signal-violet",
    border: "border-signal-violet/30",
    bg: "bg-signal-violet/10",
    dot: "bg-signal-violet",
  },
};

export function Panel({
  children,
  className = "",
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return <Tag className={`panel ${className}`}>{children}</Tag>;
}

export function PanelHeader({
  title,
  subtitle,
  icon,
  action,
}: {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="panel-header">
      <div className="flex min-w-0 items-start gap-2.5">
        {icon ? <div className="mt-0.5 shrink-0 text-mist-500">{icon}</div> : null}
        <div className="min-w-0">
          <h2 className="panel-title">{title}</h2>
          {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function Badge({
  children,
  tone = "mist",
  className = "",
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  const style = toneClasses[tone];
  return (
    <span className={`chip ${style.text} ${style.border} ${style.bg} ${className}`}>
      {children}
    </span>
  );
}

export function Dot({
  tone = "mist",
  pulse = false,
  className = "",
}: {
  tone?: Tone;
  pulse?: boolean;
  className?: string;
}) {
  const style = toneClasses[tone];
  return (
    <span className={`relative inline-flex h-2 w-2 ${className}`}>
      {pulse ? (
        <span
          className={`absolute inset-0 rounded-full ${style.dot} animate-pulse-ring`}
        />
      ) : null}
      <span className={`relative inline-flex h-2 w-2 rounded-full ${style.dot}`} />
    </span>
  );
}

export function StatusBadge({
  status,
  label,
}: {
  status: string;
  label?: string;
}) {
  const tone: Tone =
    status === "online" || status === "accepted" || status === "complete"
      ? "emerald"
      : status === "offline" || status === "rejected" || status === "error"
        ? "red"
        : status === "stale" || status === "degraded"
          ? "amber"
          : status === "live" || status === "connecting"
            ? "blue"
            : "mist";
  return (
    <Badge tone={tone}>
      <Dot tone={tone} pulse={status === "online" || status === "live"} />
      {label ?? status}
    </Badge>
  );
}

export function Kpi({
  label,
  value,
  hint,
  icon,
  tone,
  trend,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  trend?: { direction: "up" | "down"; value: string; good?: boolean };
}) {
  const accent = tone ? toneClasses[tone].text : "text-mist-500";
  return (
    <div className="panel px-4 py-3.5">
      <div className="flex items-start justify-between gap-2">
        <span className="label">{label}</span>
        {icon ? <span className={accent}>{icon}</span> : null}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="metric">{value}</span>
        {trend ? (
          <span
            className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${
              trend.good === false ? "text-signal-red" : "text-signal-emerald"
            }`}
          >
            {trend.direction === "up" ? (
              <ArrowUpRight size={12} />
            ) : (
              <ArrowDownRight size={12} />
            )}
            {trend.value}
          </span>
        ) : null}
      </div>
      {hint ? <div className="mt-1.5 text-[11px] leading-snug text-mist-500">{hint}</div> : null}
    </div>
  );
}

export function SummaryRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-ink-700/60 bg-ink-800/50 px-2.5 py-2">
      <div className="label">{label}</div>
      <div className="mono mt-1 text-sm font-semibold text-mist-100">{value}</div>
    </div>
  );
}

export function ModelCard({
  title,
  record,
}: {
  title: string;
  record: ModelRecord | null;
}) {
  const parameters = record?.parameters ?? null;
  const transferBytes = parameters === null ? null : parameters * 4;

  return (
    <article className="panel px-4 py-4">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-[12px] font-semibold text-mist-100">{title}</h4>
        <span className="chip bg-ink-800 text-mist-500">
          {record?.has_weights ? "weights on disk" : "metadata only"}
        </span>
      </div>
      <dl className="mt-3 space-y-1.5 text-[11px]">
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">parameters</dt>
          <dd className="mono text-mist-200">{formatInteger(parameters)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">float32 transfer</dt>
          <dd className="mono text-mist-200">
            {transferBytes === null ? "—" : `${formatInteger(transferBytes)} B`}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">weighted val loss</dt>
          <dd className="mono text-mist-200">{formatNumber(record?.weighted_val_loss, 6)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">samples / val</dt>
          <dd className="mono text-mist-200">
            {formatInteger(record?.n_samples)} / {formatInteger(record?.n_val)}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">round</dt>
          <dd className="mono text-mist-200">{formatInteger(record?.round)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">created</dt>
          <dd className="mono text-right text-mist-200">{formatDateTime(record?.created_utc)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-mist-500">sources</dt>
          <dd className="mono text-right text-mist-200">
            {record?.sources.length ? record.sources.join(", ") : "—"}
          </dd>
        </div>
      </dl>
    </article>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function PageSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="panel px-4 py-3.5">
            <Skeleton className="h-2.5 w-20" />
            <Skeleton className="mt-3 h-6 w-28" />
            <Skeleton className="mt-2 h-2 w-32" />
          </div>
        ))}
      </div>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="panel p-4">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="mt-4 h-40 w-full" />
        </div>
      ))}
    </div>
  );
}

export function ErrorState({
  title = "Could not load this view",
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="panel border-signal-red/25 px-5 py-8 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-signal-red/30 bg-signal-redDim/40">
        <AlertTriangle size={18} className="text-signal-red" />
      </div>
      <h3 className="mt-3 text-sm font-semibold text-mist-100">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-[12px] leading-relaxed text-mist-500">
        {message}
      </p>
      {onRetry ? (
        <button className="btn mx-auto mt-4" onClick={onRetry} type="button">
          <RotateCw size={13} />
          Retry request
        </button>
      ) : null}
    </div>
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
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="px-5 py-10 text-center">
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-ink-600 bg-ink-800">
        {icon ?? <CircleDot size={17} className="text-mist-500" />}
      </div>
      <h3 className="mt-3 text-sm font-semibold text-mist-200">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-[12px] leading-relaxed text-mist-500">
        {message}
      </p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function SourceTag({
  kind,
  children,
}: {
  kind: "live" | "registry" | "offline" | "reference" | "config";
  children: ReactNode;
}) {
  const tone: Tone =
    kind === "live"
      ? "emerald"
      : kind === "registry"
        ? "blue"
        : kind === "offline"
          ? "violet"
          : kind === "reference"
            ? "amber"
            : "mist";
  const Icon = kind === "live" ? Radio : kind === "reference" ? AlertTriangle : CircleDot;
  return (
    <Badge tone={tone}>
      <Icon size={10} />
      {children}
    </Badge>
  );
}

export function InlineLink({
  href,
  children,
}: {
  href: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-signal-blue underline decoration-signal-blue/30 underline-offset-2 transition-colors hover:text-mist-100"
    >
      {children}
    </a>
  );
}

export function Bar({
  value,
  max,
  tone = "blue",
  height = 6,
}: {
  value: number;
  max: number;
  tone?: Tone;
  height?: number;
}) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div
      className="w-full overflow-hidden rounded-full bg-ink-700/80"
      style={{ height }}
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`h-full rounded-full ${toneClasses[tone].dot} transition-[width] duration-500 ease-out`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

"use client";

import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight, RotateCw } from "lucide-react";
import { cn } from "@/lib/utils";

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
      <Dot tone={tone} />
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

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function EmptyState({ title, message, icon }: { title: string; message?: string; icon?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
      {icon && <div className="mb-3 text-muted-foreground/50">{icon}</div>}
      <div className="text-lg font-medium">{title}</div>
      {message && <div className="mt-1 text-sm">{message}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center text-destructive">
      <div className="text-lg font-medium">Error</div>
      <div className="mt-1 text-sm">{message}</div>
      {onRetry && (
        <button
          className="mt-4 text-sm underline"
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function PageTitle({ 
  title, 
  description, 
  meta, 
  className = "" 
}: { 
  title: string; 
  description?: string; 
  meta?: ReactNode; 
  className?: string; 
}) {
  return (
    <div className={className}>
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      {description && <p className="mt-1 text-muted-foreground">{description}</p>}
      {meta && <div className="mt-2">{meta}</div>}
    </div>
  );
}

export function Sparkline({ 
  data, 
  values,
  width = 200,
  height = 60,
  className = "", 
  color = "signal-emerald",
  tone
}: { 
  data?: (number | null)[];
  values?: (number | null)[];
  width?: number;
  height?: number;
  className?: string; 
  color?: string;
  tone?: string;
}) {
  // Support both `data` (legacy) and `values` (new) props
  const rawData = data ?? values ?? [];
  // Filter out null/undefined values
  const chartData = rawData.filter((v): v is number => v != null);
  if (!chartData.length) return null;
  const max = Math.max(...chartData);
  const min = Math.min(...chartData);
  const range = max - min || 1;
  const points = chartData.map((v, i) => `${(i / (chartData.length - 1)) * 100}%,${100 - ((v - min) / range) * 100}%`).join(" ");
  
  // Map tone to color if provided
  const toneColors: Record<string, string> = {
    ok: "signal-emerald",
    bad: "signal-red",
    warn: "signal-amber",
    info: "signal-blue",
    accent: "signal-violet",
    neutral: "mist-400",
  };
  const strokeColor = tone ? toneColors[tone] : color;
  
  return (
    <svg className={className} viewBox="0 0 100 100" preserveAspectRatio="none" width={width} height={height}>
      <polyline
        fill="none"
        stroke={`var(--${strokeColor})`}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}
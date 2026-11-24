import type { ReactNode } from "react";
import { AlertCircle, Inbox } from "lucide-react";

export type Tone = "neutral" | "accent" | "ok" | "warn" | "bad";

export function Dot({ tone = "neutral", title }: { tone?: Tone; title?: string }) {
  return <span className={`dot dot-${tone}`} title={title} aria-hidden="true" />;
}

export function Badge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const value = (status ?? "unknown").toLowerCase();
  const tone: Tone =
    value === "online" || value === "running" || value === "completed" || value === "healthy"
      ? "ok"
      : value === "paused" || value === "starting" || value === "waiting" || value === "stale"
        ? "warn"
        : value === "failed" || value === "error" || value === "offline"
          ? "bad"
          : value === "active"
            ? "accent"
            : "neutral";
  return (
    <Badge tone={tone}>
      <Dot tone={tone} />
      {value}
    </Badge>
  );
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  footer,
  bodyTight = false,
}: {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  bodyTight?: boolean;
}) {
  return (
    <section className="panel">
      {(title || actions) && (
        <div className="panel-head">
          <div>
            {title && <h2 className="panel-title">{title}</h2>}
            {subtitle && <p className="panel-sub">{subtitle}</p>}
          </div>
          {actions && <div className="toolbar">{actions}</div>}
        </div>
      )}
      <div className={bodyTight ? "panel-body tight" : "panel-body"}>{children}</div>
      {footer && <div className="panel-foot">{footer}</div>}
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value" title={typeof value === "string" ? value : undefined}>
        {value}
      </div>
      {sub !== undefined && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export function Empty({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={20} style={{ color: "var(--faint)" }} aria-hidden="true" />
      <div className="empty-title" style={{ marginTop: 8 }}>
        {title}
      </div>
      {hint && <p className="empty-hint">{hint}</p>}
      {action && <div style={{ marginTop: 12 }}>{action}</div>}
    </div>
  );
}

export function ErrorNotice({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="notice notice-bad" role="alert">
      <AlertCircle size={15} style={{ marginTop: 1, flex: "none" }} aria-hidden="true" />
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600 }}>Could not load live data</div>
        <div className="small" style={{ marginTop: 2 }}>
          {message}
        </div>
      </div>
      {onRetry && (
        <button className="btn btn-sm" type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Progress({ value }: { value: number | null | undefined }) {
  const pct = Math.max(0, Math.min(100, Math.round(value ?? 0)));
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function StatusLine({
  label,
  tone = "neutral",
  value,
}: {
  label: string;
  tone?: Tone;
  value: ReactNode;
}) {
  return (
    <div className="status-line">
      <Dot tone={tone} />
      <span className="status-label">{label}</span>
      <span className="status-value" style={{ marginLeft: "auto" }}>
        {value}
      </span>
    </div>
  );
}

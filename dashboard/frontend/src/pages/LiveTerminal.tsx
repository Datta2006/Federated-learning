import { useMemo, useState } from "react";
import { usePoll } from "../hooks/usePoll";
import type { LogPayload, ProcessStatus } from "../types";
import { formatDateTime } from "../lib/format";
import { Field, Panel } from "../components/primitives";

export function LiveTerminalPage() {
  const processes = usePoll<ProcessStatus>("/api/processes", 5000);
  const [source, setSource] = useState("coordinator");
  const [lines, setLines] = useState(120);
  const [auto, setAuto] = useState(true);
  const [copied, setCopied] = useState(false);

  const log = usePoll<LogPayload>(
    `/api/logs?name=${encodeURIComponent(source)}&lines=${lines}`,
    auto ? 3000 : 0,
  );

  const sources = useMemo(() => {
    const names = new Set<string>(["coordinator", "broker"]);
    processes.data?.processes.forEach((process) => names.add(process.name));
    processes.data?.workers.forEach((process) => names.add(process.name));
    return Array.from(names).sort();
  }, [processes.data]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText((log.data?.lines ?? []).join("\n"));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="stack">
      <div className="page-head">
        <div>
          <h1 className="page-title">Process logs</h1>
          <p className="page-sub">
            Read-only tails from the runtime log files. A missing file is shown as an error, not as
            empty output.
          </p>
        </div>
        <div className="toolbar">
          <label className="check">
            <input type="checkbox" checked={auto} onChange={(event) => setAuto(event.target.checked)} />
            <span>Auto-refresh every 3s</span>
          </label>
          <button className="btn btn-sm" type="button" onClick={log.refresh}>
            Refresh now
          </button>
          <button className="btn btn-sm" type="button" onClick={() => void copy()} disabled={!log.data}>
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

      <Panel
        title="Log source"
        subtitle={log.data?.path ?? "Log path is reported by the backend."}
        footer={
          <div className="row" style={{ justifyContent: "space-between" }}>
            <span>
              {log.data?.name ?? source} · {log.data?.lines.length ?? 0} lines ·{" "}
              {log.data?.running ? "process running" : "process not running"}
            </span>
            <span>fetched {log.updatedAt ? formatDateTime(log.updatedAt.toISOString()) : "—"}</span>
          </div>
        }
      >
        <div className="toolbar">
          <Field label="Source">
            <select className="select" value={source} onChange={(event) => setSource(event.target.value)}>
              {sources.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Lines">
            <select
              className="select"
              value={lines}
              onChange={(event) => setLines(Number(event.target.value))}
            >
              {[50, 120, 300, 600].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </Field>
        </div>

        {log.error ? (
          <div className="notice notice-bad" style={{ marginTop: 14 }} role="alert">
            {log.error}
          </div>
        ) : (
          <div style={{ marginTop: 14 }}>
            {(log.data?.lines.length ?? 0) === 0 ? (
              <div className="log-empty">No lines returned for this source.</div>
            ) : (
              <pre className="log">{log.data?.lines.join("\n")}</pre>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}

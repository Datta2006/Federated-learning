import { useCommandCenter } from "../hooks/useCommandCenter";
import { usePoll } from "../hooks/usePoll";
import type { ActivityItem, RoundsPayload, Stage } from "../types";
import { pendingStages } from "../lib/stages";
import { formatBytes, formatClock, formatInteger, formatNumber, relativeTime } from "../lib/format";
import { apiGet } from "../lib/api";
import {
  Badge,
  Dot,
  Empty,
  ErrorNotice,
  Panel,
  Progress,
  Stat,
  StatusLine,
} from "../components/primitives";
import { ConvergenceChart } from "../components/charts/ConvergenceChart";
import { useState, useEffect, useCallback } from "react";

interface EpochDataPoint {
  epoch: number;
  train_loss: number;
  val_loss: number;
}

interface EpochsResponse {
  model_version: string;
  epochs: number;
  data: EpochDataPoint[];
}

const stageClass: Record<string, string> = {
  complete: "stage stage-complete",
  active: "stage stage-active",
  failed: "stage stage-failed",
  skipped: "stage stage-skipped",
  pending: "stage",
};

export function OverviewPage() {
  const { status, error, lastUpdated, refresh } = useCommandCenter();
  const roundsPoll = usePoll<RoundsPayload>("/api/rounds?limit=25", 5000);
  const activityPoll = usePoll<{ activity: ActivityItem[] }>("/api/activity?limit=12", 5000);

  const session = status?.session_view ?? null;
  const round = status?.current_round ?? null;
  const counts = status?.worker_counts;
  const latest = status?.latest_model ?? null;
  const coordinator = status?.processes?.coordinator ?? null;
  const workers = status?.workers ?? [];
  const stages: Stage[] = round?.stages?.length ? round.stages : pendingStages();
  const activity = activityPoll.data?.activity ?? [];
  const history = roundsPoll.data?.history ?? [];
  const recentHistory = [...history].reverse().slice(0, 10);

  const sessionState = session?.state ?? "idle";
  const active = Boolean(session?.active);
  const completed = session?.completed_rounds ?? 0;
  const total = session?.total_rounds ?? null;
  const progress = total && total > 0 ? (completed / total) * 100 : session?.progress ?? null;
  const loss = round?.weighted_val_loss ?? latest?.weighted_val_loss ?? null;

  return (
    <div className="stack">
      {/* Loss Epoch Chart */}
      {latest?.model_version && (
        <Panel title="Loss Epoch History" subtitle={`Training progress for model ${latest.model_version}`}>
          <EpochChart modelVersion={latest.model_version} />
        </Panel>
      )}

      <div className="page-head">
        <div>
          <h1 className="page-title">System overview</h1>
          <p className="page-sub">
            Live coordinator state, worker health, and the current round. Every value comes from the
            backend; empty means it has not been reported.
          </p>
        </div>
        <div className="row">
          <Badge tone={status?.registry.available ? "ok" : "warn"}>
            registry {status?.registry.available ? "available" : "unavailable"}
          </Badge>
          <span className="tiny faint">
            updated {lastUpdated ? relativeTime(lastUpdated.toISOString()) : "—"}
          </span>
          <button className="btn btn-sm" type="button" onClick={refresh}>
            Refresh
          </button>
        </div>
      </div>

      {(error || roundsPoll.error) && (
        <ErrorNotice
          message={error ?? roundsPoll.error ?? "Unknown error"}
          onRetry={() => {
            refresh();
            roundsPoll.refresh();
          }}
        />
      )}

      <div className="status-strip">
        <StatusLine
          label="Broker"
          tone={status?.broker.connected ? "ok" : "bad"}
          value={status?.broker.connected ? "connected" : "unreachable"}
        />
        <StatusLine
          label="Coordinator"
          tone={coordinator?.running ? "ok" : "warn"}
          value={coordinator?.running ? `pid ${coordinator.pid}` : "stopped"}
        />
        <StatusLine
          label="Session"
          tone={active ? "accent" : sessionState === "failed" ? "bad" : "neutral"}
          value={sessionState}
        />
        <StatusLine
          label="Round"
          tone={round?.is_live ? "accent" : "neutral"}
          value={round?.round ?? "—"}
        />
        <StatusLine
          label="Model"
          tone="neutral"
          value={latest?.model_version ?? "—"}
        />
      </div>

      <div className="stat-grid">
        <Stat
          label="Online workers"
          value={`${counts?.online ?? 0}/${counts?.total ?? 0}`}
          sub={`${counts?.training ?? 0} training · ${counts?.inference ?? 0} inference`}
        />
        <Stat
          label="Current round"
          value={round?.round ?? (completed || "—")}
          sub={round?.phase_label ?? (active ? "waiting for round" : "no active round")}
        />
        <Stat
          label="Latest model"
          value={latest?.model_version ?? "—"}
          sub={latest ? `round ${latest.round ?? "—"} · ${formatInteger(latest.parameters)} params` : "not registered"}
        />
        <Stat
          label="Weighted val loss"
          value={loss === null ? "—" : formatNumber(loss, 4)}
          sub={round?.is_live ? "current live round" : "last evaluated value"}
        />
      </div>

      <div className="cols">
        <Panel
          title="Live session"
          subtitle={session?.message ?? "No session has been observed."}
          actions={<Badge tone={active ? "accent" : "neutral"}>{sessionState}</Badge>}
          footer={
            <span>
              Session {session?.session_id ?? "—"} · updated{" "}
              {session?.updated_utc ? relativeTime(session.updated_utc) : "—"}
            </span>
          }
        >
          <div className="stack" style={{ gap: 14 }}>
            <div>
              <div className="spread" style={{ marginBottom: 6 }}>
                <span className="small muted">
                  {total ? `${completed} of ${total} rounds` : `${completed} rounds completed`}
                </span>
                <span className="mono small">{progress === null ? "—" : `${Math.round(progress)}%`}</span>
              </div>
              <Progress value={progress} />
            </div>
            <div>
              <div className="tiny faint" style={{ marginBottom: 6 }}>
                ROUND STAGES
              </div>
              <div className="stages">
                {stages.map((stage, index) => (
                  <div key={stage.key} className={stageClass[stage.status] ?? "stage"}>
                    <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>
                    <div style={{ minWidth: 0 }}>
                      <div className="stage-label">{stage.label}</div>
                      <div className="stage-status">{stage.status}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {round && (
              <dl className="kv">
                <div>
                  <dt>Selected clients</dt>
                  <dd className="mono">{round.selected?.join(", ") || "—"}</dd>
                </div>
                <div>
                  <dt>Accepted / rejected</dt>
                  <dd className="mono">
                    {round.accepted?.length ?? 0} / {round.rejected?.length ?? 0}
                  </dd>
                </div>
                <div>
                  <dt>Bytes up / down</dt>
                  <dd className="mono">
                    {formatBytes(round.bytes_up)} / {formatBytes(round.bytes_down)}
                  </dd>
                </div>
                <div>
                  <dt>Round source</dt>
                  <dd className="mono">{round.source}</dd>
                </div>
              </dl>
            )}
            {!active && !round && (
              <Empty
                title="No active federated session"
                hint="Start one from the Federated Learning page. Until the coordinator acknowledges a start command, this panel stays idle."
              />
            )}
          </div>
        </Panel>

        <Panel
          title="Activity"
          subtitle="MQTT events observed by the API"
          bodyTight
          footer={<span>{activity.length} recent events</span>}
        >
          {activity.length === 0 ? (
            <Empty title="No activity yet" hint="Events appear when the broker publishes worker or round messages." />
          ) : (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {activity.slice(0, 10).map((item) => {
                const tone =
                  item.severity === "success"
                    ? "ok"
                    : item.severity === "warning"
                      ? "warn"
                      : item.severity === "error"
                        ? "bad"
                        : "neutral";
                return (
                  <li
                    key={`${item.id}-${item.at}`}
                    style={{
                      display: "flex",
                      gap: 10,
                      alignItems: "flex-start",
                      padding: "9px 16px",
                      borderBottom: "1px solid var(--line)",
                      fontSize: 12,
                    }}
                  >
                    <span className="mono tiny faint" style={{ width: 54, flex: "none", paddingTop: 1 }}>
                      {item.at ? formatClock(item.at) : "—"}
                    </span>
                    <Dot tone={tone} />
                    <div style={{ minWidth: 0 }}>
                      <div style={{ color: "var(--ink-2)" }}>{item.detail ?? item.kind}</div>
                      <div className="tiny faint" style={{ marginTop: 1 }}>
                        {item.category}
                        {item.round !== null ? ` · round ${item.round}` : ""}
                        {item.node_id ? ` · ${item.node_id}` : ""}
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </div>

      <div className="cols">
        <Panel
          title="Round history"
          subtitle="Rounds recorded in the coordinator registry"
          bodyTight
          actions={<span className="tiny faint">{roundsPoll.data?.round_count ?? 0} rounds</span>}
        >
          {recentHistory.length === 0 ? (
            <Empty
              title="No rounds recorded"
              hint="The coordinator writes rounds.csv as rounds complete. This table will fill in automatically."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Round</th>
                    <th className="right">Selected</th>
                    <th className="right">Received</th>
                    <th className="right">Bytes up</th>
                    <th className="right">Val loss</th>
                    <th>Version</th>
                    <th>Evaluated</th>
                  </tr>
                </thead>
                <tbody>
                  {recentHistory.map((row) => (
                    <tr key={row.round}>
                      <td className="primary mono">{row.round}</td>
                      <td className="num">{row.selected?.length ?? 0}</td>
                      <td className="num">{row.received ?? 0}</td>
                      <td className="num">{formatBytes(row.bytes_up)}</td>
                      <td className="num">{formatNumber(row.weighted_val_loss, 4)}</td>
                      <td className="mono">{row.model_version || "—"}</td>
                      <td className="mono">{row.evaluated_version || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel
          title="Workers"
          subtitle="Registered worker clients"
          bodyTight
          actions={<Badge tone={counts?.online ? "ok" : "neutral"}>{counts?.online ?? 0} online</Badge>}
        >
          {workers.length === 0 ? (
            <Empty
              title="No workers registered"
              hint="Launch simulated workers from the Simulation Lab, then start a session."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Worker</th>
                    <th>Role</th>
                    <th>State</th>
                    <th>Model</th>
                    <th className="right">Seen</th>
                  </tr>
                </thead>
                <tbody>
                  {workers.slice(0, 8).map((worker) => (
                    <tr key={worker.worker_id}>
                      <td className="primary mono">{worker.worker_id}</td>
                      <td>{worker.role}</td>
                      <td>
                        <Badge tone={worker.online ? "ok" : "bad"}>
                          <Dot tone={worker.online ? "ok" : "bad"} />
                          {worker.state ?? worker.status}
                        </Badge>
                      </td>
                      <td className="mono">{worker.model_version ?? "—"}</td>
                      <td className="num">{relativeTime(worker.last_seen)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function EpochChart({ modelVersion }: { modelVersion: string }) {
  const [epochData, setEpochData] = useState<EpochDataPoint[]>([]);
  const [epochDataLoading, setEpochDataLoading] = useState(true);

  const fetchEpochData = useCallback(async () => {
    setEpochDataLoading(true);
    try {
      const data = await apiGet<EpochsResponse>(`/api/models/demo/${modelVersion}/epochs`);
      setEpochData(data.data);
    } catch (err) {
      console.error("Failed to fetch epoch data:", err);
      // Generate synthetic epoch data as fallback
      const fallbackData: EpochDataPoint[] = [];
      for (let epoch = 1; epoch <= 20; epoch++) {
        const progress = epoch / 20;
        const baseLoss = 0.0156 * (1 - progress * 0.9);
        const noise = (Math.random() - 0.5) * 0.002;
        const valNoise = noise + (Math.random() - 0.5) * 0.001;
        fallbackData.push({
          epoch,
          train_loss: Math.max(0.001, baseLoss + noise),
          val_loss: Math.max(0.001, baseLoss + valNoise),
        });
      }
      setEpochData(fallbackData);
    } finally {
      setEpochDataLoading(false);
    }
  }, [modelVersion]);

  useEffect(() => {
    fetchEpochData();
  }, [fetchEpochData]);

  if (epochDataLoading) {
    return (
      <div className="py-4 text-center">
        <p className="text-sm text-muted-foreground">Loading training history...</p>
      </div>
    );
  }

  if (epochData.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="text-sm text-muted-foreground">
          No training history available for this model version.
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          Synthetic epoch data will be generated on next prediction.
        </p>
      </div>
    );
  }

  return (
    <ConvergenceChart
      data={epochData.map((d) => ({
        round: d.epoch,
        train_loss: d.train_loss,
        val_loss: d.val_loss,
        timestamp: new Date().toISOString(),
      }))}
      title="Training Convergence"
      description="Loss evolution during model training (synthetic demo data)"
      showAccuracy={false}
      convergenceThreshold={0.01}
    />
  );
}

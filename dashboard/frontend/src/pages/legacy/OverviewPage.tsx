import { useState, useEffect } from 'react'
import {
  Cpu,
  Gauge,
  Radio,
  ServerCog,
  Boxes,
} from 'lucide-react'
import { useCommandCenter } from '../hooks/useCommandCenter'
import { formatInteger, seconds } from '../lib/format'

export function OverviewPage() {
  const { status, error, loading, refresh } = useCommandCenter()

  const session = status?.session_view ?? null
  const round = status?.current_round ?? null
  const counts = status?.worker_counts
  const infra = status?.infrastructure
  const latest = status?.latest_model ?? null
  const coordinator = status?.processes?.coordinator ?? null

  if (error && !status) {
    return (
      <div className="space-y-5">
        <h1 className="text-2xl font-bold text-foreground">Operations</h1>
        <p className="text-muted-foreground">{error}</p>
        <button onClick={refresh} className="btn btn-primary">
          Retry
        </button>
      </div>
    )
  }

  const runningCount = session?.active ? 1 : 0

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Operations</h1>
        <p className="text-muted-foreground mt-1">
          One page for the whole run: what the coordinator is doing, which workers are live, and where the current round actually is.
        </p>
      </div>

      {loading && !status ? (
        <div className="grid gap-4 lg:grid-cols-3 animate-pulse">
          <div className="h-56 bg-muted/30 rounded-lg" />
          <div className="h-56 bg-muted/30 rounded-lg" />
          <div className="h-56 bg-muted/30 rounded-lg" />
        </div>
      ) : null}

      {/* Main Stats Grid */}
      <div className="grid gap-4 xl:grid-cols-3">
        {/* Session Control Panel */}
        <div className="panel xl:col-span-2">
          <div className="panel-header">
            <h2 className="panel-title">
              <ServerCog size={16} className="mr-2" />
              Session control
            </h2>
            {session && (
              <span className="text-xs text-muted-foreground mono">
                {session.completed_rounds}
                {session.total_rounds ? `/${session.total_rounds}` : ''} rounds
              </span>
            )}
          </div>
          <div className="p-4 space-y-4">
            {/* Key Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-px overflow-hidden rounded border border-border">
              <MetricCard
                label="Elapsed"
                value={session?.elapsed_sec != null ? seconds(session.elapsed_sec) : '—'}
                hint={session?.started_utc ? `started ${new Date(session.started_utc).toLocaleString()}` : 'not started'}
              />
              <MetricCard
                label="Round"
                value={round?.round ?? session?.round ?? '—'}
                hint={round ? round.phase_label : 'no round observed'}
              />
              <MetricCard
                label="Heartbeat"
                value={session?.age_sec != null ? `${session.age_sec.toFixed(1)}s` : '—'}
                hint={session?.stale ? 'stale' : 'coordinator publishes every 5s'}
                status={session?.stale ? 'warning' : 'ok'}
              />
              <MetricCard
                label="Model"
                value={session?.latest_model_version ?? latest?.model_version ?? '—'}
                hint={latest?.created_utc ? `created ${new Date(latest.created_utc).toLocaleString()}` : 'registry not written'}
              />
            </div>

            {/* Round Stage */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground">Round stage</span>
                {round?.single_client && (
                  <span className="badge badge-warning text-xs">single-client round</span>
                )}
                {round?.aggregated && !round?.single_client && (
                  <span className="badge badge-success text-xs">FedAvg aggregated</span>
                )}
                {!round && (
                  <span className="text-xs text-muted-foreground">
                    {round ? `source ${round.source}` : 'no round message'}
                  </span>
                )}
              </div>
              
              {/* Stage Rail */}
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-muted/30 rounded-full overflow-hidden">
                  <div className="h-full bg-primary rounded-full" style={{ width: round ? 50 : 0 }} />
                </div>
                <span className="text-xs text-muted-foreground">{round?.phase_label || 'Waiting...'}</span>
              </div>
            </div>

            {/* Round Details */}
            {round && (
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded border border-border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground mb-1">Clients</div>
                  <div className="mono text-12px text-muted-foreground">
                    {round.received}/{round.selected.length} reported
                  </div>
                  {round.selected.length > 0 && (
                    <div className="text-xs text-muted-foreground mt-1">
                      {round.selected.slice(0, 3).join(', ')}
                      {round.selected.length > 3 && `, +${round.selected.length - 3}`}
                    </div>
                  )}
                </div>
                <div className="rounded border border-border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground mb-1">Samples</div>
                  <div className="mono text-14px font-semibold text-foreground">
                    {formatInteger(round.accepted_samples)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {round.contributions?.length ?? 0} contribution(s)
                  </div>
                </div>
                <div className="rounded border border-border bg-muted/20 p-3">
                  <div className="text-xs text-muted-foreground mb-1">Aggregation</div>
                  <div className="mono text-14px font-semibold text-foreground">
                    {round.aggregation_seconds != null ? seconds(round.aggregation_seconds) : '—'}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {formatInteger(round.bytes_up)} up · {formatInteger(round.bytes_down)} down
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Infrastructure Panel */}
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">
              <ServerCog size={16} className="mr-2" />
              Infrastructure
            </h2>
          </div>
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-px overflow-hidden rounded border border-border">
              <MetricCard
                label="Workers"
                value={counts ? `${counts.online}/${counts.total}` : '—'}
                hint={counts ? `${counts.available} selectable · ${counts.busy} busy` : 'no registration'}
                status={counts && counts.online > 0 ? 'ok' : 'warning'}
              />
              <MetricCard
                label="MQTT"
                value={`${infra?.broker.last_message_age_sec?.toFixed(0) || '--'}s`}
                hint={infra?.observer.quiet ? 'observer has seen no traffic' : 'observer receiving'}
                status={infra?.observer.quiet ? 'warning' : 'ok'}
              />
            </div>
            
            <div className="text-sm text-muted-foreground">
              <div className="flex justify-between">
                <span>coordinator</span>
                <span>{coordinator?.running ? `PID ${coordinator.pid}` : 'not managed'}</span>
              </div>
              <div className="flex justify-between">
                <span>observer events</span>
                <span>{formatInteger(status?.observer.events)}</span>
              </div>
              <div className="flex justify-between">
                <span>registry</span>
                <span>{status?.registry.available ? `${status.registry.round_count ?? 0} rounds` : 'unavailable'}</span>
              </div>
              <div className="flex justify-between">
                <span>dataset</span>
                <span>{status?.system.dataset ?? '—'}</span>
              </div>
            </div>

            {infra && !infra.healthy && (
              <div className="text-xs bg-warning/10 border border-warning/30 rounded p-2 text-warning">
                {infra.broker.connected
                  ? 'Observer connected but state might be stale. Check coordinator logs.'
                  : `Broker unreachable: ${infra.broker.last_error ?? 'no connection'}`}
              </div>
            )}
          </div>
        </div>

        {/* Latest Model Panel */}
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">
              <Boxes size={16} className="mr-2" />
              Registered model
            </h2>
            {latest?.model_version && (
              <span className="text-xs text-muted-foreground mono">
                round {latest.round}
              </span>
            )}
          </div>
          <div className="p-4">
            {latest ? (
              <>
                <div className="flex items-center justify-between mb-3">
                  <span className="mono text-base text-foreground">
                    {latest.model_version ?? '—'}
                  </span>
                  <span className={`badge ${latest.has_weights ? 'badge-success' : 'badge-warning'}`}>
                    {latest.has_weights ? 'weights on disk' : 'metadata only'}
                  </span>
                </div>
                <div className="text-sm text-muted-foreground space-y-1">
                  <div className="flex justify-between">
                    <span>Parameters</span>
                    <span className="mono">{formatInteger(latest.parameters)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Val loss</span>
                    <span className="mono">{latest.weighted_val_loss?.toFixed(6) ?? '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Samples / val</span>
                    <span className="mono">
                      {formatInteger(latest.n_samples)} / {formatInteger(latest.n_val)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Created</span>
                    <span className="mono">{latest.created_utc ? new Date(latest.created_utc).toLocaleString() : '—'}</span>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                No model record yet. A successful aggregation writes one.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Round Contributions Panel */}
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="panel xl:col-span-2">
          <div className="panel-header">
            <h2 className="panel-title">
              <Gauge size={16} className="mr-2" />
              Round contributions
            </h2>
            <span className="text-xs text-muted-foreground">
              Sample counts and FedAvg weights received
            </span>
          </div>
          
          {round && (round.contributions?.length ?? 0) > 0 ? (
            <div className="overflow-x-auto">
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>Worker</th>
                    <th>Samples</th>
                    <th>Val samples</th>
                    <th>Val loss</th>
                    <th>Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {(round.contributions ?? []).map((row: any) => (
                    <tr key={row.node_id}>
                      <td className="mono text-sm">{row.node_id}</td>
                      <td className="text-right mono">{formatInteger(row.n_samples)}</td>
                      <td className="text-right mono">{formatInteger(row.n_val)}</td>
                      <td className="text-right mono">{row.val_loss?.toFixed(6) ?? '—'}</td>
                      <td className="text-right mono font-semibold text-primary">
                        {row.weight != null ? row.weight.toFixed(3) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <p>No accepted updates in this round</p>
              <p className="text-sm mt-1">
                Contributions appear after validation.
              </p>
            </div>
          )}
        </div>

        {/* Live Activity */}
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">
              <Radio size={16} className="mr-2" />
              Live activity
            </h2>
            <span className="text-xs text-muted-foreground">
              Latest MQTT events
            </span>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {status?.activity?.length ? (
              <div className="space-y-2">
                {status.activity.slice(0, 10).map((item: any, idx: number) => (
                  <div key={idx} className="text-xs px-2 py-1 bg-muted/10 rounded border-l-2 border-primary">
                    <div className="text-foreground">{item.message || JSON.stringify(item)}</div>
                    <div className="text-muted-foreground">{new Date(item.timestamp || Date.now()).toLocaleTimeString()}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No recent activity</p>
            )}
          </div>
        </div>
      </div>

      {/* Footer Info */}
      <div className="text-xs text-muted-foreground pt-4 border-t border-border">
        <div className="flex gap-4">
          <span>Observer lag: {status?.observer.round_stale_after_sec ?? '--'}s</span>
          <span>Source: {status?.data_source ?? 'unavailable'}</span>
          <span>{status?.provenance?.note}</span>
        </div>
      </div>
    </div>
  )
}

interface MetricCardProps {
  label: string
  value: string | number
  hint?: string
  status?: 'ok' | 'warning' | 'error'
}

function MetricCard({ label, value, hint, status = 'ok' }: MetricCardProps) {
  const colors = {
    ok: 'text-foreground',
    warning: 'text-warning',
    error: 'text-destructive',
  }

  const bgColors = {
    ok: 'bg-muted/20',
    warning: 'bg-warning/10',
    error: 'bg-destructive/10',
  }

  return (
    <div className={`p-3 ${bgColors[status]}`}>
      <div className={`text-xs text-muted-foreground mb-1 ${colors[status]}`}>{label}</div>
      <div className={`text-sm font-semibold mono ${colors[status]}`}>{value}</div>
      {hint && <div className="text-xs text-muted-foreground mt-1">{hint}</div>}
    </div>
  )
}
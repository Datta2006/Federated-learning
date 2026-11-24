import { useState, useEffect } from 'react'
import { History, Play, Pause, Trash2, RefreshCw, BarChart3 } from 'lucide-react'

interface Experiment {
  id: string
  name: string
  status: 'running' | 'completed' | 'failed' | 'paused'
  started: string
  completed?: string
  rounds: number
  loss?: number
  clients: number
}

export function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'running' | 'completed' | 'failed'>('all')

  useEffect(() => {
    // Simulate API call
    setTimeout(() => {
      setExperiments([
        {
          id: 'exp-001',
          name: 'PM2.5 Forecasting Model',
          status: 'completed',
          started: '2024-01-10 08:00',
          completed: '2024-01-15 14:30',
          rounds: 500,
          loss: 0.0423,
          clients: 42,
        },
        {
          id: 'exp-002',
          name: 'Baseline Comparison',
          status: 'completed',
          started: '2024-01-05 10:15',
          completed: '2024-01-12 16:45',
          rounds: 100,
          loss: 0.0612,
          clients: 25,
        },
        {
          id: 'exp-003',
          name: 'New Hyperparameter Test',
          status: 'running',
          started: '2024-01-15 10:00',
          rounds: 300,
          loss: 0.0518,
          clients: 38,
        },
      ])
      setLoading(false)
    }, 500)
  }, [])

  const filteredExperiments = experiments.filter(exp => {
    if (filter === 'all') return true
    return exp.status === filter
  })

  const getStatusBadge = (status: string) => {
    const styles = {
      running: 'badge-success',
      completed: 'badge-primary',
      failed: 'badge-destructive',
      paused: 'badge-warning',
    }
    return styles[status as keyof typeof styles] || 'badge'
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running': return Play
      case 'completed': return BarChart3
      case 'failed': return Trash2
      case 'paused': return Pause
      default: return History
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Experiments</h1>
        <p className="text-muted-foreground mt-1">
          Experiment history and management
        </p>
      </div>

      {/* Filters and Actions */}
      <div className="flex gap-2 items-center justify-between">
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`btn btn-sm ${filter === 'all' ? 'btn-primary' : 'btn-secondary'}`}
          >
            All ({experiments.length})
          </button>
          <button
            onClick={() => setFilter('running')}
            className={`btn btn-sm ${filter === 'running' ? 'btn-primary' : 'btn-secondary'}`}
          >
            Running ({experiments.filter(e => e.status === 'running').length})
          </button>
          <button
            onClick={() => setFilter('completed')}
            className={`btn btn-sm ${filter === 'completed' ? 'btn-primary' : 'btn-secondary'}`}
          >
            Completed
          </button>
          <button
            onClick={() => setFilter('failed')}
            className={`btn btn-sm ${filter === 'failed' ? 'btn-primary' : 'btn-secondary'}`}
          >
            Failed
          </button>
        </div>
        
        <div className="flex gap-2">
          <button className="btn btn-secondary btn-sm flex items-center gap-1">
            <RefreshCw size={14} />
            Refresh
          </button>
          <button className="btn btn-primary btn-sm">
            New Experiment
          </button>
        </div>
      </div>

      {/* Experiments List */}
      <div className="panel">
        <h2 className="panel-title mb-4">Experiments</h2>
        
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-pulse text-muted-foreground">Loading experiments...</div>
          </div>
        ) : filteredExperiments.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <History size={48} className="mx-auto mb-2" />
            <p>No experiments found</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredExperiments.map((exp) => {
              const Icon = getStatusIcon(exp.status)
              return (
                <div key={exp.id} className="border border-border rounded-lg p-4">
                  <div className="flex items justify-between">
                    <div className="flex-1">
                      <div className="font-medium text-foreground mb-1">{exp.name}</div>
                      <div className="text-xs text-muted-foreground">
                        Started: {exp.started}
                        {exp.completed && <> • Completed: {exp.completed}</>}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="flex items-center gap-2">
                          <Icon size={14} className="text-muted-foreground" />
                          <span className="badge text-xs">{exp.status}</span>
                        </div>
                        {exp.rounds && (
                          <div className="text-xs text-muted-foreground mt-1">
                            {exp.rounds} rounds
                          </div>
                        )}
                      </div>
                      
                      <button className="btn btn-ghost btn-sm" aria-label="Actions">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="panel text-center">
          <div className="text-2xl font-bold text-foreground">127</div>
          <div className="text-xs text-muted-foreground">Total Experiments</div>
        </div>
        <div className="panel text-center">
          <div className="text-2xl font-bold text-success">95</div>
          <div className="text-xs text-muted-foreground">Completed</div>
        </div>
        <div className="panel text-center">
          <div className="text-2xl font-bold text-destructive">3</div>
          <div className="text-xs text-muted-foreground">Failed</div>
        </div>
      </div>

      {/* Recent Results */}
      <div className="panel">
        <h3 className="font-medium text-foreground mb-3">Recent Results</h3>
        <div className="overflow-x-auto">
          <table className="table w-full">
            <thead>
              <tr>
                <th>Experiment</th>
                <th>Start</th>
                <th>End</th>
                <th>Rounds</th>
                <th>Loss</th>
                <th>Clients</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredExperiments.slice(0, 5).map((exp) => (
                <tr key={exp.id}>
                  <td className="font-medium text-foreground mono">{exp.name}</td>
                  <td>{exp.started}</td>
                  <td>{exp.completed || '—'}</td>
                  <td className="mono">{exp.rounds}</td>
                  <td className="mono">{exp.loss?.toFixed(4) ?? '—'}</td>
                  <td>{exp.clients}</td>
                  <td><span className={`${getStatusBadge(exp.status)} text-xs`}>{exp.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
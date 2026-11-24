import { useState, useEffect } from 'react'
import { Play, Square, Pause, RefreshCw, Users, Share2 } from 'lucide-react'

interface Experiment {
  id: string
  name: string
  status: 'running' | 'stopped' | 'paused' | 'completed'
  rounds: number
  completed: number
  progress: number
  clients: number
}

export function FederatedLearningPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [loading, setLoading] = useState(true)
  const [activeExperiment, setActiveExperiment] = useState<string | null>(null)

  useEffect(() => {
    // Simulate API call
    setTimeout(() => {
      setExperiments([
        {
          id: 'exp-001',
          name: 'PM2.5 Forecasting Model',
          status: 'running',
          rounds: 500,
          completed: 128,
          progress: 25.6,
          clients: 42,
        },
        {
          id: 'exp-002',
          name: 'Baseline Comparison',
          status: 'completed',
          rounds: 100,
          completed: 100,
          progress: 100,
          clients: 25,
        },
      ])
      setLoading(false)
    }, 500)
  }, [])

  const getStatusBadge = (status: string) => {
    const styles = {
      running: 'badge-success',
      stopped: 'badge',
      paused: 'badge-warning',
      completed: 'badge-primary',
    }
    return styles[status as keyof typeof styles] || 'badge'
  }

  const toggleExperiment = (id: string) => {
    console.log('Toggle experiment:', id)
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Federated Learning</h1>
        <p className="text-muted-foreground mt-1">
          Training orchestration and experiment management
        </p>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-2">
        <button className="btn btn-primary flex items-center gap-2">
          <Play size={16} />
          Start Experiment
        </button>
        <button className="btn btn-secondary flex items-center gap-2">
          <Pause size={16} />
          Pause
        </button>
        <button className="btn btn-secondary flex items-center gap-2">
          <Square size={16} />
          Stop
        </button>
        <button className="btn btn-ghost flex items-center gap-2 ml-auto">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* FL Stats */}
      <div className="grid gap-4 sm:grid-cols-4">
        <FLStatCard
          title="Active Experiments"
          value="1"
          icon={Play}
          color="primary"
        />
        <FLStatCard
          title="Total Rounds"
          value="628"
          icon={Share2}
        />
        <FLStatCard
          title="Running Rounds"
          value="128"
          icon={Users}
          status="ok"
        />
        <FLStatCard
          title="Avg Progress"
          value="85.2%"
          icon={RefreshCw}
        />
      </div>

      {/* Experiments List */}
      <div className="panel">
        <h2 className="panel-title mb-4">Experiments</h2>
        
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-pulse text-muted-foreground">Loading experiments...</div>
          </div>
        ) : (
          <div className="space-y-4">
            {experiments.map((exp) => (
              <div key={exp.id} className="border border-border rounded-lg p-4">
                <div className="flex items justify-between">
                  <div className="flex-1">
                    <div className="font-medium text-foreground mb-2">{exp.name}</div>
                    
                    {/* Progress Bar */}
                    <div className="mb-2">
                      <div className="flex justify-between text-xs text-muted-foreground mb-1">
                        <span>Round {exp.completed} / {exp.rounds}</span>
                        <span>{exp.progress}%</span>
                      </div>
                      <div className="progress">
                        <div 
                          className="progress-fill" 
                          style={{ width: `${exp.progress}%` }}
                        />
                      </div>
                    </div>
                    
                    <div className="text-xs text-muted-foreground">
                      {exp.clients} clients • {exp.status}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <span className={`${getStatusBadge(exp.status)} text-xs`}>
                      {exp.status.charAt(0).toUpperCase() + exp.status.slice(1)}
                    </span>
                    
                    <button 
                      onClick={() => setActiveExperiment(activeExperiment === exp.id ? null : exp.id)}
                      className="btn btn-ghost btn-sm"
                    >
                      {activeExperiment === exp.id ? '-' : '+'}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Training Config */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Training Settings</h3>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-muted-foreground">Batch Size</label>
              <input type="number" value="32" className="input mt-1" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Learning Rate</label>
              <input type="number" step="0.001" value="0.01" className="input mt-1" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Rounds</label>
              <input type="number" value="500" className="input mt-1" />
            </div>
          </div>
        </div>

        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Latest Model</h3>
          <div className="space-y-2">
            <div>
              <span className="text-sm text-muted-foreground">Version</span>
              <div className="font-mono text-foreground">model_v3.2_round_128</div>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Validation Loss</span>
              <div className="font-mono text-success">0.0423</div>
            </div>
            <div>
              <span className="text-sm text-muted-foreground">Parameters</span>
              <div className="font-mono text-foreground">12.8M</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

interface FLStatCardProps {
  title: string
  value: string | number
  icon: any
  color?: 'primary'
  status?: 'ok' | 'warning' | 'neutral'
}

function FLStatCard({ title, value, icon: Icon, color = 'neutral', status = 'neutral' }: FLStatCardProps) {
  const colors = {
    primary: 'text-primary',
    neutral: status === 'ok' ? 'text-success' : 'text-foreground',
  }

  return (
    <div className="panel text-center">
      <Icon size={20} className={`mx-auto mb-2 ${colors[color as keyof typeof colors] || 'text-foreground'}`} />
      <div className="text-xl font-bold text-foreground">{value}</div>
      <div className="text-xs text-muted-foreground">{title}</div>
    </div>
  )
}
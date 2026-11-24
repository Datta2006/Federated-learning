import { useState, useEffect } from 'react'
import { Server, Plus, Play, Pause, Settings, Trash2 } from 'lucide-react'

interface Gateway {
  id: string
  name: string
  status: 'online' | 'offline' | 'starting'
  workers: number
  latency: number
  location: string
}

export function GatewaysPage() {
  const [gateways, setGateways] = useState<Gateway[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Simulate API call
    setTimeout(() => {
      setGateways([
        {
          id: 'gw-001',
          name: 'Primary Gateway',
          status: 'online',
          workers: 18,
          latency: 12,
          location: 'Data Center A',
        },
        {
          id: 'gw-002',
          name: 'Edge Gateway 1',
          status: 'online',
          workers: 12,
          latency: 24,
          location: 'Building B',
        },
        {
          id: 'gw-003',
          name: 'Edge Gateway 2',
          status: 'offline',
          workers: 8,
          latency: 0,
          location: 'Building C',
        },
      ])
      setLoading(false)
    }, 500)
  }, [])

  const getStatusBadge = (status: string) => {
    const styles = {
      online: 'badge-success',
      offline: 'badge',
      starting: 'badge-warning',
    }
    return styles[status as keyof typeof styles] || 'badge'
  }

  const getStatusText = (status: string) => {
    const texts = {
      online: 'Online',
      offline: 'Offline',
      starting: 'Starting',
    }
    return texts[status as keyof typeof texts] || status
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Gateways</h1>
        <p className="text-muted-foreground mt-1">
          Gateway orchestration and management
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-2">
        <button className="btn btn-primary flex items-center gap-2">
          <Plus size={16} />
          Add Gateway
        </button>
        <button className="btn btn-secondary flex items-center gap-2">
          <Play size={16} />
          Start All
        </button>
        <button className="btn btn-secondary flex items-center gap-2">
          <Pause size={16} />
          Stop All
        </button>
      </div>

      {/* Gateway Stats */}
      <div className="grid gap-4 sm:grid-cols-3">
        <GatewayStatCard
          title="Total Gateways"
          value="3"
          description="Active gateways"
        />
        <GatewayStatCard
          title="Online"
          value="2"
          description="Working properly"
          status="ok"
        />
        <GatewayStatCard
          title="Offline"
          value="1"
          description="Need attention"
          status="warning"
        />
      </div>

      {/* Gateway List */}
      <div className="panel">
        <h2 className="panel-title mb-4">Gateway List</h2>
        
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-pulse text-muted-foreground">Loading gateways...</div>
          </div>
        ) : (
          <div className="space-y-3">
            {gateways.map((gateway) => (
              <div key={gateway.id} className="border border-border rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                      <Server size={20} className="text-primary" />
                    </div>
                    <div>
                      <div className="font-medium text-foreground">{gateway.name}</div>
                      <div className="text-sm text-muted-foreground">
                        {gateway.location} • {gateway.workers} workers • {gateway.latency}ms latency
                      </div>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <span className={`${getStatusBadge(gateway.status)} text-xs`}>
                      {getStatusText(gateway.status)}
                    </span>
                    
                    <button className="btn btn-ghost btn-sm" aria-label="Configure">
                      <Settings size={16} />
                    </button>
                    <button className="btn btn-ghost btn-sm text-destructive" aria-label="Delete">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Gateway Actions */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Network Map</h3>
          <div className="border-2 border-dashed border-muted rounded-lg h-48 flex items-center justify-center">
            <div className="text-center">
              <Server size={48} className="mx-auto mb-2 text-muted-foreground" />
              <p className="text-muted-foreground">Network visualization will appear here</p>
            </div>
          </div>
        </div>

        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Quick Actions</h3>
          <div className="space-y-2">
            <button className="btn btn-secondary w-full justify-start">
              <Settings size={16} className="mr-2" />
              Configure All Gateways
            </button>
            <button className="btn btn-secondary w-full justify-start">
              <Play size={16} className="mr-2" />
              Reboot Offline Gateways
            </button>
            <button className="btn btn-secondary w-full justify-start">
              <Download size={16} className="mr-2" />
              Download Configuration
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

interface GatewayStatCardProps {
  title: string
  value: string | number
  description: string
  status?: 'ok' | 'warning' | 'neutral'
}

function GatewayStatCard({ title, value, description, status = 'neutral' }: GatewayStatCardProps) {
  const colors = {
    ok: 'text-success',
    warning: 'text-warning',
    neutral: 'text-foreground',
  }

  const borderColors = {
    ok: 'border-success/20',
    warning: 'border-warning/20',
    neutral: 'border-border',
  }

  return (
    <div className={`panel text-center border ${borderColors[status]}`}>
      <div className={`text-2xl font-bold ${colors[status]}`}>{value}</div>
      <div className="text-sm font-medium text-foreground">{title}</div>
      <div className="text-xs text-muted-foreground mt-1">{description}</div>
    </div>
  )
}
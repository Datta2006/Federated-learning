import { useState, useEffect } from 'react'
import { Network, Users, Clock, Activity } from 'lucide-react'

export function NetworkPage() {
  const [networkData, setNetworkData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Simulate API call
    setTimeout(() => {
      setNetworkData({
        nodes: 42,
        online: 38,
        offline: 4,
        edges: 128,
        latency: '24ms',
        bandwidth: '5.2 Mbps',
      })
      setLoading(false)
    }, 500)
  }, [])

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Network Topology</h1>
        <p className="text-muted-foreground mt-1">
          Live network visualization and status
        </p>
      </div>

      {/* Network Stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <NetworkStatCard
          icon={Network}
          title="Nodes"
          value="42"
          change="+2 from last hour"
        />
        <NetworkStatCard
          icon={Users}
          title="Online"
          value="38"
          change="90.5% uptime"
          status="ok"
        />
        <NetworkStatCard
          icon={Clock}
          title="Avg Latency"
          value="24ms"
          change="↓ 3ms"
          status="ok"
        />
        <NetworkStatCard
          icon={Activity}
          title="Bandwidth"
          value="5.2 Mbps"
          change="↑ 0.8 Mbps"
        />
      </div>

      {/* Network Topology Visualization */}
      <div className="panel">
        <h2 className="panel-title mb-4">Network Status</h2>
        
        {loading ? (
          <div className="text-center py-8">
            <div className="animate-pulse text-muted-foreground">Loading network data...</div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Network Graph Placeholder */}
            <div className="border-2 border-dashed border-muted rounded-lg h-64 flex items-center justify-center">
              <div className="text-center">
                <Network size={48} className="mx-auto mb-2 text-muted-foreground" />
                <p className="text-muted-foreground">Network visualization will appear here</p>
                <p className="text-sm mt-1">Connected: {networkData.online}/{networkData.nodes} nodes</p>
              </div>
            </div>

            {/* Node Status Table */}
            <div className="overflow-x-auto">
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>Node ID</th>
                    <th>Status</th>
                    <th>Latency</th>
                    <th>Uptime</th>
                    <th>Last Seen</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="mono">node-001</td>
                    <td><span className="badge badge-success">Online</span></td>
                    <td className="mono">12ms</td>
                    <td>99.8%</td>
                    <td className="text-sm text-muted-foreground">2 min ago</td>
                  </tr>
                  <tr>
                    <td className="mono">node-002</td>
                    <td><span className="badge badge-success">Online</span></td>
                    <td className="mono">18ms</td>
                    <td>99.5%</td>
                    <td className="text-sm text-muted-foreground">5 min ago</td>
                  </tr>
                  <tr>
                    <td className="mono">node-003</td>
                    <td><span className="badge">Offline</span></td>
                    <td className="mono">—</td>
                    <td>87.2%</td>
                    <td className="text-sm text-muted-foreground">15 min ago</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Network Metrics */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Traffic Overview</h3>
          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span>Upload</span>
                <span className="mono">2.1 Mbps</span>
              </div>
              <div className="h-2 bg-muted/30 rounded-full overflow-hidden">
                <div className="h-full bg-primary rounded-full" style={{ width: '65%' }} />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span>Download</span>
                <span className="mono">3.1 Mbps</span>
              </div>
              <div className="h-2 bg-muted/30 rounded-full overflow-hidden">
                <div className="h-full bg-success rounded-full" style={{ width: '78%' }} />
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <h3 className="font-medium text-foreground mb-3">Recent Events</h3>
          <div className="space-y-2">
            <div className="text-xs">
              <span className="text-foreground">node-002</span> reconnected
            </div>
            <div className="text-xs">
              <span className="text-foreground">node-003</span> went offline
            </div>
            <div className="text-xs">
              Network heartbeat OK
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

interface NetworkStatCardProps {
  icon: any
  title: string
  value: string | number
  change?: string
  status?: 'ok' | 'warning' | 'error'
}

function NetworkStatCard({ icon: Icon, title, value, change, status = 'ok' }: NetworkStatCardProps) {
  const colors = {
    ok: 'text-foreground',
    warning: 'text-warning',
    error: 'text-destructive',
  }

  return (
    <div className="panel text-center">
      <Icon size={24} className={`mx-auto mb-2 ${colors[status]}`} />
      <div className={`text-2xl font-bold ${colors[status]}`}>{value}</div>
      <div className="text-sm text-muted-foreground">{title}</div>
      {change && <div className="text-xs text-muted-foreground mt-1">{change}</div>}
    </div>
  )
}
import { useEffect, useState } from 'react'
import { Users, Zap, Network, Cpu, HardDrive, Wifi, AlertTriangle, CheckCircle, Clock } from 'lucide-react'
import { StatCard } from '@/components/cards/StatCard'
import { StatusBadge } from '@/components/cards/StatusBadge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useExperimentStore } from '@/stores/experimentStore'

interface Worker {
  id: string
  name: string
  status: 'online' | 'offline' | 'warning' | 'critical'
  ip_address?: string
  role: 'gateway' | 'worker'
  region?: string
  version?: string
  cpu_usage?: number
  memory_usage?: number
  disk_usage?: number
  connected_at?: string
  last_heartbeat?: string
  experiments?: number
}

// Generate mock worker data
const generateWorkerData = (): Worker[] => {
  const workers: Worker[] = []
  const roles = ['gateway', 'worker']
  const statuses: Worker['status'][] = ['online', 'warning', 'offline', 'critical']
  const regions = ['North America', 'Europe', 'Asia-Pacific', 'South America', 'Africa']

  for (let i = 1; i <= 12; i++) {
    const status = i < 10 ? 'online' : i < 11 ? 'warning' : 'offline'
    workers.push({
      id: `worker-${i.toString().padStart(3, '0')}`,
      name: `Worker-${i}`,
      status,
      ip_address: `192.168.1.${100 + i}`,
      role: roles[i % 2] as 'gateway' | 'worker',
      region: regions[i % regions.length],
      version: `v2.3.${i % 5}`,
      cpu_usage: status === 'online' ? Math.floor(Math.random() * 40 + 20) : undefined,
      memory_usage: status === 'online' ? Math.floor(Math.random() * 30 + 40) : undefined,
      disk_usage: Math.floor(Math.random() * 20 + 60),
      connected_at: status === 'online' ? new Date(Date.now() - Math.random() * 86400000).toISOString() : undefined,
      last_heartbeat: status === 'online' ? new Date(Date.now() - Math.random() * 300000).toISOString() : undefined,
      experiments: status === 'online' ? Math.floor(Math.random() * 3) : 0,
    })
  }
  return workers
}

export function WorkersPage() {
  const { experiments } = useExperimentStore()
  const [workers, setWorkers] = useState<Worker[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'gateways' | 'workers'>('overview')
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    // In a real app, this would fetch from the API
    setWorkers(generateWorkerData())
  }, [])

  const onlineWorkers = workers.filter(w => w.status === 'online')
  const warningWorkers = workers.filter(w => w.status === 'warning')
  const offlineWorkers = workers.filter(w => w.status === 'offline')
  const criticalWorkers = workers.filter(w => w.status === 'critical')

  const gateways = onlineWorkers.filter(w => w.role === 'gateway')
  const activeWorkers = onlineWorkers.filter(w => w.role === 'worker')

  const filteredWorkers = workers.filter(w =>
    w.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    w.ip_address?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    w.region?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const totalCpu = onlineWorkers.reduce((sum, w) => sum + (w.cpu_usage || 0), 0)
  const totalMemory = onlineWorkers.reduce((sum, w) => sum + (w.memory_usage || 0), 0)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Workers & Gateways
          </h2>
          <p className="text-muted-foreground">
            Monitor your federated learning nodes in real-time
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {onlineWorkers.length} Online • {warningWorkers.length} Warning • {offlineWorkers.length} Offline
          </Badge>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Nodes"
          value={workers.length}
          description="All gateways and workers"
          icon={<Users className="h-4 w-4" />}
          gradient
        />
        <StatCard
          title="Online Nodes"
          value={onlineWorkers.length}
          description="Currently connected"
          icon={<CheckCircle className="h-4 w-4" />}
          gaugeValue={(onlineWorkers.length / workers.length) * 100}
        />
        <StatCard
          title="Gateways"
          value={gateways.length}
          description="Active gateways"
          icon={<Network className="h-4 w-4" />}
        />
        <StatCard
          title="Avg. CPU Usage"
          value={totalCpu / (onlineWorkers.length || 1)}
          description="Across all online nodes"
          icon={<Cpu className="h-4 w-4" />}
        />
      </div>

      {/* Health Summary */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>System Health</CardTitle>
            <CardDescription>Current status overview</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4 text-success-500" />
                <span className="text-sm">Healthy</span>
              </div>
              <StatusBadge status="online" size="sm" />
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-amber-500" />
                <span className="text-sm">Degraded</span>
              </div>
              <StatusBadge status="warning" size="sm" />
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-destructive-500" />
                <span className="text-sm">Critical</span>
              </div>
              <StatusBadge status="critical" size="sm" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Resource Usage</CardTitle>
            <CardDescription>Across online nodes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm text-muted-foreground">CPU</span>
                <span className="text-sm font-medium">{totalCpu.toFixed(1)}%</span>
              </div>
              <div className="h-2 rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-success-500"
                  style={{ width: `${totalCpu / (onlineWorkers.length || 1) * 2}%` }}
                />
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Memory</span>
                <span className="text-sm font-medium">{totalMemory.toFixed(1)}%</span>
              </div>
              <div className="h-2 rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-airfed-500"
                  style={{ width: `${totalMemory / (onlineWorkers.length || 1) * 2}%` }}
                />
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Disk</span>
                <span className="text-sm font-medium">
                  {(onlineWorkers.reduce((sum, w) => sum + (w.disk_usage || 0), 0) / (onlineWorkers.length || 1)).toFixed(1)}%
                </span>
              </div>
              <div className="h-2 rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-emerald-500"
                  style={{ width: `${onlineWorkers.reduce((sum, w) => sum + (w.disk_usage || 0), 0) / (onlineWorkers.length || 1) / 1.5}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Network Status</CardTitle>
            <CardDescription>Current connections</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Connected Gateways</span>
              <Badge>{gateways.length}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Connected Workers</span>
              <Badge>{activeWorkers.length}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Pending Reconnections</span>
              <Badge variant="destructive">{offlineWorkers.length}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Avg. Latency</span>
              <span className="font-medium">42ms</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab as any} className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="gateways">Gateways ({gateways.length})</TabsTrigger>
          <TabsTrigger value="workers">Workers ({activeWorkers.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <Card>
            <CardHeader>
              <CardTitle>All Nodes</CardTitle>
              <CardDescription>Search and filter your nodes</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-4">
                <input
                  type="text"
                  placeholder="Search by name, IP, or region..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full rounded-lg border border-input bg-background px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              <div className="space-y-2">
                {filteredWorkers.map((worker) => (
                  <div
                    key={worker.id}
                    className="flex items-center justify-between rounded-lg border border-border bg-background/50 p-4"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                        {worker.role === 'gateway' ? (
                          <Network className="h-5 w-5" />
                        ) : (
                          <Users className="h-5 w-5" />
                        )}
                      </div>
                      <div>
                        <p className="font-medium text-foreground">{worker.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {worker.ip_address} • {worker.region}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {worker.cpu_usage !== undefined && (
                        <div className="hidden sm:block text-xs text-muted-foreground">
                          CPU: {worker.cpu_usage}%
                        </div>
                      )}
                      <StatusBadge status={worker.status} />
                      <Badge variant="outline" className="text-xs">
                        {worker.role}
                      </Badge>
                    </div>
                  </div>
                ))}
                {filteredWorkers.length === 0 && (
                  <div className="py-8 text-center">
                    <p className="text-muted-foreground">No nodes found matching your search</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="gateways">
          <Card>
            <CardHeader>
              <CardTitle>Gateways</CardTitle>
              <CardDescription>{gateways.length} active gateways</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {gateways.map((gateway) => (
                  <div
                    key={gateway.id}
                    className="border border-border rounded-lg p-4 bg-background/50"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-medium text-foreground">{gateway.name}</h3>
                      <StatusBadge status={gateway.status} size="sm" />
                    </div>
                    <p className="text-sm text-muted-foreground mb-3">
                      {gateway.ip_address}
                    </p>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Region</span>
                        <span>{gateway.region}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Version</span>
                        <span>{gateway.version}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Active Experiments</span>
                        <span>{gateway.experiments}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="workers">
          <Card>
            <CardHeader>
              <CardTitle>Workers</CardTitle>
              <CardDescription>{activeWorkers.length} active workers</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {activeWorkers.map((worker) => (
                  <div
                    key={worker.id}
                    className="border border-border rounded-lg p-4 bg-background/50"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-medium text-foreground">{worker.name}</h3>
                      <StatusBadge status={worker.status} size="sm" />
                    </div>
                    <p className="text-sm text-muted-foreground mb-3">
                      {worker.ip_address}
                    </p>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Region</span>
                        <span>{worker.region}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">CPU</span>
                        <span>{worker.cpu_usage}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Memory</span>
                        <span>{worker.memory_usage}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Disk</span>
                        <span>{worker.disk_usage}%</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
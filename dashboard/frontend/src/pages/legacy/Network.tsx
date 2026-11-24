import { useEffect, useState } from 'react'
import { Network, Activity, Globe, ArrowUp, ArrowDown, Wifi, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, PieChart, Pie, Cell } from 'recharts'

interface NetworkNode {
  id: string
  name: string
  type: 'gateway' | 'worker'
  status: 'online' | 'offline' | 'warning'
  ip_address?: string
  port?: number
  region?: string
  data_transferred?: number
  packets?: number
}

interface NetworkLink {
  source: string
  target: string
  bytes_up: number
  bytes_down: number
  latency_ms: number
  status: 'active' | 'idle' | 'degraded'
}

// Generate mock network topology
const generateNetworkData = (): { nodes: NetworkNode[]; links: NetworkLink[] } => {
  const nodes: NetworkNode[] = [
    { id: 'gateway-1', name: 'Gateway-NA', type: 'gateway', status: 'online', ip_address: '192.168.1.1', region: 'North America', data_transferred: 45.2, packets: 12500 },
    { id: 'worker-1', name: 'Worker-1', type: 'worker', status: 'online', ip_address: '192.168.1.11', region: 'North America', data_transferred: 2.1, packets: 580 },
    { id: 'worker-2', name: 'Worker-2', type: 'worker', status: 'online', ip_address: '192.168.1.12', region: 'North America', data_transferred: 3.8, packets: 920 },
    { id: 'worker-3', name: 'Worker-3', type: 'worker', status: 'warning', ip_address: '192.168.1.13', region: 'Europe', data_transferred: 1.5, packets: 420 },
    { id: 'gateway-2', name: 'Gateway-EU', type: 'gateway', status: 'online', ip_address: '192.168.2.1', region: 'Europe', data_transferred: 32.1, packets: 8900 },
    { id: 'worker-4', name: 'Worker-4', type: 'worker', status: 'online', ip_address: '192.168.2.11', region: 'Europe', data_transferred: 4.2, packets: 1100 },
    { id: 'worker-5', name: 'Worker-5', type: 'worker', status: 'offline', ip_address: '192.168.2.12', region: 'Asia', data_transferred: 0, packets: 0 },
    { id: 'gateway-3', name: 'Gateway-APAC', type: 'gateway', status: 'online', ip_address: '192.168.3.1', region: 'Asia-Pacific', data_transferred: 28.7, packets: 6500 },
    { id: 'worker-6', name: 'Worker-6', type: 'worker', status: 'online', ip_address: '192.168.3.11', region: 'Asia-Pacific', data_transferred: 5.6, packets: 1350 },
    { id: 'central', name: 'Central Server', type: 'worker', status: 'online', ip_address: '10.0.0.1', data_transferred: 110, packets: 28000 },
  ]

  const links: NetworkLink[] = [
    { source: 'gateway-1', target: 'central', bytes_up: 22.5, bytes_down: 22.7, latency_ms: 15, status: 'active' },
    { source: 'gateway-2', target: 'central', bytes_up: 16.1, bytes_down: 16.0, latency_ms: 45, status: 'active' },
    { source: 'gateway-3', target: 'central', bytes_up: 14.3, bytes_down: 14.4, latency_ms: 62, status: 'active' },
    { source: 'worker-1', target: 'gateway-1', bytes_up: 1.05, bytes_down: 1.05, latency_ms: 2, status: 'active' },
    { source: 'worker-2', target: 'gateway-1', bytes_up: 1.9, bytes_down: 1.9, latency_ms: 3, status: 'active' },
    { source: 'worker-3', target: 'gateway-2', bytes_up: 0.75, bytes_down: 0.75, latency_ms: 22, status: 'degraded' },
    { source: 'worker-4', target: 'gateway-2', bytes_up: 2.1, bytes_down: 2.1, latency_ms: 3, status: 'active' },
    { source: 'worker-6', target: 'gateway-3', bytes_up: 2.8, bytes_down: 2.8, latency_ms: 5, status: 'active' },
  ]

  return { nodes, links }
}

export function NetworkPage() {
  const [networkData, setNetworkData] = useState<{ nodes: NetworkNode[]; links: NetworkLink[] }>({ nodes: [], links: [] })
  const [selectedRegion, setSelectedRegion] = useState<string>('all')
  const [isActive, setIsActive] = useState(true)

  useEffect(() => {
    setNetworkData(generateNetworkData())
    const interval = setInterval(() => {
      setNetworkData(generateNetworkData())
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const nodes = networkData.nodes
  const links = networkData.links

  const filteredNodes = selectedRegion === 'all'
    ? nodes
    : nodes.filter(n => n.region === selectedRegion)

  const totalUp = links.reduce((sum, l) => sum + l.bytes_up, 0)
  const totalDown = links.reduce((sum, l) => sum + l.bytes_down, 0)
  const totalLatency = links.reduce((sum, l) => sum + l.latency_ms, 0) / links.length

  // Regional traffic data
  const regionalData = [
    { name: 'North America', up: 22.5, down: 22.7 },
    { name: 'Europe', up: 16.1, down: 16.0 },
    { name: 'Asia-Pacific', up: 14.3, down: 14.4 },
  ]

  // Node types distribution
  const typeData = [
    { name: 'Gateways', value: nodes.filter(n => n.type === 'gateway').length, color: '#0ea5e9' },
    { name: 'Workers', value: nodes.filter(n => n.type === 'worker').length, color: '#10b981' },
  ]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Network Topology
          </h2>
          <p className="text-muted-foreground">
            Monitor network traffic and node connectivity
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={isActive ? 'default' : 'outline'} className="text-xs">
            {isActive ? 'Real-time' : 'Snapshot'}
          </Badge>
        </div>
      </div>

      {/* Network Stats */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Traffic</CardTitle>
            <Wifi className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalUp.toFixed(1)} MB</div>
            <p className="text-xs text-muted-foreground">Up: {totalUp.toFixed(1)} MB</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Downstream</CardTitle>
            <ArrowDown className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalDown.toFixed(1)} MB</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Avg Latency</CardTitle>
            <Wifi className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalLatency.toFixed(0)}ms</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Active Links</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {links.filter(l => l.status === 'active').length}/{links.length}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Topology Visualization */}
      <Card>
        <CardHeader>
          <CardTitle>Network Graph</CardTitle>
          <CardDescription>Visual representation of node connections</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-96">
            <svg viewBox="0 0 800 400" className="w-full h-full">
              <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                  <polygon points="0 0, 10 3.5, 0 7" fill="#64748b" />
                </marker>
              </defs>

              {/* Links */}
              {links.map((link, i) => (
                <g key={i}>
                  <line
                    x1={getNodeX(link.source)}
                    y1={getNodeY(link.source)}
                    x2={getNodeX(link.target)}
                    y2={getNodeY(link.target)}
                    stroke={link.status === 'active' ? '#cbd5e1' : link.status === 'degraded' ? '#f59e0b' : '#64748b'}
                    strokeWidth={link.status === 'active' ? 2 : link.status === 'degraded' ? 1.5 : 1}
                    strokeDasharray={link.status === 'active' ? 'none' : '5 5'}
                    marker-end="url(#arrowhead)"
                  />
                  <text
                    x={(getNodeX(link.source) + getNodeX(link.target)) / 2 - 20}
                    y={(getNodeY(link.source) + getNodeY(link.target)) / 2 - 10}
                    fontSize="10"
                    fill="#64748b"
                  >
                    {link.bytes_up}MB
                  </text>
                </g>
              ))}

              {/* Nodes */}
              {nodes.map((node) => (
                <g key={node.id}>
                  <circle
                    cx={getNodeX(node.id)}
                    cy={getNodeY(node.id)}
                    r={node.type === 'gateway' ? 15 : 8}
                    fill={node.status === 'online' ? (node.type === 'gateway' ? '#0ea5e9' : '#10b981') : node.status === 'warning' ? '#f59e0b' : '#64748b'}
                    stroke="#ffffff"
                    strokeWidth={2}
                  />
                  <text
                    x={getNodeX(node.id)}
                    y={getNodeY(node.id) + 25}
                    fontSize="10"
                    textAnchor="middle"
                    fill="#64748b"
                  >
                    {node.name}
                  </text>
                </g>
              ))}
            </svg>
          </div>
        </CardContent>
      </Card>

      {/* Traffic Analysis */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Regional Traffic</CardTitle>
            <CardDescription>Data transfer by region</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={regionalData}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip formatter={(value: number) => `${value.toFixed(1)} MB`} />
                <Legend />
                <Bar dataKey="up" fill="#0ea5e9" name="Upload" />
                <Bar dataKey="down" fill="#10b981" name="Download" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Node Distribution</CardTitle>
            <CardDescription>Nodes by type and status</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={typeData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                >
                  {typeData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Node List */}
      <Card>
        <CardHeader>
          <CardTitle>Network Nodes</CardTitle>
          <CardDescription>Status and connectivity details</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left p-4 font-medium">Node</th>
                  <th className="text-left p-4 font-medium">IP Address</th>
                  <th className="text-left p-4 font-medium">Region</th>
                  <th className="text-left p-4 font-medium">Type</th>
                  <th className="text-left p-4 font-medium">Status</th>
                  <th className="text-right p-4 font-medium">Traffic</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => (
                  <tr key={node.id} className="border-b border-border hover:bg-muted/50">
                    <td className="p-4 font-medium">{node.name}</td>
                    <td className="p-4">{node.ip_address}</td>
                    <td className="p-4">{node.region}</td>
                    <td className="p-4">
                      <Badge variant="outline" className="text-xs">{node.type}</Badge>
                    </td>
                    <td className="p-4">
                      {node.status === 'online' ? (
                        <Badge className="bg-success-100 text-success-700">Online</Badge>
                      ) : node.status === 'warning' ? (
                        <Badge className="bg-amber-100 text-amber-700">Warning</Badge>
                      ) : (
                        <Badge className="bg-gray-100 text-gray-700">Offline</Badge>
                      )}
                    </td>
                    <td className="p-4 text-right">{node.data_transferred?.toFixed(1)} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function getNodeX(id: string): number {
  const positions: Record<string, number> = {
    'gateway-1': 100,
    'gateway-2': 400,
    'gateway-3': 700,
    'central': 400,
    'worker-1': 80,
    'worker-2': 150,
    'worker-3': 350,
    'worker-4': 450,
    'worker-5': 650,
    'worker-6': 750,
  }
  return positions[id] || 400
}

function getNodeY(id: string): number {
  const positions: Record<string, number> = {
    'gateway-1': 200,
    'gateway-2': 200,
    'gateway-3': 200,
    'central': 200,
    'worker-1': 150,
    'worker-2': 250,
    'worker-3': 130,
    'worker-4': 270,
    'worker-5': 130,
    'worker-6': 270,
  }
  return positions[id] || 200
}
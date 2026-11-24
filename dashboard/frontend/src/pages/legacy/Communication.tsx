import { useEffect, useState } from 'react'
import { Zap, MessageSquare, Send, Clock, BarChart3, Activity, Globe, Layers, Users } from 'lucide-react'
import { StatCard } from '@/components/cards/StatCard'
import { StatusBadge } from '@/components/cards/StatusBadge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, LineChart, Line, AreaChart, Area, Dot } from 'recharts'
import { useExperimentStore } from '@/stores/experimentStore'
import { cn } from '@/lib/utils'

interface CommunicationMetrics {
  timestamp: string
  bytes_up: number
  bytes_down: number
  packets_up: number
  packets_down: number
  latency_ms: number
  packet_loss: number
  compression_ratio: number
  encryption_overhead: number
}

interface LinkStats {
  gateway_id: string
  bytes_up: number
  bytes_down: number
  latency_ms: number
  packet_loss: number
  active_workers: number
}

// Generate mock communication data
const generateCommunicationData = (intervals: number): CommunicationMetrics[] => {
  const data: CommunicationMetrics[] = []
  const baseBytesUp = 2.5
  const baseBytesDown = 2.2

  for (let i = intervals; i >= 0; i--) {
    const time = new Date(Date.now() - i * 60 * 1000)
    const variation = Math.sin(i / 3) * 0.5 + (Math.random() - 0.5)

    data.push({
      timestamp: time.toISOString(),
      bytes_up: Math.max(0, baseBytesUp + variation + Math.random() * 0.3),
      bytes_down: Math.max(0, baseBytesDown + variation + Math.random() * 0.3),
      packets_up: Math.floor(1200 + Math.random() * 200),
      packets_down: Math.floor(1000 + Math.random() * 200),
      latency_ms: Math.max(5, 15 + variation * 10 + Math.random() * 5),
      packet_loss: Math.max(0, Math.min(5, Math.random() * 2)),
      compression_ratio: 2.1 + Math.random() * 0.3,
      encryption_overhead: 0.05 + Math.random() * 0.02,
    })
  }
  return data
}

// Generate link statistics
const generateLinkStats = (): LinkStats[] => {
  const gateways = ['Gateway-NA', 'Gateway-EU', 'Gateway-APAC']
  const regions = ['North America', 'Europe', 'Asia-Pacific']

  return gateways.map((name, i) => ({
    gateway_id: `gateway-${i + 1}`,
    bytes_up: 22.5 - i * 5,
    bytes_down: 22.7 - i * 5,
    latency_ms: 15 + i * 15,
    packet_loss: 0.1 + i * 0.2,
    active_workers: 5 - i * 1,
  }))
}

const formatBytes = (gb: number) => `${gb.toFixed(1)} GB`
const formatMbps = (gb: number) => `${gb.toFixed(2)} Mbps`

export function CommunicationPage() {
  const { experiments } = useExperimentStore()
  const [commData, setCommData] = useState<CommunicationMetrics[]>([])
  const [linkStats, setLinkStats] = useState<LinkStats[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'links' | 'optimization'>('overview')
  const [timeRange, setTimeRange] = useState<'hour' | 'day' | 'week'>('hour')

  useEffect(() => {
    const intervals = timeRange === 'hour' ? 60 : timeRange === 'day' ? 1440 : 10080
    setCommData(generateCommunicationData(intervals))
    setLinkStats(generateLinkStats())
  }, [timeRange])

  const totalUp = commData.reduce((sum, d) => sum + d.bytes_up, 0)
  const totalDown = commData.reduce((sum, d) => sum + d.bytes_down, 0)
  const avgLatency = commData.reduce((sum, d) => sum + d.latency_ms, 0) / commData.length
  const avgPacketLoss = commData.reduce((sum, d) => sum + d.packet_loss, 0) / commData.length
  const avgCompression = commData.reduce((sum, d) => sum + d.compression_ratio, 0) / commData.length

  const throughputData = commData.map(d => ({
    time: new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    Upload: d.bytes_up,
    Download: d.bytes_down,
  }))

  const latencyData = commData.map(d => ({
    timestamp: new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    Latency: d.latency_ms,
    'Packet Loss': d.packet_loss,
  }))

  const packetData = commData.map(d => ({
    timestamp: new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    'Sent Packets': d.packets_up,
    'Received Packets': d.packets_down,
  }))

  const throughputMb = totalUp / 1000
  const downloadMb = totalDown / 1000

  const totalPacketsUp = commData.reduce((sum, d) => sum + d.packets_up, 0)
  const totalPacketsDown = commData.reduce((sum, d) => sum + d.packets_down, 0)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Communication Metrics
          </h2>
          <p className="text-muted-foreground">
            Monitor network traffic and data transfer efficiency
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {avgPacketLoss.toFixed(2)}% Packet Loss • {avgLatency.toFixed(0)}ms Latency
          </Badge>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Upload"
          value={`${throughputMb.toFixed(1)} GB`}
          description="All communication upstream"
          icon={<Send className="h-4 w-4" />}
          gradient
        />
        <StatCard
          title="Total Download"
          value={`${downloadMb.toFixed(1)} GB`}
          description="All communication downstream"
          icon={<MessageSquare className="h-4 w-4" />}
        />
        <StatCard
          title="Avg. Latency"
          value={`${avgLatency.toFixed(1)}ms`}
          description="Network delay"
          icon={<Clock className="h-4 w-4" />}
        />
        <StatCard
          title="Compression Ratio"
          value={`${avgCompression.toFixed(1)}x`}
          description="Data reduction"
          icon={<Layers className="h-4 w-4" />}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab as any} className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="links">Links</TabsTrigger>
          <TabsTrigger value="optimization">Optimization</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Throughput</CardTitle>
                <CardDescription>Data transfer rates</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <AreaChart data={throughputData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="time" />
                    <YAxis />
                    <Tooltip formatter={(value: number) => `${value.toFixed(2)} GB`} />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="Upload"
                      stackId="1"
                      stroke="#0ea5e9"
                      fill="rgba(14, 165, 233, 0.3)"
                    />
                    <Area
                      type="monotone"
                      dataKey="Download"
                      stackId="1"
                      stroke="#10b981"
                      fill="rgba(16, 185, 129, 0.3)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Latency & Packet Loss</CardTitle>
                <CardDescription>Network stability metrics</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={latencyData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="timestamp" />
                    <YAxis yAxisId="left" />
                    <YAxis yAxisId="right" orientation="right" />
                    <Tooltip />
                    <Legend />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="Latency"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="Latency (ms)"
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="Packet Loss"
                      stroke="#ef4444"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="Packet Loss (%)"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="links">
          <Card>
            <CardHeader>
              <CardTitle>Gateway Links</CardTitle>
              <CardDescription>Data transfer by gateway</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="p-4 text-left font-medium">Gateway</th>
                      <th className="p-4 text-left font-medium">Region</th>
                      <th className="p-4 text-left font-medium">Upload</th>
                      <th className="p-4 text-left font-medium">Download</th>
                      <th className="p-4 text-left font-medium">Latency</th>
                      <th className="p-4 text-left font-medium">Packet Loss</th>
                      <th className="p-4 text-right font-medium">Workers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {linkStats.map((link) => (
                      <tr key={link.gateway_id} className="border-b border-border hover:bg-muted/50">
                        <td className="p-4 font-medium">
                          {link.gateway_id.replace('gateway-', 'Gateway-')}
                        </td>
                        <td className="p-4">
                          {['North America', 'Europe', 'Asia-Pacific'][parseInt(link.gateway_id.split('-')[1] ?? '1') - 1]}
                        </td>
                        <td className="p-4 font-mono">
                          {formatMbps(link.bytes_up)}
                        </td>
                        <td className="p-4 font-mono">
                          {formatMbps(link.bytes_down)}
                        </td>
                        <td className="p-4">
                          <span className={link.latency_ms > 40 ? 'text-destructive-600' : 'text-success-600'}>
                            {link.latency_ms} ms
                          </span>
                        </td>
                        <td className="p-4">
                          <span className={link.packet_loss > 1 ? 'text-destructive-600' : 'text-success-600'}>
                            {link.packet_loss.toFixed(2)}%
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <Badge variant="outline">{link.active_workers}</Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="optimization">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Compression Efficiency</CardTitle>
                <CardDescription>Data reduction metrics</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Total Data Saved</span>
                    <span className="text-sm font-medium">{((totalUp + totalDown) * 0.53).toFixed(2)} GB</span>
                  </div>
                  <Progress value={53} />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="text-center">
                    <p className="text-2xl font-bold text-airfed-600">{avgCompression.toFixed(1)}x</p>
                    <p className="text-xs text-muted-foreground">Avg Compression Ratio</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold text-airfed-600">{((avgCompression - 1) * 100).toFixed(0)}%</p>
                    <p className="text-xs text-muted-foreground">Reduction Rate</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Packet Analysis</CardTitle>
                <CardDescription>Transmission statistics</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={packetData}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="timestamp" />
                    <YAxis />
                    <Tooltip formatter={(value: number) => `${value.toLocaleString()} packets`} />
                    <Legend />
                    <Bar dataKey="Sent Packets" fill="#0ea5e9" />
                    <Bar dataKey="Received Packets" fill="#10b981" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
import { useEffect, useState } from 'react'
import { Calendar, CheckCircle, Clock, XCircle, TrendingDown, BarChart3, Users, Brain } from 'lucide-react'
import { StatCard } from '@/components/cards/StatCard'
import { StatusBadge } from '@/components/cards/StatusBadge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useExperimentStore } from '@/stores/experimentStore'

interface ExperimentHistory {
  id: string
  name: string
  experiment_type: string
  status: string
  created_at: string
  started_at?: string
  completed_at?: string
  final_val_loss?: number
  final_val_acc?: number
  duration?: number
  rounds?: number
  gateway_nodes?: number
}

// Generate mock experiment history
const generateExperimentHistory = (): ExperimentHistory[] => {
  return [
    {
      id: 'exp-001',
      name: 'ResNet18 FL Training',
      experiment_type: 'federated',
      status: 'completed',
      created_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      started_at: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000 + 3600000).toISOString(),
      completed_at: new Date(Date.now() - 6 * 24 * 60 * 60 * 1000).toISOString(),
      final_val_loss: 0.152,
      final_val_acc: 0.945,
      duration: 82800, // 23 hours
      rounds: 25,
      gateway_nodes: 5,
    },
    {
      id: 'exp-002',
      name: 'EfficientNet Hyperparameter Search',
      experiment_type: 'hyperparameter_search',
      status: 'completed',
      created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      started_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000 + 7200000).toISOString(),
      completed_at: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(),
      final_val_loss: 0.118,
      final_val_acc: 0.962,
      duration: 75600, // 21 hours
      rounds: 20,
      gateway_nodes: 3,
    },
    {
      id: 'exp-003',
      name: 'MobileNetEdge Deployment',
      experiment_type: 'production',
      status: 'failed',
      created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      started_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000 + 3600000).toISOString(),
      completed_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000 + 5400000).toISOString(),
      final_val_loss: 0.251,
      final_val_acc: 0.891,
      duration: 36000, // 10 hours
      rounds: 15,
      gateway_nodes: 2,
    },
    {
      id: 'exp-004',
      name: 'Custom CNN Ablation Study',
      experiment_type: 'ablation',
      status: 'completed',
      created_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      started_at: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000 + 10800000).toISOString(),
      completed_at: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
      final_val_loss: 0.189,
      final_val_acc: 0.921,
      duration: 32400, // 9 hours
      rounds: 18,
      gateway_nodes: 4,
    },
    {
      id: 'exp-005',
      name: 'Cross-City FLAN Training',
      experiment_type: 'federated',
      status: 'running',
      created_at: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
      started_at: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
      final_val_loss: 0.21,
      final_val_acc: 0.91,
      duration: 21600,
      rounds: 12,
      gateway_nodes: 8,
    },
    {
      id: 'exp-006',
      name: 'Legacy Model Retrain',
      experiment_type: 'centralized',
      status: 'completed',
      created_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
      started_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000 + 5400000).toISOString(),
      completed_at: new Date(Date.now() - 29 * 24 * 60 * 60 * 1000).toISOString(),
      final_val_loss: 0.198,
      final_val_acc: 0.915,
      duration: 46800, // 13 hours
      rounds: 10,
      gateway_nodes: 1,
    },
  ]
}

const formatDuration = (seconds: number | undefined) => {
  if (!seconds) return '-'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)

  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

const formatDate = (date: string) => new Date(date).toLocaleDateString()

export function PerformancePage() {
  const { experiments, fetchExperiments } = useExperimentStore()
  const [history, setHistory] = useState<ExperimentHistory[]>([])
  const [searchTerm, setSearchTerm] = useState('')
  const [typeFilter, setTypeFilter] = useState<'all' | 'federated' | 'centralized' | 'hyperparameter_search' | 'production' | 'ablation'>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'running' | 'failed' | 'pending'>('all')
  const [dateRange, setDateRange] = useState<'7d' | '30d' | '90d'>('7d')

  useEffect(() => {
    fetchExperiments()
    setHistory(generateExperimentHistory())
  }, [fetchExperiments])

  const filteredHistory = history.filter(exp => {
    const matchesSearch = exp.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          exp.id.toLowerCase().includes(searchTerm.toLowerCase())
    const matchesType = typeFilter === 'all' || exp.experiment_type === typeFilter
    const matchesStatus = statusFilter === 'all' || exp.status === statusFilter
    return matchesSearch && matchesType && matchesStatus
  })

  const completedCount = history.filter(e => e.status === 'completed').length
  const failedCount = history.filter(e => e.status === 'failed').length
  const runningCount = history.filter(e => e.status === 'running').length

  const avgAccuracy = history.reduce((sum, e) => sum + (e.final_val_acc || 0), 0) / history.length
  const avgLoss = history.reduce((sum, e) => sum + (e.final_val_loss || 0), 0) / history.length

  // Calculate success rate
  const successRate = history.length > 0
    ? (completedCount / history.length) * 100
    : 0

  // Best performing experiment
  const bestExp = history.reduce((prev, curr) =>
    (!prev || (curr.final_val_acc || 0) < (prev.final_val_acc || 0)) ? curr : prev
  , undefined as ExperimentHistory | undefined)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Performance History
          </h2>
          <p className="text-muted-foreground">
            Track experiment outcomes and historical performance
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {completedCount} Completed • {runningCount} Running • {failedCount} Failed
          </Badge>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Success Rate"
          value={`${successRate.toFixed(1)}%`}
          description="Completed experiments"
          icon={<CheckCircle className="h-4 w-4" />}
          gradient
        />
        <StatCard
          title="Avg. Accuracy"
          value={`${avgAccuracy.toFixed(2)}%`}
          description="Across all experiments"
          icon={<Brain className="h-4 w-4" />}
        />
        <StatCard
          title="Avg. Loss"
          value={avgLoss.toFixed(4)}
          description="Validation loss"
          icon={<TrendingDown className="h-4 w-4" />}
        />
        <StatCard
          title="Total Experiments"
          value={history.length}
          description="In history"
          icon={<Calendar className="h-4 w-4" />}
        />
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Input
            type="search"
            placeholder="Search experiments..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="h-9 w-[250px]"
          />
          <Select value={typeFilter} onValueChange={setTypeFilter as any}>
            <SelectTrigger className="h-9 w-[150px]">
              <SelectValue placeholder="Filter by type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="federated">Federated</SelectItem>
              <SelectItem value="centralized">Centralized</SelectItem>
              <SelectItem value="hyperparameter_search">HP Search</SelectItem>
              <SelectItem value="production">Production</SelectItem>
              <SelectItem value="ablation">Ablation</SelectItem>
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter as any}>
            <SelectTrigger className="h-9 w-[150px]">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="running">Running</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
            </SelectContent>
          </Select>
          <Select value={dateRange} onValueChange={setDateRange as any}>
            <SelectTrigger className="h-9 w-[120px]">
              <SelectValue placeholder="Date range" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7d">Last 7 days</SelectItem>
              <SelectItem value="30d">Last 30 days</SelectItem>
              <SelectItem value="90d">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Performance Summary Cards */}
      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Best Performance</CardTitle>
            <CardDescription>Top performing experiment</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground mb-1">Experiment</p>
              <p className="font-medium text-foreground">{bestExp?.name || '-'}</p>
            </div>
            <div className="flex items-center gap-4">
              <div>
                <p className="text-sm text-muted-foreground mb-1">Accuracy</p>
                <p className="text-xl font-bold text-success-600">
                  {bestExp && bestExp.final_val_acc != null ? `${(bestExp.final_val_acc * 100).toFixed(2)}%` : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground mb-1">Loss</p>
                <p className="text-xl font-bold text-foreground">
                  {bestExp?.final_val_loss?.toFixed(4) ?? '-'}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Failures</CardTitle>
            <CardDescription>Experiments that failed</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {history.filter(e => e.status === 'failed').slice(0, 3).map(exp => (
                <div key={exp.id} className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-foreground text-sm">{exp.name}</p>
                    <p className="text-xs text-muted-foreground">
                      Failed after {formatDuration(exp.duration)}
                    </p>
                  </div>
                  <StatusBadge status="failed" />
                </div>
              ))}
              {history.filter(e => e.status === 'failed').length === 0 && (
                <p className="text-center text-muted-foreground py-4">No failed experiments</p>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Resource Efficiency</CardTitle>
            <CardDescription>Data usage metrics</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Avg. Rounds/Experiment</span>
              <span className="font-medium">
                {(history.reduce((sum, e) => sum + (e.rounds || 0), 0) / history.length).toFixed(1)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Avg. Nodes Used</span>
              <span className="font-medium">
                {(history.reduce((sum, e) => sum + (e.gateway_nodes || 0), 0) / history.length).toFixed(1)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Avg. Duration</span>
              <span className="font-medium">
                {formatDuration(history.reduce((sum, e) => sum + (e.duration || 0), 0) / history.length)}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Experiments Table */}
      <Card>
        <CardHeader>
          <CardTitle>Experiment History</CardTitle>
          <CardDescription>{filteredHistory.length} experiments</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Accuracy</TableHead>
                <TableHead>Loss</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Created</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredHistory.map((exp) => (
                <TableRow key={exp.id}>
                  <TD>
                    <div className="font-medium">{exp.name}</div>
                    <div className="text-xs text-muted-foreground">{exp.id}</div>
                  </TD>
                  <TD>
                    <Badge variant="outline" className="text-xs">
                      {exp.experiment_type.replace('_', ' ')}
                    </Badge>
                  </TD>
                  <TD>
                    <StatusBadge status={exp.status} />
                  </TD>
                  <TD>
                    {exp.final_val_acc ? `${(exp.final_val_acc * 100).toFixed(2)}%` : '-'}
                  </TD>
                  <TD>
                    {exp.final_val_loss != null ? exp.final_val_loss.toFixed(4) : '-'}
                  </TD>
                  <TD>{formatDuration(exp.duration)}</TD>
                  <TD>{formatDate(exp.created_at)}</TD>
                  <TD>
                    <Button variant="ghost" size="sm">
                      View
                    </Button>
                  </TD>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
        <CardFooter>
          <Button variant="outline" className="w-full">
            View All History
          </Button>
        </CardFooter>
      </Card>
    </div>
  )
}

const TD = ({ children }: { children: React.ReactNode }) => (
  <td className="font-medium">{children}</td>
)
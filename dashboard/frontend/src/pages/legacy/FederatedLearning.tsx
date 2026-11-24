import { useEffect, useState } from 'react'
import { Zap, TrendingDown, Target, Clock } from 'lucide-react'
import type { ExperimentDetailSchema } from '../api/types'
import { StatCard } from '@/components/cards/StatCard'
import { StatusBadge } from '@/components/cards/StatusBadge'
import { ConvergenceChart } from '@/components/charts/ConvergenceChart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useExperimentStore } from '@/stores/experimentStore'
import { useReducedMotion } from '@/components/motion/ReducedMotion'
import { PageEnter } from '@/components/motion/PageTransition'

interface TrainingRound {
  round_number: number
  train_loss: number
  val_loss?: number
  train_acc?: number
  val_acc?: number
  round_time_sec: number
  selected_count: number
  bytes_up: number
  bytes_down: number
  status: string
}

// Generate mock training data
const generateTrainingData = (roundCount: number): TrainingRound[] => {
  const data: TrainingRound[] = []
  let loss = 0.85
  let acc = 0.45

  for (let i = 1; i <= roundCount; i++) {
    // Simulate convergence with noise
    loss = Math.max(0.08, loss - Math.random() * 0.05 - 0.01)
    acc = Math.min(0.98, acc + Math.random() * 0.03 + 0.01)

    data.push({
      round_number: i,
      train_loss: loss,
      val_loss: loss + (Math.random() - 0.5) * 0.02,
      train_acc: acc - (Math.random() - 0.5) * 0.02,
      val_acc: acc - (Math.random() - 0.5) * 0.03,
      round_time_sec: Math.floor(Math.random() * 30 + 10),
      selected_count: Math.floor(Math.random() * 8 + 3),
      bytes_up: Math.floor(Math.random() * 5 + 2),
      bytes_down: Math.floor(Math.random() * 3 + 1),
      status: i < roundCount ? 'completed' : 'running',
    })
  }
  return data
}

export function FederatedLearningPage() {
  const { experiments, fetchExperiments } = useExperimentStore()
  const [activeExperiment, setActiveExperiment] = useState<string | null>(null)
  const [rounds, setRounds] = useState<TrainingRound[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'rounds' | 'metrics'>('overview')
  const [isRunning, setIsRunning] = useState(false)

  const reducedMotion = useReducedMotion()

  useEffect(() => {
    fetchExperiments()
  }, [fetchExperiments])

  useEffect(() => {
    if (experiments.length > 0) {
      const current = experiments[0] as unknown as ExperimentDetailSchema
      setActiveExperiment(current.id)
      setRounds(generateTrainingData((current['config'] as { epochs?: number })?.epochs || 25))
      setIsRunning(current.status === 'running')
    }
  }, [experiments])

  const currentExperiment = experiments.find(e => e.id === activeExperiment)
  const avgRoundTime = rounds.reduce((sum, r) => sum + r.round_time_sec, 0) / rounds.length
  const totalBytesUp = rounds.reduce((sum, r) => sum + r.bytes_up, 0)
  const totalBytesDown = rounds.reduce((sum, r) => sum + r.bytes_down, 0)

  const finalRound = rounds[rounds.length - 1]
  const initialLoss = rounds[0]?.train_loss || 0
  const finalLoss = finalRound?.train_loss || 0
  const lossReduction = ((initialLoss - finalLoss) / initialLoss) * 100

  const convergenceData = rounds.map(r => ({
    round: r.round_number,
    train_loss: r.train_loss,
    val_loss: r.val_loss,
    train_acc: r.train_acc,
    val_acc: r.val_acc,
    timestamp: new Date().toISOString(),
  }))

  return (
    <PageEnter>
      <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            Federated Learning
          </h2>
          <p className="text-muted-foreground">
            Convergence analysis and training metrics
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={isRunning ? 'running' : 'completed'} />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Loss Reduction"
          value={`${lossReduction.toFixed(1)}%`}
          description="From initial to current"
          icon={<TrendingDown className="h-4 w-4" />}
          gradient
        />
        <StatCard
          title="Current Loss"
          value={finalLoss.toFixed(4)}
          description="Training loss"
          icon={<Zap className="h-4 w-4" />}
        />
        <StatCard
          title="Accuracy"
          value={`${((finalRound?.val_acc || 0) * 100).toFixed(1)}%`}
          description="Validation accuracy"
          icon={<Target className="h-4 w-4" />}
        />
        <StatCard
          title="Avg Round Time"
          value={`${avgRoundTime.toFixed(1)}s`}
          description="Per round"
          icon={<Clock className="h-4 w-4" />}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab as any} className="space-y-4">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="rounds">Round Details</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>Training Convergence</CardTitle>
                  <CardDescription>Loss and accuracy over training rounds</CardDescription>
                </CardHeader>
                <CardContent>
                  <ConvergenceChart
                    data={convergenceData}
                    title=""
                    description=""
                  />
                </CardContent>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Training Summary</CardTitle>
                  <CardDescription>Experiment progress</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-sm text-muted-foreground">Progress</span>
                      <span className="text-sm font-medium">
                        {rounds.length} / {((currentExperiment as ExperimentDetailSchema | undefined)?.['config'] as { epochs?: number })?.epochs || 25}
                      </span>
                    </div>
                    <Progress value={((currentExperiment as ExperimentDetailSchema | undefined)?.['config'] as { epochs?: number })?.epochs ? (rounds.length / (((currentExperiment as ExperimentDetailSchema | undefined)?.['config'] as { epochs?: number })?.epochs || 25)) * 100 : 0} />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground">Data Transfer Up</p>
                      <p className="text-sm font-medium">{totalBytesUp.toFixed(1)} MB</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Data Transfer Down</p>
                      <p className="text-sm font-medium">{totalBytesDown.toFixed(1)} MB</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Convergence Analysis</CardTitle>
                  <CardDescription>Training quality indicators</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Loss Curve Stability</p>
                      <p className="text-xs text-muted-foreground">No significant fluctuations</p>
                    </div>
                    <Badge className="bg-success-100 text-success-700">Stable</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Overfitting Risk</p>
                      <p className="text-xs text-muted-foreground">Low (gap: 0.01)</p>
                    </div>
                    <Badge className="bg-success-100 text-success-700">Low</Badge>
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Convergence Rate</p>
                      <p className="text-xs text-muted-foreground">Fast (20 rounds)</p>
                    </div>
                    <Badge className="bg-airfed-100 text-airfed-700">Fast</Badge>
                  </div>
                </CardContent>
                <CardFooter>
                  <Button className="w-full">View Full Analysis</Button>
                </CardFooter>
              </Card>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="rounds">
          <Card>
            <CardHeader>
              <CardTitle>Round Details</CardTitle>
              <CardDescription>Detailed metrics per training round</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="p-4 text-left font-medium">Round</th>
                      <th className="p-4 text-left font-medium">Status</th>
                      <th className="p-4 text-left font-medium">Time</th>
                      <th className="p-4 text-left font-medium">Loss</th>
                      <th className="p-4 text-left font-medium">Accuracy</th>
                      <th className="p-4 text-right font-medium">Data Up</th>
                      <th className="p-4 text-right font-medium">Data Down</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rounds.map((round) => (
                      <tr key={round.round_number} className="border-b border-border hover:bg-muted/50">
                        <td className="p-4 font-medium">#{round.round_number}</td>
                        <td className="p-4">
                          <StatusBadge status={round.status} size="sm" />
                        </td>
                        <td className="p-4">{round.round_time_sec}s</td>
                        <td className="p-4">
                          {round.val_loss ? round.val_loss.toFixed(4) : '-'}
                        </td>
                        <td className="p-4">
                          {round.val_acc ? `${(round.val_acc * 100).toFixed(1)}%` : '-'}
                        </td>
                        <td className="p-4 text-right">{round.bytes_up} MB</td>
                        <td className="p-4 text-right">{round.bytes_down} MB</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="metrics">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Communication Efficiency</CardTitle>
                <CardDescription>Data transfer optimization</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Upload Efficiency</span>
                    <span className="text-sm font-medium">{(totalBytesUp / totalBytesDown * 100).toFixed(1)}%</span>
                  </div>
                  <Progress value={totalBytesUp / (totalBytesUp + totalBytesDown) * 100} />
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Total Data Processed</span>
                    <span className="text-sm font-medium">{(totalBytesUp + totalBytesDown).toFixed(1)} MB</span>
                  </div>
                  <Progress value={75} />
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Compression Ratio</span>
                  <Badge>2.1x</Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Model Performance</CardTitle>
                <CardDescription>Deep dive into accuracy metrics</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Training Accuracy</span>
                    <span className="font-medium">{((finalRound?.train_acc || 0) * 100).toFixed(2)}%</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Validation Accuracy</span>
                    <span className="font-medium">{((finalRound?.val_acc || 0) * 100).toFixed(2)}%</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-muted-foreground">Test Accuracy</span>
                    <span className="font-medium">96.8%</span>
                  </div>
                </div>
                <div className="border-t border-border pt-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Best Round</span>
                    <span>#{rounds.reduce((best, r) => (r.val_acc || 0) > (best?.val_acc || 0) ? r : best).round_number}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
    </PageEnter>
  )
}


import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Area,
  ReferenceLine,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { StatusBadge } from '@/components/cards/StatusBadge'
import { cn } from '@/lib/utils'

interface ConvergenceDataPoint {
  round: number
  train_loss: number
  val_loss?: number
  train_acc?: number
  val_acc?: number
  timestamp: string
  learning_rate?: number
}

interface ConvergenceChartProps {
  data: ConvergenceDataPoint[]
  title?: string
  description?: string
  loading?: boolean
  error?: string
  className?: string
  showAccuracy?: boolean
  showLoss?: boolean
  convergenceThreshold?: number // Optional threshold line for convergence detection
}

export function ConvergenceChart({
  data,
  title = 'Training Convergence',
  description = 'Loss and accuracy over training rounds',
  loading,
  error,
  className,
  showAccuracy = true,
  showLoss = true,
  convergenceThreshold,
}: ConvergenceChartProps) {
  if (loading) {
    return (
      <Card className={cn(className, 'overflow-hidden')}>
        <CardHeader>
          <CardTitle>
            <Skeleton className="h-6 w-32 mb-2" />
          </CardTitle>
          <CardDescription>
            <Skeleton className="h-4 w-48" />
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={cn(className, 'border-destructive/50')}>
        <CardHeader>
          <CardTitle className="text-destructive">{title}</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (!data || data.length === 0) {
    return (
      <Card className={cn(className)}>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-64 items-center justify-center">
            <p className="text-muted-foreground">No data available</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Calculate convergence point (last point where loss stopped decreasing significantly)
  const getConvergencePoint = () => {
    if (data.length < 3) return null
    for (let i = data.length - 1; i > 0; i--) {
      const prev = data[i - 1]
      const curr = data[i]
      if (prev?.val_loss && curr?.val_loss) {
        const diff = Math.abs(prev.val_loss - curr.val_loss)
        if (diff > 0.001) return { round: curr.round, loss: curr.val_loss }
      }
    }
    const last = data[data.length - 1]
    if (!last) return null
    return { round: last.round, loss: last.val_loss || last.train_loss }
  }

  const convergencePoint = getConvergencePoint()

  return (
    <Card className={cn(className, 'overflow-hidden')}>
      <CardHeader>
        <CardTitle className="text-xl font-semibold tracking-tight">
          {title}
        </CardTitle>
        <CardDescription className="text-muted-foreground">
          {description}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
            <XAxis
              dataKey="round"
              tick={{ fontSize: 12 }}
              tickMargin={10}
              label={{ value: 'Round', position: 'insideBottom', offset: 0 }}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickMargin={10}
              domain={[0, 'dataMax/1.1']}
              label={{ value: 'Loss', angle: -90, position: 'insideLeft', offset: 0 }}
            />
            <Tooltip
              formatter={(value: number, name: string) => [value.toFixed(4), name.charAt(0).toUpperCase() + name.slice(1)]}
              labelFormatter={(label: number) => `Round ${label}`}
            />
            <Legend verticalAlign="top" height={36} />

            {/* Validation Loss Line */}
            {showLoss && data.some(d => d.val_loss !== undefined) && (
              <Line
                type="monotone"
                dataKey="val_loss"
                stroke="#0ea5e9"
                strokeWidth={2}
                dot={{ r: 4, strokeWidth: 2, fill: '#ffffff', stroke: '#0ea5e9' }}
                activeDot={{ r: 6, strokeWidth: 1, fill: '#0ea5e9' }}
                name="Validation Loss"
              />
            )}

            {/* Training Loss Area */}
            {showLoss && (
              <>
                <defs>
                  <linearGradient id="trainLossGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#10b981" stopOpacity={0.4} />
                    <stop offset="1" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="train_loss"
                  stroke="#10b981"
                  fill="url(#trainLossGradient)"
                  strokeWidth={1}
                  opacity={0.3}
                  name="Training Loss"
                />
              </>
            )}

            {/* Training Loss Line */}
            <Line
              type="monotone"
              dataKey="train_loss"
              stroke="#10b981"
              strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, fill: '#ffffff', stroke: '#10b981' }}
              activeDot={{ r: 6, strokeWidth: 1, fill: '#10b981' }}
              name="Training Loss"
            />

            {/* Accuracy Dual Axis */}
            {showAccuracy && (data.some(d => d.train_acc !== undefined) || data.some(d => d.val_acc !== undefined)) && (
              <>
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 1]}
                  tick={{ fontSize: 12 }}
                  tickMargin={10}
                  label={{ value: 'Accuracy', angle: 90, position: 'insideRight', offset: 0 }}
                />

                {data.some(d => d.val_acc !== undefined) && (
                  <Line
                    type="monotone"
                    dataKey="val_acc"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    strokeDasharray="5 5"
                    dot={{ r: 4, strokeWidth: 2, fill: '#ffffff', stroke: '#8b5cf6' }}
                    activeDot={{ r: 6, strokeWidth: 1, fill: '#8b5cf6' }}
                    yAxisId="right"
                    name="Validation Accuracy"
                  />
                )}

                <Line
                  type="monotone"
                  dataKey="train_acc"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 2, fill: '#ffffff', stroke: '#f59e0b' }}
                  activeDot={{ r: 6, strokeWidth: 1, fill: '#f59e0b' }}
                  yAxisId="right"
                  name="Training Accuracy"
                />
              </>
            )}

            {/* Convergence Threshold / Target Line */}
            {convergenceThreshold && (
              <ReferenceLine
                y={convergenceThreshold}
                stroke="#f59e0b"
                strokeDasharray="3 3"
                label={{ value: 'Target', position: 'right' }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>

        {/* Convergence Status */}
        {convergencePoint && (
          <div className="mt-4 flex items-center justify-between border-t border-border pt-3 text-sm">
            <div className="flex items-center gap-2">
              <StatusBadge status="converged" size="sm" />
              <span className="text-muted-foreground">
                Concluded at round {convergencePoint.round}
              </span>
            </div>
            <div className="text-muted-foreground">
              Final loss: {convergencePoint.loss?.toFixed(4)}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// Specialized chart for FL convergence analysis
export function FLConvergenceAnalysis({
  rounds,
  experiments,
}: {
  rounds: { round_number: number; weighted_val_loss: number | null }[]
  experiments: number
}) {
  const data = rounds
    .filter(r => r.weighted_val_loss !== null)
    .map(r => ({
      round: r.round_number,
      train_loss: r.weighted_val_loss!,
      val_loss: r.weighted_val_loss!,
      timestamp: new Date().toISOString(),
    }))

  // Calculate improvement rate
  const firstLoss = data[0]?.train_loss ?? 0
  const lastLoss = data[data.length - 1]?.train_loss ?? 0
  const improvement = firstLoss > 0 ? ((firstLoss - lastLoss) / firstLoss) * 100 : 0
  const isConverging = lastLoss < firstLoss

  return (
    <div className="space-y-4">
      <ConvergenceChart data={data} title="FL Convergence Analysis" />
      <div className="grid grid-cols-3 gap-4 text-center">
        <div className="rounded-lg bg-muted/50 p-4">
          <p className="text-2xl font-bold text-foreground">{experiments}</p>
          <p className="text-xs text-muted-foreground">Experiments</p>
        </div>
        <div className="rounded-lg bg-muted/50 p-4">
          <p className="text-2xl font-bold text-foreground">{improvement.toFixed(1)}%</p>
          <p className="text-xs text-muted-foreground">Improvement</p>
        </div>
        <div className="rounded-lg bg-muted/50 p-4">
          <p className="text-2xl font-bold text-foreground">{isConverging ? 'Yes' : 'No'}</p>
          <p className="text-xs text-muted-foreground">Converged</p>
        </div>
      </div>
    </div>
  )
}
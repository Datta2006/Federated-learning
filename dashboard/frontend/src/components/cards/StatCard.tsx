import { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface StatCardProps {
  title: string
  value: string | number
  description?: string
  icon?: ReactNode
  trend?: number
  trendLabel?: string
  className?: string
  loading?: boolean
  error?: string
  gradient?: boolean
  gaugeValue?: number // 0-100 for gauge visualization
}

export function StatCard({
  title,
  value,
  description,
  icon,
  trend,
  trendLabel,
  className,
  loading,
  error,
  gradient,
  gaugeValue,
}: StatCardProps) {
  const formatValue = (val: string | number) => {
    if (typeof val === 'number') {
      if (val >= 1e9) return `${(val / 1e9).toFixed(2)}B`
      if (val >= 1e6) return `${(val / 1e6).toFixed(2)}M`
      if (val >= 1e3) return `${(val / 1e3).toFixed(1)}K`
      return val.toString()
    }
    return val
  }

  const trendColor = trend && trend > 0 ? 'text-success-500' : trend && trend < 0 ? 'text-destructive-500' : 'text-muted-foreground'

  if (loading) {
    return (
      <Card className={cn(className, 'overflow-hidden')}>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">
            <Skeleton className="h-4 w-24" />
          </CardTitle>
          {icon && <div className="h-4 w-4 opacity-50">{icon}</div>}
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-16" />
          {description && <Skeleton className="mt-1 h-3 w-20" />}
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className={cn(className, 'border-destructive/50')}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-destructive">{title}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-destructive">{error}</div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className={cn(gradient && 'bg-gradient-to-r from-airfed-50/50 to-energy-50/50', className)}>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        {icon && (
          <div className="h-4 w-4 text-muted-foreground/70">
            {icon}
          </div>
        )}
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline gap-2">
          <div className="text-2xl font-bold text-foreground">
            {formatValue(value)}
          </div>
          {trend !== undefined && (
            <div className="text-xs">
              <span className={trendColor}>
                {trend > 0 ? '+' : ''}{trend}%
              </span>
              {trendLabel && (
                <span className="text-muted-foreground"> {trendLabel}</span>
              )}
            </div>
          )}
        </div>
        {description && (
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        )}
        {gaugeValue !== undefined && (
          <Gauge value={gaugeValue} className="mt-3" />
        )}
      </CardContent>
    </Card>
  )
}

interface GaugeProps {
  value: number
  className?: string
}

function Gauge({ value, className }: GaugeProps) {
  const radius = 20
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (value / 100) * circumference

  const getColor = (v: number) => {
    if (v < 40) return '#10b981' // success
    if (v < 70) return '#f59e0b' // warning
    return '#ef4444' // danger
  }

  return (
    <div className={cn('w-full h-2 bg-muted rounded-full overflow-hidden', className)}>
      <svg
        viewBox="0 0 100 100"
        className="w-full h-full transform rotate-[-90deg]"
      >
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth="5"
        />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke={getColor(value)}
          strokeWidth="5"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <span className="text-xs font-bold text-muted-foreground">
          {value}%
        </span>
      </div>
    </div>
  )
}
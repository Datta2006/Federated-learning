import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { format, parseISO } from 'date-fns'

interface ActivityDataPoint {
  time: string
  timestamp?: string
  [key: string]: number | string | undefined
}

interface ActivityChartProps {
  data: ActivityDataPoint[]
  title?: string
  description?: string
  loading?: boolean
  error?: string
  className?: string
  valueKey?: string
  areaColor?: string
}

export function ActivityChart({
  data,
  title = 'Activity Over Time',
  description = 'Recent activity metrics',
  loading,
  error,
  className,
  valueKey = 'value',
  areaColor = '#0ea5e9',
}: ActivityChartProps) {
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
          <AreaChart data={data} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 12 }}
              tickMargin={10}
              label={{ value: 'Time', position: 'insideBottom', offset: 0 }}
              tickFormatter={(value) => {
                const date = parseISO(value)
                return format(date, 'HH:mm')
              }}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickMargin={10}
              domain={[0, 'dataMax/1.1']}
            />
            <Tooltip
              formatter={(value: number, name: string) => [value.toFixed(2), name]}
              labelFormatter={(label: string) => `Time: ${label}`}
            />
            <Legend verticalAlign="top" height={36} />
            <Area
              type="monotone"
              dataKey={valueKey}
              stroke={areaColor}
              fill={`url(#${valueKey}Gradient)`}
              strokeWidth={2}
              opacity={0.6}
            >
              <defs>
                <linearGradient id={`${valueKey}Gradient`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor={areaColor} stopOpacity={0.6} />
                  <stop offset="1" stopColor={areaColor} stopOpacity={0} />
                </linearGradient>
              </defs>
            </Area>
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
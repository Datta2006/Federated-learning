import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { AlertCircle, CheckCircle, Clock, Pause, Play, RefreshCw, XCircle } from 'lucide-react'

interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md' | 'lg'
  showIcon?: boolean
  className?: string
}

const statusConfig: Record<string, {
  colors: string
  icon: React.ComponentType<{ className?: string }>
  label: string
  bgPattern?: string
}> = {
  online: {
    colors: 'border-success-500/50 text-success-500',
    icon: CheckCircle,
    label: 'Online',
  },
  offline: {
    colors: 'border-gray-500/50 text-gray-500',
    icon: XCircle,
    label: 'Offline',
  },
  pending: {
    colors: 'border-amber-500/50 text-amber-500',
    icon: Clock,
    label: 'Pending',
  },
  running: {
    colors: 'border-airfed-500/50 text-airfed-500',
    icon: RefreshCw,
    label: 'Running',
  },
  completed: {
    colors: 'border-success-500/50 text-success-500',
    icon: CheckCircle,
    label: 'Completed',
  },
  failed: {
    colors: 'border-destructive-500/50 text-destructive-500',
    icon: XCircle,
    label: 'Failed',
  },
  stopped: {
    colors: 'border-gray-500/50 text-gray-500',
    icon: Pause,
    label: 'Stopped',
  },
  warning: {
    colors: 'border-amber-500/50 text-amber-500',
    icon: AlertCircle,
    label: 'Warning',
  },
  critical: {
    colors: 'border-destructive-500/50 text-destructive-500',
    icon: AlertCircle,
    label: 'Critical',
  },
  idle: {
    colors: 'border-gray-500/50 text-gray-500',
    icon: Clock,
    label: 'Idle',
  },
  active: {
    colors: 'border-airfed-500/50 text-airfed-500',
    icon: Play,
    label: 'Active',
  },
  converged: {
    colors: 'border-success-500/50 text-success-500',
    icon: CheckCircle,
    label: 'Converged',
  },
  diverging: {
    colors: 'border-destructive-500/50 text-destructive-500',
    icon: AlertCircle,
    label: 'Diverging',
  },
  unstable: {
    colors: 'border-amber-500/50 text-amber-500',
    icon: AlertCircle,
    label: 'Unstable',
  },
  degraded: {
    colors: 'border-amber-500/50 text-amber-500',
    icon: AlertCircle,
    label: 'Degraded',
  },
  saturated: {
    colors: 'border-energy-500/50 text-energy-500',
    icon: RefreshCw,
    label: 'Saturated',
  },
  accepted: {
    colors: 'border-success-500/50 text-success-500',
    icon: CheckCircle,
    label: 'Accepted',
  },
  rejected: {
    colors: 'border-destructive-500/50 text-destructive-500',
    icon: XCircle,
    label: 'Rejected',
  },
}

export function StatusBadge({
  status,
  size = 'md',
  showIcon = true,
  className,
}: StatusBadgeProps) {
  const config = statusConfig[status.toLowerCase()] || {
    colors: 'border-gray-500/50 text-gray-500',
    icon: Clock,
    label: status,
  }

  const Icon = config.icon

  const sizeClasses = {
    sm: 'h-5 px-2 text-xs',
    md: 'h-6 px-2.5 text-sm',
    lg: 'h-7 px-3 text-base',
  }

  return (
    <Badge
      variant="outline"
      className={cn(
        'whitespace-nowrap transition-all duration-200',
        sizeClasses[size],
        config.colors,
        className,
      )}
    >
      {showIcon && <Icon className={cn('mr-1.5', size === 'sm' ? 'h-3 w-3' : 'h-4 w-4')} />}
      {config.label}
    </Badge>
  )
}

// Preset status badges for common use cases
export const Badges = {
  Online: ({ className }: { className?: string }) => (
    <StatusBadge status="online" className={className} />
  ),
  Offline: ({ className }: { className?: string }) => (
    <StatusBadge status="offline" className={className} />
  ),
  Running: ({ className }: { className?: string }) => (
    <StatusBadge status="running" className={className} />
  ),
  Completed: ({ className }: { className?: string }) => (
    <StatusBadge status="completed" className={className} />
  ),
  Failed: ({ className }: { className?: string }) => (
    <StatusBadge status="failed" className={className} />
  ),
  Pending: ({ className }: { className?: string }) => (
    <StatusBadge status="pending" className={className} />
  ),
  Warning: ({ className }: { className?: string }) => (
    <StatusBadge status="warning" className={className} />
  ),
  Critical: ({ className }: { className?: string }) => (
    <StatusBadge status="critical" className={className} />
  ),
  Converged: ({ className }: { className?: string }) => (
    <StatusBadge status="converged" className={className} />
  ),
  Diverging: ({ className }: { className?: string }) => (
    <StatusBadge status="diverging" className={className} />
  ),
}
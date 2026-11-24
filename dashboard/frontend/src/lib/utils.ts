import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date, format: 'short' | 'long' | 'relative' = 'short'): string {
  const d = typeof date === 'string' ? new Date(date) : date

  if (format === 'relative') {
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHours = Math.floor(diffMin / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffSec < 60) return 'just now'
    if (diffMin < 60) return `${diffMin}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return d.toLocaleDateString()
  }

  const options: Intl.DateTimeFormatOptions = format === 'long'
    ? { year: 'numeric', month: 'long', day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric' }
    : { year: '2-digit', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }

  return d.toLocaleString(undefined, options)
}

export function formatNumber(value: number, decimals = 2, locale = 'en-US'): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`
}

export function formatPercentage(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`
}

export function getStatusColor(status: string): string {
  const statusLower = status.toLowerCase()
  const colors: Record<string, string> = {
    online: 'text-success-500',
    offline: 'text-gray-500',
    pending: 'text-amber-500',
    running: 'text-airfed-500',
    completed: 'text-success-500',
    failed: 'text-destructive-500',
    warning: 'text-amber-500',
    critical: 'text-destructive-500',
    idle: 'text-gray-500',
    active: 'text-airfed-500',
    saturated: 'text-ener gy-500',
  }
  return colors[statusLower] || 'text-gray-500'
}

export function getStatusBackgroundColor(status: string): string {
  const statusLower = status.toLowerCase()
  const colors: Record<string, string> = {
    online: 'bg-success-100 dark:bg-success-900',
    offline: 'bg-gray-100 dark:bg-gray-900',
    pending: 'bg-amber-100 dark:bg-amber-900',
    running: 'bg-airfed-100 dark:bg-airfed-900',
    completed: 'bg-success-100 dark:bg-success-900',
    failed: 'bg-destructive-100 dark:bg-destructive-900',
    warning: 'bg-amber-100 dark:bg-amber-900',
    critical: 'bg-destructive-100 dark:bg-destructive-900',
    idle: 'bg-gray-100 dark:bg-gray-900',
    active: 'bg-airfed-100 dark:bg-airfed-900',
    saturated: 'bg-energy-100 dark:bg-energy-900',
  }
  return colors[statusLower] || 'bg-gray-100 dark:bg-gray-900'
}

export function calculateRoundStats(rounds: { round_time_sec: number; selected_count: number; bytes_up: number; bytes_down: number }[]): {
  avgRoundTime: number
  avgSelected: number
  totalBytesUp: number
  totalBytesDown: number
  avgLatency: number
} {
  if (rounds.length === 0) {
    return {
      avgRoundTime: 0,
      avgSelected: 0,
      totalBytesUp: 0,
      totalBytesDown: 0,
      avgLatency: 0,
    }
  }

  const totalRoundTime = rounds.reduce((sum, r) => sum + r.round_time_sec, 0)
  const totalSelected = rounds.reduce((sum, r) => sum + r.selected_count, 0)
  const totalBytesUp = rounds.reduce((sum, r) => sum + r.bytes_up, 0)
  const totalBytesDown = rounds.reduce((sum, r) => sum + r.bytes_down, 0)

  return {
    avgRoundTime: totalRoundTime / rounds.length,
    avgSelected: totalSelected / rounds.length,
    totalBytesUp,
    totalBytesDown,
    avgLatency: (totalBytesUp + totalBytesDown) / rounds.length,
  }
}

export function generateId(): string {
  return Math.random().toString(36).substring(2) + Date.now().toString(36)
}

export function debounce<T extends (...args: any[]) => any>(func: T, delay: number): T {
  let timeoutId: any
  return ((...args: Parameters<T>) => {
    clearTimeout(timeoutId)
    timeoutId = setTimeout(() => func(...args), delay)
  }) as T
}

export function throttle<T extends (...args: any[]) => any>(func: T, limit: number): T {
  let inThrottle: boolean
  return ((...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args)
      inThrottle = true
      setTimeout(() => (inThrottle = false), limit)
    }
  }) as T
}

export function calculateConvergence(rounds: { weighted_val_loss: number | null }[]): {
  converging: boolean
  rate: number
  finalLoss: number | null
} {
  const validRounds = rounds
    .map(r => r.weighted_val_loss)
    .filter((loss): loss is number => loss !== null)

  if (validRounds.length < 2) {
    return { converging: false, rate: 0, finalLoss: validRounds[validRounds.length - 1] ?? null }
  }

  // Calculate loss reduction rate
  const firstLoss = validRounds[0] ?? 0
  const lastLoss = validRounds[validRounds.length - 1] ?? 0
  const reductionRate = firstLoss > 0 ? ((firstLoss - lastLoss) / firstLoss) * 100 : 0

  // Check if converging (loss decreasing)
  const isConverging = lastLoss < firstLoss

  return {
    converging: isConverging,
    rate: reductionRate,
    finalLoss: lastLoss,
  }
}

export function getRiskLevel(loss: number | null, baseline: number): 'low' | 'medium' | 'high' {
  if (loss === null) return 'high'
  const ratio = loss / baseline
  if (ratio < 0.9) return 'low'
  if (ratio < 1.2) return 'medium'
  return 'high'
}

export function parseJwt(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    const base64Url = parts[1]
    if (!base64Url) return null
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = atob(base64)
    return JSON.parse(jsonPayload)
  } catch {
    return null
  }
}

export function truncateString(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str
  return str.slice(0, maxLength - 3) + '...'
}
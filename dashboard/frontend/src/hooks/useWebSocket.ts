import { useEffect, useRef, useState, useCallback } from 'react'
import type { ExperimentSchema, RoundSchema, WorkerStatus } from '@/api/types'

export interface WebSocketMessage {
  type: string
  data: unknown
  timestamp: string
}

export interface UseWebSocketOptions {
  url: string
  protocols?: string | string[]
  reconnectAttempts?: number
  reconnectInterval?: number
  enabled?: boolean
}

export interface UseWebSocketResult<T = unknown> {
  data: T | null
  isConnected: boolean
  isConnecting: boolean
  error: Error | null
  sendMessage: (message: unknown) => void
  lastMessage: WebSocketMessage | null
}

let globalWsId = 0

export function useWebSocket<T = unknown>(
  options: UseWebSocketOptions,
): UseWebSocketResult<T> {
  const {
    url,
    protocols,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
    enabled = true,
  } = options

  const [data, setData] = useState<T | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const wsIdRef = useRef(`ws_${++globalWsId}`)

  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!enabled) return

    setIsConnecting(true)
    setError(null)

    try {
      const ws = new WebSocket(url, protocols)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        setIsConnecting(false)
        reconnectAttemptsRef.current = 0
        console.debug(`WebSocket connected: ${wsIdRef.current}`)
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage
          setLastMessage(message)
          setData(message.data as T)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }

      ws.onerror = () => {
        console.error(`WebSocket error: ${wsIdRef.current}`)
        setError(new Error('WebSocket error'))
      }

      ws.onclose = (event) => {
        setIsConnected(false)
        setIsConnecting(false)
        console.debug(`WebSocket closed: ${wsIdRef.current}`, event)

        if (reconnectAttemptsRef.current < reconnectAttempts) {
          reconnectAttemptsRef.current += 1
          reconnectTimeoutRef.current = setTimeout(() => {
            connect()
          }, reconnectInterval)
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e : new Error('Failed to create WebSocket'))
      setIsConnecting(false)
    }
  }, [url, protocols, enabled, reconnectAttempts, reconnectInterval])

  useEffect(() => {
    if (enabled) {
      connect()
    }

    return () => {
      cleanup()
    }
  }, [connect, cleanup, enabled])

  const sendMessage = useCallback((message: unknown) => {
    if (wsRef.current && (wsRef.current as any).readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket is not open, cannot send message')
    }
  }, [])

  return {
    data,
    isConnected,
    isConnecting,
    error,
    sendMessage,
    lastMessage,
  }
}

// Specialized hook for experiment updates
export function useExperimentUpdates(experimentId: string) {
  const wsUrl = `${(import.meta.env as Record<string, string>)['VITE_WEBSOCKET_URL'] || 'ws://localhost:8000/ws'}/experiments/${experimentId}`

  return useWebSocket<{
    experiment: ExperimentSchema
    rounds: RoundSchema[]
  }>({
    url: wsUrl,
    reconnectAttempts: 10,
    reconnectInterval: 2000,
  })
}

// Specialized hook for worker status
export function useWorkerStatus() {
  const wsUrl = `${(import.meta.env as Record<string, string>)['VITE_WEBSOCKET_URL'] || 'ws://localhost:8000/ws'}/workers`

  return useWebSocket<{
    workers: WorkerStatus[]
    timestamp: string
  }>({
    url: wsUrl,
    reconnectAttempts: 5,
    reconnectInterval: 5000,
  })
}

// Specialized hook for real-time metrics
export function useMetricsUpdates(experimentId: string) {
  const wsUrl = `${(import.meta.env as Record<string, string>)['VITE_WEBSOCKET_URL'] || 'ws://localhost:8000/ws'}/metrics/${experimentId}`

  return useWebSocket<{
    metrics: Record<string, number>
    timestamp: string
  }>({
    url: wsUrl,
    reconnectAttempts: 3,
    reconnectInterval: 1000,
  })
}

// Hook for managing multiple WebSockets
export function useMultipleWebSockets<T extends Record<string, string>>(
  urls: T,
): { [K in keyof T]: UseWebSocketResult<unknown> } & { reconnectAll: () => void } {
  const results = {} as { [K in keyof T]: UseWebSocketResult<unknown> }

  (Object.entries(urls) as [keyof T, string][]).forEach(([key, url]) => {
    results[key] = useWebSocket<unknown>({
      url,
      reconnectAttempts: 5,
      reconnectInterval: 3000,
    })
  })

  const reconnectAll = useCallback(() => {
    Object.values(results).forEach(result => {
      if (result.data) {
        // Trigger reconnect logic per connection
      }
    })
  }, [results])

  return { ...results, reconnectAll } as { [K in keyof T]: UseWebSocketResult<unknown> } & { reconnectAll: () => void }
}
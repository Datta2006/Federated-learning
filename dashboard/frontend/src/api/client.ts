import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios'

// API base URL
const API_BASE_URL = (import.meta.env as Record<string, string>)['VITE_API_BASE'] || '/api'

// WebSocket URL
export const WS_URL = (import.meta.env as Record<string, string>)['VITE_WEBSOCKET_URL'] || 'ws://localhost:8000/ws'

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for adding auth token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('authToken')
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error: AxiosError) => {
    return Promise.reject(error)
  },
)

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Handle unauthorized - redirect to login or clear token
      localStorage.removeItem('authToken')
      window.location.href = '/login'
    }

    if (error.response?.status === 403) {
      console.error('Access forbidden')
    }

    if (error.code === 'ECONNABORTED') {
      console.error('Request timeout')
    }

    if (!error.response) {
      console.error('Network error - cannot reach server')
    }

    return Promise.reject(error)
  },
)

// Error handling helper
export const handleApiError = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      return error.response.data?.message || error.response.statusText || 'An error occurred'
    }
    if (error.request) {
      return 'Network error - cannot reach server'
    }
  }
  return 'An unexpected error occurred'
}

// HTTP methods
export const httpGet = <T>(url: string, params?: Record<string, unknown>) =>
  apiClient.get<T>(url, { params }).then((res) => res.data)

export const httpPost = <T>(url: string, data?: Record<string, unknown>) =>
  apiClient.post<T>(url, data).then((res) => res.data)

export const httpPut = <T>(url: string, data?: Record<string, unknown>) =>
  apiClient.put<T>(url, data).then((res) => res.data)

export const httpPatch = <T>(url: string, data?: Record<string, unknown>) =>
  apiClient.patch<T>(url, data).then((res) => res.data)

export const httpDelete = <T>(url: string) =>
  apiClient.delete<T>(url).then((res) => res.data)

export default apiClient
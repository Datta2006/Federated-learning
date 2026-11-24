// TypeScript interfaces matching backend Pydantic schemas exactly

// Experiment Types
export type ExperimentType = 'federated' | 'centralized' | 'hyperparameter_search' | 'ablation' | 'production'

// Core Experiment Schema
export interface ExperimentSchema {
  id: string
  name: string
  experiment_type: string
  seed: number
  epochs: number
  batch_size: number
  learning_rate: number
  model_name: string
  model_version: string
  status: string
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

// Extended Experiment Detail Schema
export interface ExperimentDetailSchema extends ExperimentSchema {
  config: Record<string, unknown>
  gateway_config: Record<string, unknown>
  description?: string | null
}

// Round Schema
export interface RoundSchema {
  round_number: number
  status: string
  round_time_sec: number
  selected_count: number
  selected_nodes: string[]
  received_count: number
  dropped_nodes: string[]
  bytes_up: number
  bytes_down: number
  weighted_val_loss?: number | null
  model_version: string
  accepted_count: number
  rejected_count: number
  single_client: boolean
  aggregated: boolean
  timestamp: string
}

// Metrics Schema
export interface MetricsSchema {
  final_val_loss?: number | null
  final_val_acc?: number | null
  final_test_loss?: number | null
  final_test_acc?: number | null
  total_rounds: number
  experiment_duration_sec?: number | null
  total_bytes_up: number
  total_bytes_down: number
}

// Experiment Summary Schema
export interface ExperimentSummarySchema {
  experiment_id: string
  round_count: number
  metrics?: MetricsSchema | null
}

// Create Experiment Request
export interface ExperimentCreateRequest {
  name: string
  experiment_type?: string
  description?: string | null
  seed: number
  epochs: number
  batch_size: number
  learning_rate: number
  model_name: string
  model_version: string
  config?: Record<string, unknown>
  gateway_config?: Record<string, unknown>
}

// Update Experiment Request
export interface ExperimentUpdateRequest {
  name?: string
  description?: string
  status?: string
}

// Round Submission
export interface RoundSubmission {
  experiment_id: string
  round_number: number
  selected_nodes?: string[]
  received_count?: number
  dropped_nodes?: string[]
  bytes_up?: number
  bytes_down?: number
  round_time_sec?: number
  weighted_val_loss?: number | null
  evaluated_version?: string
  model_version?: string
  accepted_nodes?: string[]
  rejected_nodes?: Record<string, string>
  single_client?: boolean
  aggregated?: boolean
  status?: string
}

// Telemetry Record
export interface TelemetryRecord {
  id: number
  experiment_id: string
  topic: string
  node_id: string
  message_type: string
  payload: Record<string, unknown>
  received_at: string
}

// Forecast Record
export interface ForecastRecord {
  id: number
  experiment_id: string
  forecast_type: string
  version: string
  predictions: number[]
  confidence_interval?: [number | null, number | null] | null
  mae?: number | null
  rmse?: number | null
  created_at: string
}

// Alert Record
export interface AlertRecord {
  id: number
  experiment_id: string
  alert_type: string
  severity: string
  message: string
  details?: Record<string, unknown> | null
  created_at: string
  resolved_at?: string | null
  resolved: boolean
}

// Worker Status
export interface WorkerStatus {
  node_id: string
  status: 'online' | 'offline' | 'warning' | 'critical'
  last_seen: string
  ip_address?: string
  version?: string
  gateway?: string
  cpu_usage?: number
  memory_usage?: number
  disk_usage?: number
}

// Network Node
export interface NetworkNode {
  id: string
  name: string
  type: 'gateway' | 'worker'
  status: 'online' | 'offline' | 'warning'
  ip_address?: string
  port?: number
  version?: string
  model?: string
  connected_at?: string
  last_heartbeat?: string
  location?: string
  region?: string
}

// Network Link
export interface NetworkLink {
  source: string
  target: string
  bytes_up: number
  bytes_down: number
  latency_ms: number
  status: 'active' | 'idle' | 'degraded'
}

// Air Quality Measurement
export interface AirQualityMeasurement {
  id: string
  timestamp: string
  station_id: string
  aqi: number
  pm25?: number
  pm10?: number
  no2?: number
  so2?: number
  co?: number
  o3?: number
  temperature?: number
  humidity?: number
  pressure?: number
  accuracy?: number
}

// Air Quality Forecast
export interface AirQualityForecast {
  id: string
  forecast_type: string
  version: string
  predictions: number[]
  confidence_interval?: [number | null, number | null] | null
  mae?: number | null
  rmse?: number | null
  created_at: string
}

// Communication Metrics
export interface CommunicationMetrics {
  experiment_id: string
  round_number: number
  bytes_up: number
  bytes_down: number
  latency_ms: number
  packet_loss: number
  retransmission_rate: number
  timestamp: string
}

// Training Metrics for FL
export interface TrainingMetrics {
  round: number
  train_loss: number
  val_loss?: number
  train_acc?: number
  val_acc?: number
  learning_rate?: number
  timestamp: string
}

// Global Model
export interface GlobalModel {
  model_id: string
  name: string
  version: string
  created_at: string
  framework: string
  parameters?: number
  architecture?: string
  training_experiments?: number
  performance_metrics?: {
    accuracy?: number
    loss?: number
    f1_score?: number
  }
  file_size?: string
  download_url?: string
}

// Experiment with full details
export interface ExperimentWithDetails extends ExperimentDetailSchema {
  rounds: RoundSchema[]
  metrics: MetricsSchema | null
  telemetry_records: TelemetryRecord[]
  forecasts: ForecastRecord[]
  alerts: AlertRecord[]
}

// Pagination Response
export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  limit: number
  has_more: boolean
}
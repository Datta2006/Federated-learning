export type NodeStatus = "online" | "offline" | "stale" | "unknown";
export type NodeRole = "training" | "inference";
export type StageStatus = "complete" | "active" | "pending" | "skipped" | "failed";

export interface NodeView {
  id: string;
  year: number | null;
  role: NodeRole;
  status: NodeStatus;
  reported_state: string | null;
  reason: string | null;
  last_seen: string | null;
  last_health: string | null;
  message_ts: string | null;
  retained: boolean;
  source: "mqtt" | "none";
}

export interface Stage {
  key: string;
  label: string;
  status: StageStatus;
}

export interface RoundView {
  round: number;
  model_version: string | null;
  selected: string[];
  received: number;
  upload_nodes: string[];
  acks: Record<string, "accepted" | "rejected">;
  accepted: string[];
  rejected: string[];
  reasons: Record<string, string>;
  registered_version: string | null;
  single_client?: boolean;
  aggregated?: boolean;
  started_at: string | null;
  last_event_at: string | null;
  bytes_up: number;
  bytes_down: number;
  phase: string;
  phase_label: string;
  is_live: boolean;
  idle_seconds: number | null;
  stages: Stage[];
  source: "mqtt" | "registry";
}

export interface ModelRecord {
  model_version: string | null;
  round: number | null;
  created_utc: string | null;
  parameters: number | null;
  weighted_val_loss: number | null;
  n_samples: number | null;
  n_val: number | null;
  sources: string[];
  kind: string | null;
  evaluated_round: number | null;
  model: Record<string, unknown>;
  has_weights?: boolean;
  record_path?: string;
}

export interface WorkerView {
  id: string;
  worker_id: string;
  role: NodeRole;
  dataset: string;
  shard_index: number | null;
  shard_count: number | null;
  n_samples: number;
  n_val: number;
  model: Record<string, unknown>;
  capabilities: Record<string, unknown>;
  state: string | null;
  registered_at: string | null;
  last_seen: string | null;
  last_seen_age_sec: number | null;
  current_round: number | null;
  progress: number | null;
  phase: string | null;
  detail: string | null;
  update_status: string | null;
  model_version: string | null;
  registration_count: number;
  online: boolean;
  connection: "online" | "offline";
  status: NodeStatus;
  selectable: boolean;
}

export interface WorkerCounts {
  total: number;
  online: number;
  offline: number;
  training: number;
  inference: number;
  available: number;
  busy: number;
}

export interface SessionState {
  session_id: string | null;
  state: string | null;
  config: TrainingConfigInput | null;
  round: number | null;
  completed_rounds: number;
  message: string | null;
  latest_model_version: string | null;
  updated_utc: string | null;
  retained: boolean;
  observed_at?: number;
}

export interface RoundProgressView {
  round: number;
  stage: string;
  status: string;
  stages: Record<string, StageStatus>;
  model_version: string | null;
  selected: string[];
  accepted: string[];
  rejected: Record<string, string>;
  bytes_up: number;
  bytes_down: number;
  single_client: boolean;
  detail: string | null;
  observed_at?: number;
  retained?: boolean;
}

export interface RoundSummaryView {
  round: number;
  status: string;
  selected: string[];
  accepted: string[];
  rejected: Record<string, string>;
  checksums: Record<string, string>;
  model_version: string | null;
  evaluated_version: string | null;
  weighted_val_loss: number | null;
  bytes_up: number;
  bytes_down: number;
  seconds: number;
  single_client: boolean;
  aggregated: boolean;
  config: Record<string, unknown> | null;
  detail: string | null;
  observed_at?: number;
  retained?: boolean;
}

export interface ProcessInfo {
  name: string;
  kind: string;
  role: string | null;
  pid: number;
  running: boolean;
  exit_code: number | null;
  started_at: string | null;
  uptime_sec: number | null;
  command: string[];
  log_path: string;
}

export interface CrashInfo {
  name: string;
  kind: string;
  exit_code: number | null;
  at: string;
  log_tail: string[];
}

export interface ProcessStatus {
  broker: { host: string; port: number; reachable: boolean; owned: boolean };
  processes: ProcessInfo[];
  coordinator: ProcessInfo | null;
  workers: ProcessInfo[];
  crashes: CrashInfo[];
  runtime_dir: string;
}

export interface TrainingConfigInput {
  mode: "fixed" | "continuous";
  rounds: number;
  min_workers: number;
  max_workers: number | null;
  local_epochs: number;
  deadline_sec: number;
  selection_strategy: "all" | "random";
  aggregation_method: "fedavg";
  window_hours: number;
  learning_rate: number;
  simulation_workers: number;
  launch_workers: boolean;
  worker_role: "training" | "inference";
}

export interface WorkersPayload {
  workers: WorkerView[];
  counts: WorkerCounts;
  nodes: NodeView[];
  processes: ProcessInfo[];
  coordinator: ProcessInfo | null;
  broker: ProcessStatus["broker"];
  crashes: CrashInfo[];
}

export interface SessionPayload {
  available: boolean;
  session: SessionState | null;
  current_round: RoundView | null;
  round_progress: RoundView | null;
  round_summaries: RoundSummaryView[];
  workers: WorkerView[];
  worker_counts: WorkerCounts;
  processes: ProcessStatus;
  stage_definition: { key: string; label: string }[];
}

export interface LiveRoundsPayload {
  session: SessionState | null;
  current_round: RoundView | null;
  round_progress: RoundView | null;
  summaries: RoundSummaryView[];
  stage_definition: { key: string; label: string }[];
}

export interface CommandResponse {
  ok: boolean;
  command?: string;
  message?: string;
  config?: TrainingConfigInput;
  session?: SessionState | null;
  readiness?: unknown;
  processes?: ProcessStatus;
  started?: ProcessInfo[];
  skipped?: string[];
  stopped?: string[];
}

export interface LogPayload {
  name: string;
  path: string;
  lines: string[];
  running: boolean;
}

export interface StatusPayload {
  server_time: string;
  data_source: "live_mqtt" | "registry_only" | "unavailable";
  broker: {
    connected: boolean;
    host: string | null;
    port: number | null;
    base_topic?: string;
    last_error: string | null;
    connected_at: string | null;
    last_message_at: string | null;
    connection_count: number;
  };
  observer: {
    started_at: string;
    events: number;
    stale_after_sec: number;
    round_stale_after_sec: number;
  };
  nodes: NodeView[];
  workers?: WorkerView[];
  worker_counts?: WorkerCounts;
  session?: SessionState | null;
  round_progress?: RoundView | null;
  round_summaries?: RoundSummaryView[];
  processes?: ProcessStatus;
  current_round: RoundView | null;
  round_is_live: boolean;
  round_is_stale: boolean;
  latest_model: ModelRecord | null;
  best_model: ModelRecord | null;
  registry: {
    available: boolean;
    path: string | null;
    source: string | null;
    round_count: number | null;
    updated?: string | null;
    rounds_csv?: string | null;
  };
  configured_nodes: { id: string; year: number; role: NodeRole }[];
  config: {
    base_topic: string;
    heartbeat_sec: number;
    training_nodes: string[];
    inference_nodes: string[];
  };
  predictions: {
    available: boolean;
    source: string;
    created_utc?: string;
    model_version?: string | null;
    nodes?: string[];
    horizon_hours?: number;
  };
  system: {
    api_started: string;
    mqtt_enabled: boolean;
    dataset: string;
  };
  provenance: { live: string; historical: string; note: string };
}

export interface RoundHistoryRow {
  round: number;
  selected: string[];
  received: number;
  dropped_nodes: string[];
  bytes_up: number;
  bytes_down: number;
  round_time_sec: number | null;
  weighted_val_loss: number | null;
  evaluated_version: string;
  model_version: string;
}

export interface RoundsPayload {
  available: boolean;
  source: string;
  registry_path: string;
  round_count: number;
  current_round: RoundView | null;
  round_is_live: boolean;
  round_is_stale: boolean;
  stage_definition: { key: string; label: string }[];
  history: RoundHistoryRow[];
  loss_history: {
    round: number;
    weighted_val_loss: number | null;
    evaluated_version: string;
    model_version: string;
  }[];
  note: string;
}

export interface ModelPayload {
  available: boolean;
  source: string;
  registry_path: string;
  latest: ModelRecord | null;
  best: ModelRecord | null;
  versions: ModelRecord[];
  current_round: number | null;
  round_count: number;
  transfer: {
    parameters: number | null;
    bytes: number | null;
    chunk_size: number | null;
    chunks: number | null;
    dtype: string;
  };
  note: string;
}

export interface ComparisonRow {
  method: string;
  label: string;
  short: string;
  color: string;
  description: string;
  requested_method: string;
  n_seeds: number | null;
  n_train: number | null;
  n_test: number | null;
  rmse_raw_mean: number | null;
  rmse_raw_std: number | null;
  mae_raw_mean: number | null;
  mae_raw_std: number | null;
  r2_raw_mean: number | null;
  r2_raw_std: number | null;
  rmse_clipped_mean: number | null;
  mae_clipped_mean: number | null;
  r2_clipped_mean: number | null;
  epochs_mean: number | null;
  train_seconds_mean: number | null;
  parameters: number | null;
  notes: string | null;
}

export interface SeedResult {
  method: string;
  seed: number;
  rmse_raw: number | null;
  mae_raw: number | null;
  r2_raw: number | null;
  rmse_clipped: number | null;
  mae_clipped: number | null;
  r2_clipped: number | null;
  n_test: number | null;
}

export interface MetricsPayload {
  available: boolean;
  sources: Record<string, string | null>;
  headline: string;
  comparison: ComparisonRow[];
  all_methods: ComparisonRow[];
  seed_results: SeedResult[];
  federated_seed_results: Record<string, unknown>[];
  unseen_node5: Record<string, unknown> | null;
  bytes: Record<string, unknown> | null;
  aggregate: Record<string, unknown> | null;
  loss_history: {
    round: number;
    weighted_val_loss: number | null;
    evaluated_version: string;
    model_version: string;
    available: boolean;
  }[];
  loss_summary: {
    available: boolean;
    latest: number | null;
    best: number | null;
    note: string;
  };
  active_registry: {
    source: string;
    path: string;
    latest_model_version: string | null;
  };
  notes: string;
}

export interface AirPoint {
  ts: string;
  actual: number | null;
  actual_filled: number | null;
  predicted: number | null;
  temp: number | null;
  rh: number | null;
}

export interface AirQualityPayload {
  node: string;
  year: number;
  mode: "historical_replay";
  is_realtime: false;
  dataset: { name: string; path: string; timezone: string };
  prediction_source: "fedavg_offline" | "persistence_reference";
  prediction_label: string;
  model_version: string | null;
  prediction_stale: boolean;
  note: string;
  actual_note: string;
  units: { pm25: string; temp: string; rh: string };
  range: { start: string | null; end: string | null; points: number };
  series: AirPoint[];
  available_nodes: { id: string; year: number; predictions_available: boolean }[];
  predictions: {
    available: boolean;
    source: string;
    created_utc?: string;
    model_version?: string | null;
    nodes?: string[];
    horizon_hours?: number;
  };
  latest_model_version: string | null;
}

export interface CommEvent {
  id: number;
  at: string | null;
  topic: string;
  kind: string;
  node_id: string | null;
  round: number | null;
  model_version: string | null;
  status: string | null;
  index: number | null;
  chunks: number | null;
  size_bytes: number;
  checksum: string | null;
  checksum_ok: boolean | null;
  retained: boolean;
  detail: string;
  direction?: "up" | "down";
}

export interface CommunicationPayload {
  server_time: string;
  broker: {
    connected: boolean;
    last_error: string | null;
    connected_at: string | null;
    last_message_at: string | null;
    host: string | null;
    port: number | null;
    base_topic?: string;
  };
  observed: {
    bytes_up: number;
    bytes_down: number;
    messages: number;
    chunks: number;
    chunk_bytes: number;
    checksum_ok: number;
    checksum_bad: number;
    acks_accepted: number;
    acks_rejected: number;
  };
  live_round: RoundView | null;
  history: {
    round: number;
    bytes_up: number;
    bytes_down: number;
    received: number;
    selected: number;
    dropped_nodes: string[];
    round_time_sec: number | null;
  }[];
  last_model_announce: {
    model_version: string | null;
    federated_round: number | null;
    chunks: number | null;
    sha256: string | null;
    size: number | null;
    at: string | null;
    retained: boolean;
  } | null;
  model_transfer: {
    model_version: string | null;
    parameters: number | null;
    bytes: number | null;
    chunk_size: number | null;
    chunks: number | null;
    source: string;
  };
  acks: { accepted: number; rejected: number; rejected_events: CommEvent[] };
  events: CommEvent[];
  topic_contract: { topic: string; direction: "up" | "down"; purpose: string }[];
  registry: { source: string; path: string | null; available: boolean };
  provenance: { observed: string; history: string; note: string };
}

export interface LiveMessage {
  type: "hello" | "mqtt_event" | "tick";
  at?: string;
  event?: CommEvent;
  data?: {
    mqtt_enabled: boolean;
    broker: { host: string; port: number; base_topic: string };
  };
}

export interface SocketState {
  status: "connecting" | "open" | "closed";
  lastEvent: CommEvent | null;
  lastMessageAt: string | null;
  retryInMs: number | null;
}

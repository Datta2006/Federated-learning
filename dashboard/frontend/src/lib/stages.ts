import type { Stage } from "../types";

/** Mirrors common.worker_protocol.ROUND_STAGES. */
export const ROUND_STAGES: { key: string; label: string }[] = [
  { key: "waiting_for_workers", label: "Waiting for workers" },
  { key: "client_selection", label: "Client selection" },
  { key: "model_distribution", label: "Global model distribution" },
  { key: "local_training", label: "Local training" },
  { key: "update_upload", label: "Update upload" },
  { key: "update_validation", label: "Update validation" },
  { key: "aggregation", label: "Aggregation" },
  { key: "model_registration", label: "Model registration" },
];

export function pendingStages(): Stage[] {
  return ROUND_STAGES.map((stage) => ({ ...stage, status: "pending" }));
}

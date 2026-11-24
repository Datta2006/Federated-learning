import apiClient from './client'
import type {
  ExperimentSchema,
  ExperimentDetailSchema,
  ExperimentSummarySchema,
  ExperimentCreateRequest,
  ExperimentUpdateRequest,
  RoundSchema,
} from './types'

// List experiments
export const listExperiments = async (
  limit = 100,
  offset = 0,
  status?: string,
): Promise<ExperimentSchema[]> => {
  const params: Record<string, number | string> = { limit, offset }
  if (status) params['status'] = status
  const response = await apiClient.get<ExperimentSchema[]>('/v1/experiments', { params })
  return response.data
}

// Get single experiment
export const getExperiment = async (experimentId: string): Promise<ExperimentDetailSchema> => {
  const response = await apiClient.get<ExperimentDetailSchema>(`/v1/experiments/${experimentId}`)
  return response.data
}

// Get experiment summary
export const getExperimentSummary = async (experimentId: string): Promise<ExperimentSummarySchema> => {
  const response = await apiClient.get<ExperimentSummarySchema>(`/v1/experiments/${experimentId}/summary`)
  return response.data
}

// Get experiment rounds
export const getExperimentRounds = async (
  experimentId: string,
  limit = 1000,
): Promise<RoundSchema[]> => {
  const response = await apiClient.get<RoundSchema[]>(`/v1/experiments/${experimentId}/rounds`, {
    params: { limit },
  })
  return response.data
}

// Create experiment
export const createExperiment = async (
  request: ExperimentCreateRequest,
): Promise<ExperimentSchema> => {
  const response = await apiClient.post<ExperimentSchema>('/v1/experiments', request)
  return response.data
}

// Update experiment
export const updateExperiment = async (
  experimentId: string,
  request: ExperimentUpdateRequest,
): Promise<ExperimentSchema> => {
  const response = await apiClient.patch<ExperimentSchema>(`/v1/experiments/${experimentId}`, request)
  return response.data
}

// Delete experiment
export const deleteExperiment = async (experimentId: string): Promise<void> => {
  await apiClient.delete(`/v1/experiments/${experimentId}`)
}

// Submit round
export const submitRound = async (round: Partial<RoundSchema> & { experiment_id: string; round_number: number }) => {
  const response = await apiClient.post('/v1/experiments/rounds', round)
  return response.data
}

// Complete experiment
export const completeExperiment = async (
  experimentId: string,
  params?: {
    val_loss?: number
    val_acc?: number
    test_loss?: number
    test_acc?: number
    duration_sec?: number
  },
) => {
  const response = await apiClient.post(`/v1/experiments/${experimentId}/complete`, params)
  return response.data
}

// Recover experiment from stage4
export const recoverStage4Experiment = async (stage4Path: string) => {
  const response = await apiClient.post('/v1/experiments/recover-stage4', null, {
    params: { stage4_path: stage4Path },
  })
  return response.data
}
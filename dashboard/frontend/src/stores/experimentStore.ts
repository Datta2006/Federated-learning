import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import type {
  ExperimentSchema,
  ExperimentDetailSchema,
  ExperimentSummarySchema,
  RoundSchema,
  MetricsSchema,
} from '@/api/types'

export interface ExperimentState {
  // Data
  experiments: ExperimentSchema[]
  currentExperiment: ExperimentDetailSchema | null
  currentExperimentRounds: RoundSchema[]
  currentExperimentSummary: ExperimentSummarySchema | null
  metrics: MetricsSchema | null
  isLoading: boolean
  error: string | null

  // Filters
  statusFilter: string | null
  searchQuery: string

  // Actions
  fetchExperiments: (status?: string) => Promise<void>
  fetchExperiment: (id: string) => Promise<void>
  fetchExperimentRounds: (id: string) => Promise<void>
  fetchExperimentSummary: (id: string) => Promise<void>
  createExperiment: (data: Partial<ExperimentSchema>) => Promise<void>
  updateExperiment: (id: string, data: Partial<ExperimentSchema>) => Promise<void>
  deleteExperiment: (id: string) => Promise<void>
  setActiveExperiment: (experiment: ExperimentDetailSchema) => void
  setStatusFilter: (status: string | null) => void
  setSearchQuery: (query: string) => void
  clearError: () => void
  clearExperiments: () => void
}

export const useExperimentStore = create<ExperimentState>()(
  devtools(
    persist(
      (set, get) => ({
        // Initial state
        experiments: [],
        currentExperiment: null,
        currentExperimentRounds: [],
        currentExperimentSummary: null,
        metrics: null,
        isLoading: false,
        error: null,
        statusFilter: null,
        searchQuery: '',

        // Actions
        fetchExperiments: async (status) => {
          set({ isLoading: true, error: null })
          try {
            const experiments = await import('@/api/experiments').then(m => m.listExperiments(undefined, undefined, status))
            set({ experiments, isLoading: false })
          } catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to fetch experiments', isLoading: false })
          }
        },

        fetchExperiment: async (id) => {
          set({ isLoading: true, error: null })
          try {
            const experiment = await import('@/api/experiments').then(m => m.getExperiment(id))
            set({ currentExperiment: experiment, isLoading: false })
          } catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to fetch experiment', isLoading: false })
          }
        },

        fetchExperimentRounds: async (id) => {
          set({ isLoading: true, error: null })
          try {
            const rounds = await import('@/api/experiments').then(m => m.getExperimentRounds(id))
            set({ currentExperimentRounds: rounds, isLoading: false })
          } catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to fetch rounds', isLoading: false })
          }
        },

        fetchExperimentSummary: async (id) => {
          set({ isLoading: true, error: null })
          try {
            const summary = await import('@/api/experiments').then(m => m.getExperimentSummary(id))
            set({ currentExperimentSummary: summary, isLoading: false })
          } catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to fetch summary', isLoading: false })
          }
        },

        createExperiment: async (data) => {
          set({ isLoading: true, error: null })
          try {
            const experiment = await import('@/api/experiments').then(m =>
              m.createExperiment(data as any)
            )
            set(state => ({
              experiments: [...state.experiments, experiment],
              isLoading: false,
            }))
          } catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to create experiment', isLoading: false })
          }
        },

        updateExperiment: async (id, data) => {
          set({ isLoading: true, error: null })
          try {
            const experiment = await import('@/api/experiments').then(m =>
              m.updateExperiment(id, data as any)
            )
            set(state => ({
              experiments: state.experiments.map(e => e.id === id ? experiment : e),
              currentExperiment: get().currentExperiment?.id === id ? { ...get().currentExperiment, ...data } as ExperimentDetailSchema : get().currentExperiment,
              isLoading: false,
            }))
          } catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to update experiment', isLoading: false })
          }
        },

        deleteExperiment: async (id) => {
          set({ isLoading: true, error: null })
          try {
            await import('@/api/experiments').then(m => m.deleteExperiment(id))
            set(state => ({
              experiments: state.experiments.filter(e => e.id !== id),
              isLoading: false,
            }))
          } catch (error) {
            set({ error: error instanceof Error ? error.message : 'Failed to delete experiment', isLoading: false })
          }
        },

        setActiveExperiment: (experiment) => {
          set({ currentExperiment: experiment })
        },

        setStatusFilter: (status) => {
          set({ statusFilter: status })
        },

        setSearchQuery: (query) => {
          set({ searchQuery: query })
        },

        clearError: () => {
          set({ error: null })
        },

        clearExperiments: () => {
          set({
            experiments: [],
            currentExperiment: null,
            currentExperimentRounds: [],
            currentExperimentSummary: null,
            metrics: null,
          })
        },
      }),
      {
        name: 'experiment-store',
      },
    ),
  ),
)
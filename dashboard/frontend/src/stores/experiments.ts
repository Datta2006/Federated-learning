/**
 * Zustand Store for Experiments
 * Centralized state management for experiment data
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type {
  ExperimentSchema,
  ExperimentDetailSchema,
  ExperimentSummarySchema,
  RoundSchema,
} from '../api/types';

export interface ExperimentsState {
  // Data
  experiments: ExperimentSchema[];
  activeExperiment: ExperimentDetailSchema | null;
  experimentRounds: RoundSchema[];
  selectedExperimentId: string | null;

  // Loading states
  isLoadingExperiments: boolean;
  isLoadingExperiment: boolean;
  isLoadingRounds: boolean;

  // Error states
  error: string | null;

  // Filters
  statusFilter: string | null;
  typeFilter: string | null;

  // Actions
  setExperiments: (experiments: ExperimentSchema[]) => void;
  setActiveExperiment: (experiment: ExperimentDetailSchema | null) => void;
  setRounds: (rounds: RoundSchema[]) => void;
  setSelectedExperimentId: (id: string | null) => void;
  setStatusFilter: (status: string | null) => void;
  setTypeFilter: (type: string | null) => void;

  // Loading setters
  setLoadingExperiments: (loading: boolean) => void;
  setLoadingExperiment: (loading: boolean) => void;
  setLoadingRounds: (loading: boolean) => void;

  // Error handling
  setError: (error: string | null) => void;

  // Data fetching actions
  fetchExperiments: (params?: { limit?: number; offset?: number; status?: string }) => Promise<void>;
  fetchExperiment: (id: string) => Promise<void>;
  fetchExperimentRounds: (experimentId: string, limit?: number) => Promise<void>;
  fetchExperimentSummary: (experimentId: string) => Promise<ExperimentSummarySchema | null>;

  // CRUD actions
  createExperiment: (data: Omit<ExperimentSchema, 'id' | 'status' | 'created_at' | 'started_at' | 'completed_at'> & { id?: string }) => Promise<void>;
  updateExperiment: (id: string, data: Partial<ExperimentSchema>) => Promise<void>;
  deleteExperiment: (id: string) => Promise<void>;
}

export const useExperimentsStore = create<ExperimentsState>()(
  devtools(
    persist(
      (set, get) => ({
        // Initial state
        experiments: [],
        activeExperiment: null,
        experimentRounds: [],
        selectedExperimentId: null,
        isLoadingExperiments: false,
        isLoadingExperiment: false,
        isLoadingRounds: false,
        error: null,
        statusFilter: null,
        typeFilter: null,

        // Setters
        setExperiments: (experiments) => set({ experiments }),
        setActiveExperiment: (experiment) => set({ activeExperiment: experiment }),
        setRounds: (rounds) => set({ experimentRounds: rounds }),
        setSelectedExperimentId: (id) => set({ selectedExperimentId: id }),
        setStatusFilter: (status) => set({ statusFilter: status }),
        setTypeFilter: (type) => set({ typeFilter: type }),
        setLoadingExperiments: (loading) => set({ isLoadingExperiments: loading }),
        setLoadingExperiment: (loading) => set({ isLoadingExperiment: loading }),
        setLoadingRounds: (loading) => set({ isLoadingRounds: loading }),
        setError: (error) => set({ error }),

        // Data fetching actions
        fetchExperiments: async (params) => {
          const { limit, offset, status } = params || {};
          set({ isLoadingExperiments: true, error: null });

          try {
            const apiClient = (await import('../api/client')).default;
            const experiments = await apiClient.get('/v1/experiments', { params: { limit, offset, status } });
            set({ experiments: experiments.data, isLoadingExperiments: false });
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to fetch experiments';
            set({ error: message, isLoadingExperiments: false });
          }
        },

        fetchExperiment: async (id) => {
          set({ isLoadingExperiment: true, error: null, selectedExperimentId: id });

          try {
            const apiClient = (await import('../api/client')).default;
            const experiment = await apiClient.get(`/v1/experiments/${id}`);
            const summary = await apiClient.get(`/v1/experiments/${id}/summary`);

            // Merge summary into experiment details
            const experimentWithMetrics = {
              ...experiment.data,
              metrics: summary.data?.metrics,
            };

            set({
              activeExperiment: experimentWithMetrics as ExperimentDetailSchema,
              isLoadingExperiment: false
            });
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to fetch experiment';
            set({ error: message, isLoadingExperiment: false });
          }
        },

        fetchExperimentRounds: async (experimentId, limit = 100) => {
          set({ isLoadingRounds: true, error: null });

          try {
            const apiClient = (await import('../api/client')).default;
            const rounds = await apiClient.get(`/v1/experiments/${experimentId}/rounds`, { params: { limit } });
            set({ experimentRounds: rounds.data, isLoadingRounds: false });
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to fetch rounds';
            set({ error: message, isLoadingRounds: false });
          }
        },

        fetchExperimentSummary: async (experimentId) => {
          try {
            const apiClient = (await import('../api/client')).default;
            const summary = await apiClient.get(`/v1/experiments/${experimentId}/summary`);
            return summary.data;
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to fetch summary';
            set({ error: message });
            return null;
          }
        },

        // CRUD actions
        createExperiment: async (data) => {
          set({ error: null });

          try {
            const apiClient = (await import('../api/client')).default;
            const experiment = await apiClient.post('/v1/experiments', data);
            const { experiments } = get();
            set({ experiments: [...experiments, experiment.data] });
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to create experiment';
            set({ error: message });
            throw error;
          }
        },

        updateExperiment: async (id, data) => {
          set({ error: null });

          try {
            const apiClient = (await import('../api/client')).default;
            const experiment = await apiClient.put(`/v1/experiments/${id}`, data);
            const { experiments } = get();
            set({
              experiments: experiments.map((e) => (e.id === id ? { ...e, ...experiment.data } : e)),
              activeExperiment: get().activeExperiment?.id === id
                ? { ...get().activeExperiment, ...data } as ExperimentDetailSchema
                : get().activeExperiment,
            });
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to update experiment';
            set({ error: message });
            throw error;
          }
        },

        deleteExperiment: async (id) => {
          set({ error: null });

          try {
            const apiClient = (await import('../api/client')).default;
            await apiClient.delete(`/v1/experiments/${id}`);
            const { experiments } = get();
            set({ experiments: experiments.filter((e) => e.id !== id) });
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to delete experiment';
            set({ error: message });
            throw error;
          }
        },
      }),
      { name: 'experiments-storage' },
    ),
  ),
);

export default useExperimentsStore;
/**
 * React Hooks for Experiment Data
 * Provides data fetching, caching, and mutation hooks
 */

import { useEffect, useCallback, useState } from 'react';
import useExperimentsStore from '../stores/experiments';
import type { ExperimentSchema, ExperimentSummarySchema } from '../api/types';

export function useExperiments(params?: {
  limit?: number;
  offset?: number;
  status?: string;
}) {
  const {
    experiments,
    isLoadingExperiments,
    error,
    fetchExperiments,
    statusFilter,
  } = useExperimentsStore();

  useEffect(() => {
    // Use params if provided, otherwise use filter state
    const fetchParams = params || { status: statusFilter || undefined };

    // Only fetch if not already loading or if params changed significantly
    if (fetchParams) {
      fetchExperiments(fetchParams as { limit?: number; offset?: number; status?: string });
    }
  }, [fetchExperiments, params, statusFilter]);

  return {
    experiments,
    isLoading: isLoadingExperiments,
    error,
    refetch: () => fetchExperiments(params),
  };
}

export function useExperiment(id: string) {
  const {
    activeExperiment,
    isLoadingExperiment,
    error,
    fetchExperiment,
  } = useExperimentsStore();

  useEffect(() => {
    if (id) {
      fetchExperiment(id);
    }
  }, [fetchExperiment, id]);

  return {
    experiment: activeExperiment,
    isLoading: isLoadingExperiment,
    error,
    refetch: () => fetchExperiment(id),
  };
}

export function useExperimentRounds(experimentId: string, limit?: number) {
  const {
    experimentRounds,
    isLoadingRounds,
    error,
    fetchExperimentRounds,
  } = useExperimentsStore();

  useEffect(() => {
    if (experimentId) {
      fetchExperimentRounds(experimentId, limit);
    }
  }, [fetchExperimentRounds, experimentId, limit]);

  return {
    rounds: experimentRounds,
    isLoading: isLoadingRounds,
    error,
    refetch: () => fetchExperimentRounds(experimentId, limit),
  };
}

export function useExperimentSummary(experimentId: string) {
  const {
    fetchExperimentSummary,
    error: fetchError,
  } = useExperimentsStore();

  const [summary, setSummary] = useState<ExperimentSummarySchema | null>(null);
  const [loading, setLoading] = useState<boolean>(!!experimentId);

  useEffect(() => {
    if (experimentId) {
      setLoading(true);
      fetchExperimentSummary(experimentId).then((data) => {
        setSummary(data);
        setLoading(false);
      }).catch(() => {
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, [experimentId, fetchExperimentSummary]);

  return {
    summary,
    isLoading: loading,
    error: fetchError,
    refetch: () => {
      if (experimentId) {
        setLoading(true);
        fetchExperimentSummary(experimentId).then((data) => {
          setSummary(data);
          setLoading(false);
        }).catch(() => {
          setLoading(false);
        });
      }
    },
  };
}

export function useCreateExperiment() {
  const { createExperiment, error } = useExperimentsStore();
  const [isCreating, setIsCreating] = useState(false);

  const create = useCallback(async (data: Omit<ExperimentSchema, 'id' | 'status' | 'created_at' | 'started_at' | 'completed_at'> & { id?: string }) => {
    setIsCreating(true);
    try {
      await createExperiment(data);
    } finally {
      setIsCreating(false);
    }
  }, [createExperiment]);

  return { create, isCreating, error };
}

export function useUpdateExperiment() {
  const { updateExperiment, error } = useExperimentsStore();
  const [isUpdating, setIsUpdating] = useState(false);

  const update = useCallback(async (id: string, data: Partial<ExperimentSchema>) => {
    setIsUpdating(true);
    try {
      await updateExperiment(id, data);
    } finally {
      setIsUpdating(false);
    }
  }, [updateExperiment]);

  return { update, isUpdating, error };
}

export function useDeleteExperiment() {
  const { deleteExperiment, error } = useExperimentsStore();
  const [isDeleting, setIsDeleting] = useState(false);

  const deleteExp = useCallback(async (id: string) => {
    setIsDeleting(true);
    try {
      await deleteExperiment(id);
    } finally {
      setIsDeleting(false);
    }
  }, [deleteExperiment]);

  return { delete: deleteExp, isDeleting, error };
}
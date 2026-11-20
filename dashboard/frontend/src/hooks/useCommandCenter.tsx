import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { apiGet } from "../lib/api";
import { useLiveFeed } from "./useLiveFeed";
import type { StatusPayload } from "../types";

interface CommandCenter {
  status: StatusPayload | null;
  error: string | null;
  loading: boolean;
  lastUpdated: Date | null;
  socket: "connecting" | "open" | "closed";
  retryInMs: number | null;
  refresh: () => void;
}

const CommandCenterContext = createContext<CommandCenter | null>(null);

const POLL_MS = 5000;

/**
 * One shared polling + WebSocket state source for every page.
 *
 * - Polling is the guaranteed path (works behind any proxy).
 * - A WebSocket event triggers a debounced refetch instead of a full page
 *   reload, so bursts of upload chunks collapse into one API call.
 * - The previous snapshot stays visible during transient errors; the error is
 *   surfaced in the shell rather than blanking the interface.
 */
export function CommandCenterProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const { revision, snapshot, status: socket, retryInMs } = useLiveFeed();

  const cancelled = useRef(false);
  const fetching = useRef(false);
  const queued = useRef(false);
  const debounce = useRef<number | null>(null);

  const fetchStatus = useCallback(async () => {
    if (fetching.current) {
      queued.current = true;
      return;
    }
    fetching.current = true;
    try {
      const payload = await apiGet<StatusPayload>("/api/status");
      if (cancelled.current) return;
      setStatus(payload);
      setError(null);
      setLastUpdated(new Date());
    } catch (caught) {
      if (cancelled.current) return;
      setError(caught instanceof Error ? caught.message : "Request failed");
    } finally {
      fetching.current = false;
      setLoading(false);
      if (queued.current) {
        queued.current = false;
        void fetchStatus();
      }
    }
  }, []);

  useEffect(() => {
    cancelled.current = false;
    void fetchStatus();
    const interval = window.setInterval(() => void fetchStatus(), POLL_MS);
    return () => {
      cancelled.current = true;
      window.clearInterval(interval);
    };
  }, [fetchStatus]);

  useEffect(() => {
    if (!revision) return;
    if (debounce.current !== null) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => void fetchStatus(), 600);
    return () => {
      if (debounce.current !== null) window.clearTimeout(debounce.current);
    };
  }, [revision, fetchStatus]);

  const value = useMemo<CommandCenter>(
    () => ({
      status,
      error,
      loading,
      lastUpdated,
      socket,
      retryInMs,
      refresh: () => void fetchStatus(),
    }),
    [status, error, loading, lastUpdated, socket, retryInMs, fetchStatus],
  );

  // The snapshot is a fast paint path; the next poll reconciles details.
  useEffect(() => {
    if (!snapshot) return;
    setStatus((current) => {
      if (!current) return current;
      return {
        ...current,
        server_time: snapshot.server_time ?? current.server_time,
        session_view: snapshot.session ?? current.session_view,
        current_round: snapshot.current_round ?? current.current_round,
        worker_counts: snapshot.worker_counts ?? current.worker_counts,
        infrastructure: snapshot.infrastructure ?? current.infrastructure,
      };
    });
  }, [snapshot]);

  return (
    <CommandCenterContext.Provider value={value}>
      {children}
    </CommandCenterContext.Provider>
  );
}

export function useCommandCenter(): CommandCenter {
  const context = useContext(CommandCenterContext);
  if (!context) {
    throw new Error("useCommandCenter must be used inside CommandCenterProvider");
  }
  return context;
}

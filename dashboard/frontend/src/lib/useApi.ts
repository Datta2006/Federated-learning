import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "./api";

interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  lastUpdated: Date | null;
  refresh: () => void;
}

export function useApi<T>(path: string, refreshMs = 0): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [nonce, setNonce] = useState(0);
  const hasData = useRef(false);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const run = async () => {
      if (!hasData.current) setLoading(true);
      try {
        const payload = await apiGet<T>(path, controller.signal);
        if (cancelled) return;
        hasData.current = true;
        setData(payload);
        setError(null);
        setLastUpdated(new Date());
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "Request failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [path, nonce]);

  useEffect(() => {
    if (refreshMs <= 0) return;
    const id = window.setInterval(() => setNonce((value) => value + 1), refreshMs);
    return () => window.clearInterval(id);
  }, [refreshMs]);

  return { data, error, loading, lastUpdated, refresh };
}

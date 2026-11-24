import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../lib/api";

/**
 * Poll a JSON endpoint. `intervalMs = 0` disables the timer but still loads
 * once. The previous payload stays visible during a transient error.
 */
export function usePoll<T>(path: string | null, intervalMs = 5000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);

    const load = async () => {
      try {
        const payload = await apiGet<T>(path);
        if (cancelled) return;
        setData(payload);
        setError(null);
        setUpdatedAt(new Date());
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "Request failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    const timer =
      intervalMs > 0 ? window.setInterval(() => void load(), intervalMs) : null;
    return () => {
      cancelled = true;
      if (timer !== null) window.clearInterval(timer);
    };
  }, [path, intervalMs, tick]);

  return { data, error, loading, updatedAt, refresh };
}

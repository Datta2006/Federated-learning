import { useCallback, useState } from "react";
import { apiPost } from "../lib/api";

/** Small POST action helper with pending/error state for control buttons. */
export function useAction<T = unknown>() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<T | null>(null);

  const run = useCallback(async (path: string, body?: unknown): Promise<T | null> => {
    setPending(true);
    setError(null);
    try {
      const payload = await apiPost<T>(path, body);
      setResult(payload);
      return payload;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed");
      return null;
    } finally {
      setPending(false);
    }
  }, []);

  const resetError = useCallback(() => setError(null), []);

  return { run, pending, error, result, resetError };
}

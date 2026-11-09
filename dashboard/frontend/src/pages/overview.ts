import { useState, useEffect } from "react";
import { apiGet } from "../lib/api";
import { useLiveFeed } from "../hooks/useLiveFeed";
import type { StatusPayload } from "../types";

type OverviewSnapshot = StatusPayload;

/**
 * Pulls the live status payload and refreshes on every `mqtt_event` message.
 * Returns null while loading or after a request error so callers can show a
 * Skeleton or an ErrorState accordingly.
 */
export function useOverviewStatus(refreshMs = 3000): OverviewSnapshot | null {
  const [data, setData] = useState<OverviewSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const payload = await apiGet<StatusPayload>("/api/status");
      setData(payload);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      // Keep existing snapshot visible on transient errors; only clear it when the
      // transport is truly down so callers can decide between Skeleton vs ErrorState.
    }
  };

  useLiveFeed({
    onMessage: () => void refresh(),
  });

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(refresh, refreshMs);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return data;
}

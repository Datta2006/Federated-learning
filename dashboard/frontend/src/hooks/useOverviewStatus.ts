import { useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { useLiveFeed } from "./useLiveFeed";
import type { StatusPayload } from "../types";

/**
 * Pulls `/api/status` and refetches on every MQTT event from the live feed.
 * Returns null until the first successful response.
 */
export function useOverviewStatus(refreshMs = 3000): StatusPayload | null {
  const [data, setData] = useState<StatusPayload | null>(null);
  const { revision } = useLiveFeed();

  useEffect(() => {
    let cancelled = false;

    const refresh = async () => {
      try {
        const payload = await apiGet<StatusPayload>("/api/status");
        if (!cancelled) setData(payload);
      } catch {
        // Keep the previous snapshot visible on transient API errors.
      }
    };

    void refresh();
    const interval = window.setInterval(refresh, refreshMs);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [refreshMs, revision]);

  return data;
}

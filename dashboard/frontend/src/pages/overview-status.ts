import { useState, useEffect } from "react";
import { apiGet } from "../lib/api";
import { useLiveFeed } from "../hooks/useLiveFeed";
import type { StatusPayload } from "../types";

type OverviewSnapshot = StatusPayload;

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
    }
  };

  useLiveFeed({ onMessage: () => void refresh() });

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(refresh, refreshMs);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return data;
}

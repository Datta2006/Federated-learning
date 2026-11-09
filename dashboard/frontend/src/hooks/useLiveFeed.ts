import { useEffect, useRef, useState } from "react";
import type { CommEvent, LiveMessage, SocketState } from "../types";
import { websocketUrl } from "../lib/api";

const MAX_BACKOFF = 15000;

/**
 * Read-only WebSocket feed. Reconnects with capped exponential backoff and
 * exposes a revision counter that pages can use to refetch on new telemetry.
 */
export function useLiveFeed(): SocketState & { revision: number } {
  const [status, setStatus] = useState<SocketState["status"]>("connecting");
  const [lastEvent, setLastEvent] = useState<CommEvent | null>(null);
  const [lastMessageAt, setLastMessageAt] = useState<string | null>(null);
  const [retryInMs, setRetryInMs] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);

  const socket = useRef<WebSocket | null>(null);
  const retry = useRef(0);
  const timer = useRef<number | null>(null);
  const disposed = useRef(false);

  useEffect(() => {
    disposed.current = false;

    const connect = () => {
      if (disposed.current) return;
      setStatus("connecting");
      setRetryInMs(null);
      let ws: WebSocket;
      try {
        ws = new WebSocket(websocketUrl());
      } catch {
        schedule();
        return;
      }
      socket.current = ws;

      ws.onopen = () => {
        retry.current = 0;
        setStatus("open");
        setRetryInMs(null);
      };

      ws.onmessage = (raw) => {
        let message: LiveMessage;
        try {
          message = JSON.parse(raw.data as string) as LiveMessage;
        } catch {
          return;
        }
        if (message.type === "hello") {
          setStatus("open");
          return;
        }
        setLastMessageAt(new Date().toISOString());
        if (message.type === "mqtt_event" && message.event) {
          setLastEvent(message.event);
          // Batch UI refreshes: the feed could be chatty during weight upload.
          setRevision((value) => value + 1);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onclose = () => {
        if (socket.current === ws) socket.current = null;
        if (disposed.current) return;
        setStatus("closed");
        schedule();
      };
    };

    const schedule = () => {
      const delay = Math.min(1000 * 2 ** retry.current, MAX_BACKOFF);
      retry.current += 1;
      setRetryInMs(delay);
      timer.current = window.setTimeout(connect, delay);
    };

    connect();

    return () => {
      disposed.current = true;
      if (timer.current !== null) window.clearTimeout(timer.current);
      socket.current?.close();
      socket.current = null;
    };
  }, []);

  return { status, lastEvent, lastMessageAt, retryInMs, revision };
}

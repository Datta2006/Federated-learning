import { useEffect, useRef, useState } from "react";
import type { LiveMessage, SocketState } from "../types";
import { websocketUrl } from "../lib/api";

const MAX_BACKOFF = 15000;

/**
 * WebSocket feed with automatic reconnect, an initial server snapshot, and
 * client-initiated pings. The revision counter lets pages refetch on demand;
 * the snapshot is the authoritative state at connect time.
 */
export function useLiveFeed(): SocketState & {
  revision: number;
  snapshot: LiveMessage["data"] | null;
} {
  const [status, setStatus] = useState<SocketState["status"]>("connecting");
  const [lastEvent, setLastEvent] = useState<SocketState["lastEvent"]>(null);
  const [lastMessageAt, setLastMessageAt] = useState<string | null>(null);
  const [retryInMs, setRetryInMs] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const [snapshot, setSnapshot] = useState<LiveMessage["data"] | null>(null);

  const socket = useRef<WebSocket | null>(null);
  const retry = useRef(0);
  const timer = useRef<number | null>(null);
  const ping = useRef<number | null>(null);
  const disposed = useRef(false);

  useEffect(() => {
    disposed.current = false;

    const clearPing = () => {
      if (ping.current !== null) {
        window.clearInterval(ping.current);
        ping.current = null;
      }
    };

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
        clearPing();
        ping.current = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 20000);
      };

      ws.onmessage = (raw) => {
        let message: LiveMessage;
        try {
          message = JSON.parse(raw.data as string) as LiveMessage;
        } catch {
          return;
        }
        if (message.type === "snapshot") {
          setSnapshot(message.data ?? null);
          setStatus("open");
          return;
        }
        if (message.type === "pong") return;
        setLastMessageAt(new Date().toISOString());
        if (message.type === "mqtt_event" && message.event) {
          setLastEvent(message.event);
          setRevision((value) => value + 1);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onclose = () => {
        clearPing();
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
      clearPing();
      if (timer.current !== null) window.clearTimeout(timer.current);
      socket.current?.close();
      socket.current = null;
    };
  }, []);

  return { status, lastEvent, lastMessageAt, retryInMs, revision, snapshot };
}

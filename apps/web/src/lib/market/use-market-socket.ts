"use client";

import { useEffect, useRef } from "react";

import { api } from "@/lib/api/client";

export interface LiveBar {
  instrument_id: string;
  ts: string;
  open?: string;
  high?: string;
  low?: string;
  close: string;
  volume?: string;
  is_final: boolean;
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8080/market/ws";

/**
 * Subscribe to live bars for one instrument. Fetches a one-time ticket, opens
 * the WS, subscribes, and reconnects with exponential backoff. `onBar` is kept
 * in a ref so re-renders don't reconnect.
 */
export function useMarketSocket(instrumentId: string | null, onBar: (bar: LiveBar) => void): void {
  const onBarRef = useRef(onBar);
  useEffect(() => {
    onBarRef.current = onBar;
  });

  useEffect(() => {
    if (!instrumentId) return;
    let socket: WebSocket | null = null;
    let stopped = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const scheduleReconnect = () => {
      attempt += 1;
      timer = setTimeout(connect, Math.min(1000 * 2 ** attempt, 15000));
    };

    async function connect() {
      if (stopped) return;
      try {
        const { ticket } = await api.wsTicket();
        if (stopped) return;
        socket = new WebSocket(`${WS_URL}?ticket=${encodeURIComponent(ticket)}`);
        socket.onopen = () => {
          attempt = 0;
          socket?.send(JSON.stringify({ action: "subscribe", instrument_id: instrumentId }));
        };
        socket.onmessage = (event) => {
          try {
            onBarRef.current(JSON.parse(event.data as string) as LiveBar);
          } catch {
            /* ignore malformed frame */
          }
        };
        socket.onclose = () => {
          if (!stopped) scheduleReconnect();
        };
        socket.onerror = () => socket?.close();
      } catch {
        scheduleReconnect();
      }
    }

    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [instrumentId]);
}

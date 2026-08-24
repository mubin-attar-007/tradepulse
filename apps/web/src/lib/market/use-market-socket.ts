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

/** Explicit override, inlined at build time. Empty/unset means "same origin". */
const CONFIGURED_WS_URL = process.env.NEXT_PUBLIC_WS_URL?.trim();

/**
 * Resolve the market WebSocket endpoint.
 *
 * A hardcoded `ws://localhost:8080` default is actively harmful once the bundle is
 * built: NEXT_PUBLIC_* are frozen at build time, so a missing build arg shipped that
 * literal to every visitor — a plaintext connection to the *user's own* machine, which
 * an HTTPS page blocks as mixed content and which the reconnect loop then retries
 * forever. Deriving it from the current origin instead is correct wherever the app is
 * served, because the reverse proxy exposes the WS under the same `/api` prefix the
 * REST client already uses. Called lazily (never at module scope) so SSR has no
 * `window` dependency.
 */
function resolveWsUrl(): string | null {
  if (CONFIGURED_WS_URL) return CONFIGURED_WS_URL;
  if (typeof window === "undefined") return null;
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  const base = (process.env.NEXT_PUBLIC_API_BASE ?? "/api").replace(/\/$/, "");
  // Only a relative API base can be joined to this origin; an absolute one means the
  // API lives elsewhere and NEXT_PUBLIC_WS_URL has to be set explicitly.
  if (!base.startsWith("/")) return null;
  return `${scheme}//${window.location.host}${base}/market/ws`;
}

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
      const wsUrl = resolveWsUrl();
      // No resolvable endpoint (absolute API base with no explicit WS override): stay
      // silent rather than hammering a guessed host. The chart still renders polled bars.
      if (!wsUrl) return;
      try {
        const { ticket } = await api.wsTicket();
        if (stopped) return;
        socket = new WebSocket(`${wsUrl}?ticket=${encodeURIComponent(ticket)}`);
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

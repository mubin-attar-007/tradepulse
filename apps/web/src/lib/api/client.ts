/**
 * Minimal typed API client. Talks to the same-origin `/api/*` proxy (see
 * next.config.ts), so session/CSRF cookies are first-party. Response shapes are
 * sourced from the backend's OpenAPI schema (generated; drift-guarded in CI).
 */
import type { components } from "./schema";

export type User = components["schemas"]["UserOut"];
export type Instrument = components["schemas"]["InstrumentOut"];
export type Bar = components["schemas"]["BarOut"];
export type Quote = components["schemas"]["QuoteOut"];
export type PaperSession = components["schemas"]["PaperSessionOut"];
export type Strategy = components["schemas"]["StrategyOut"];
export type StrategyDetail = components["schemas"]["StrategyDetailOut"];
export type BacktestSummary = components["schemas"]["BacktestSummaryOut"];
export type Backtest = components["schemas"]["BacktestOut"];
export type IndicatorSeries = components["schemas"]["IndicatorSeriesOut"];
export type Signal = components["schemas"]["SignalOut"];
export type Alert = components["schemas"]["AlertOut"];
export type PositionSizeRequest = components["schemas"]["PositionSizeRequest"];
export type PositionSizeResult = components["schemas"]["PositionSizeOut"];
/** The canonical StrategySpec DSL (built client-side, sent as a JSON query param). */
export type StrategySpec = components["schemas"]["StrategySpec-Input"];
export type IndicatorSpec = components["schemas"]["IndicatorSpec"];

// Public (unauthenticated) per-ticker SEO surface.
export type PublicInstrumentSummary = components["schemas"]["PublicInstrumentSummary"];
export type PublicMarket = components["schemas"]["PublicMarketOut"];
export type PublicChartBar = components["schemas"]["PublicChartBar"];
export type PublicIndicatorSeries = components["schemas"]["PublicIndicatorSeries"];
export type PublicReferenceSummary = components["schemas"]["PublicReferenceSummary"];
export type PublicTrackRecord = components["schemas"]["PublicTrackRecordOut"];
export type PublicTrackRecordComponent = components["schemas"]["PublicTrackRecordComponent"];

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Base for the PUBLIC, unauthenticated endpoints (`/public/markets…`).
 *
 * These are called from server components (the SEO pages) as well as, potentially,
 * the browser. In the browser we go through the same-origin `/api` rewrite. On the
 * server there is no origin to resolve a relative `/api/*` against, so we hit the
 * backend directly at `API_PROXY_TARGET` (the same target next.config uses for the
 * `/api/*` rewrite) — the backend serves the public router at `/public/markets`
 * with no `/api` prefix.
 */
function publicBase(): string {
  if (typeof window === "undefined") {
    const target = process.env.API_PROXY_TARGET ?? "http://localhost:8080";
    return target.replace(/\/$/, "");
  }
  return BASE;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (UNSAFE.has(method)) {
    const csrf = readCookie("csrf_token");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const res = await fetch(`${BASE}${path}`, { ...init, method, headers, credentials: "include" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch a PUBLIC endpoint, origin-resolved for server vs. browser (see `publicBase`). */
async function publicFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const res = await fetch(`${publicBase()}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  csrf: () => apiFetch<{ csrf_token: string }>("/auth/csrf"),
  me: () => apiFetch<User>("/auth/me"),
  login: (email: string, password: string) =>
    apiFetch<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, display_name: string | null) =>
    apiFetch<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    }),
  logout: () => apiFetch<{ status: string }>("/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    apiFetch<{ status: string }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  deleteAccount: (password: string) =>
    apiFetch<{ status: string }>("/auth/delete", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  passwordReset: (email: string) =>
    apiFetch<{ status: string }>("/auth/password-reset", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  passwordResetConfirm: (token: string, new_password: string) =>
    apiFetch<{ status: string }>("/auth/password-reset-confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),

  instruments: (assetClass?: string) =>
    apiFetch<Instrument[]>(
      `/market/instruments${assetClass ? `?asset_class=${assetClass}` : ""}`,
    ),
  bars: (id: string, timeframe: string, start?: string, end?: string) => {
    const params = new URLSearchParams({ timeframe });
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    return apiFetch<Bar[]>(`/market/instruments/${id}/bars?${params.toString()}`);
  },
  latest: (id: string) => apiFetch<Quote>(`/market/instruments/${id}/latest`),
  /**
   * Compute indicator series over an instrument's bars (auth-gated). `specs` is a
   * list of IndicatorSpec; it is JSON-encoded into the `spec` query param, matching
   * the backend contract. NaN warm-up points come back as `null`.
   */
  indicators: (id: string, specs: IndicatorSpec[], timeframe: string) => {
    const params = new URLSearchParams({ spec: JSON.stringify(specs), timeframe });
    return apiFetch<IndicatorSeries[]>(`/market/instruments/${id}/indicators?${params.toString()}`);
  },
  /**
   * Evaluate a StrategySpec's entry rule on the latest CLOSED bar (auth-gated).
   * Returns real engine math (entry/stop/target/size). `size` is present only when
   * `equity` is supplied; `size_per_10k` is always present so the client never does
   * money math. The result is an INTENDED order — live trading stays gated.
   */
  signal: (id: string, spec: StrategySpec, equity?: string) => {
    const params = new URLSearchParams({ spec: JSON.stringify(spec) });
    if (equity) params.set("equity", equity);
    return apiFetch<Signal>(`/market/instruments/${id}/signal?${params.toString()}`);
  },
  wsTicket: () =>
    apiFetch<{ ticket: string; expires_in: number }>("/market/ws-ticket", { method: "POST" }),

  paperSessions: () => apiFetch<PaperSession[]>("/paper/sessions"),

  /**
   * Position-sizing GUIDANCE from the engine's own `_size()` math (invariant #4).
   * Money comes back as Decimal strings computed server-side (invariant #2) — the
   * client never does money math. The result is NOT an executable order (live
   * trading is gated; POST /live/orders → 403).
   */
  positionSize: (req: PositionSizeRequest) =>
    apiFetch<PositionSizeResult>("/calc/position-size", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  /** The signed-in user's recent paper-trading alert feed (newest first). */
  alerts: () => apiFetch<Alert[]>("/alerts"),

  strategies: () => apiFetch<Strategy[]>("/strategies"),
  createStrategy: (spec: unknown) =>
    apiFetch<StrategyDetail>("/strategies", { method: "POST", body: JSON.stringify(spec) }),
  aiStrategy: (prompt: string) =>
    apiFetch<{ spec: unknown; provider: string }>("/ai/strategy", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  deployPaper: (strategyId: string) =>
    apiFetch<PaperSession>("/paper/deploy", {
      method: "POST",
      body: JSON.stringify({ strategy_id: strategyId }),
    }),
  backtests: () => apiFetch<BacktestSummary[]>("/backtests"),
  backtest: (id: string) => apiFetch<Backtest>(`/backtests/${id}`),
  createBacktest: (strategyId: string, start: string, end: string) =>
    apiFetch<Backtest>("/backtests", {
      method: "POST",
      body: JSON.stringify({ strategy_id: strategyId, start, end }),
    }),
  aiExplain: (context: Record<string, unknown>) =>
    apiFetch<{ text: string; provider: string }>("/ai/explain", {
      method: "POST",
      body: JSON.stringify({ context }),
    }),

  // --- Public (unauthenticated) per-ticker SEO surface ---
  /** Catalog of tickers available on the public pages (used by the sitemap). */
  publicMarkets: (init?: RequestInit) =>
    publicFetch<PublicInstrumentSummary[]>("/public/markets", init),
  /** Full per-ticker bundle: meta + delayed price + real indicators + reference backtest. */
  publicMarket: (ticker: string, init?: RequestInit) =>
    publicFetch<PublicMarket>(`/public/markets/${encodeURIComponent(ticker)}`, init),
  /** OHLCV history for the public chart. */
  publicBars: (ticker: string, timeframe: string, init?: RequestInit) =>
    publicFetch<PublicChartBar[]>(
      `/public/markets/${encodeURIComponent(ticker)}/bars?timeframe=${encodeURIComponent(timeframe)}`,
      init,
    ),
  /** Curated, caveated aggregate reference backtest across the universe (landing page). */
  publicTrackRecord: (init?: RequestInit) =>
    publicFetch<PublicTrackRecord>("/public/track-record", init),
};




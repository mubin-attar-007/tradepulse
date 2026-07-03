import type { IndicatorSpec } from "@/lib/api/client";

/**
 * The catalog of indicators the on-chart panel can toggle. Each entry knows how it
 * renders (an `overlay` shares the price pane; an `oscillator` gets its own stacked
 * pane below) and the concrete `IndicatorSpec` sent to the backend, which computes
 * the values with the SAME causal math the backtest engine uses (no client-side
 * indicator math — invariant #4).
 */
export type IndicatorKind = "EMA" | "SMA" | "RSI" | "ATR" | "BBANDS" | "MACD" | "VWAP";

export type IndicatorPlacement = "overlay" | "oscillator";

export type IndicatorDef = {
  kind: IndicatorKind;
  label: string;
  placement: IndicatorPlacement;
  /** The spec sent to `/market/instruments/{id}/indicators`. */
  spec: IndicatorSpec;
};

export const INDICATOR_CATALOG: IndicatorDef[] = [
  {
    kind: "EMA",
    label: "EMA 20",
    placement: "overlay",
    spec: { id: "ema", type: "EMA", params: { period: 20 } },
  },
  {
    kind: "SMA",
    label: "SMA 20",
    placement: "overlay",
    spec: { id: "sma", type: "SMA", params: { period: 20 } },
  },
  {
    kind: "VWAP",
    label: "VWAP",
    placement: "overlay",
    spec: { id: "vwap", type: "VWAP", params: {} },
  },
  {
    kind: "BBANDS",
    label: "Bollinger 20/2",
    placement: "overlay",
    spec: { id: "bb", type: "BBANDS", params: { period: 20, std: 2 } },
  },
  {
    kind: "RSI",
    label: "RSI 14",
    placement: "oscillator",
    spec: { id: "rsi", type: "RSI", params: { period: 14 } },
  },
  {
    kind: "ATR",
    label: "ATR 14",
    placement: "oscillator",
    spec: { id: "atr", type: "ATR", params: { period: 14 } },
  },
  {
    kind: "MACD",
    label: "MACD 12/26/9",
    placement: "oscillator",
    spec: { id: "macd", type: "MACD", params: { fast: 12, slow: 26, signal: 9 } },
  },
];

export const INDICATOR_BY_KIND: Record<IndicatorKind, IndicatorDef> = Object.fromEntries(
  INDICATOR_CATALOG.map((d) => [d.kind, d]),
) as Record<IndicatorKind, IndicatorDef>;

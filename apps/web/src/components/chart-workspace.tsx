"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CandlestickSeries,
  createChart,
  LineSeries,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

import { DataBadge } from "@/components/data-badge";
import { IndicatorPanel } from "@/components/indicator-panel";
import { SignalCard } from "@/components/signal-card";
import { api, type Bar, type IndicatorSeries, type StrategySpec } from "@/lib/api/client";
import { attachOhlcLegend } from "@/lib/chart-legend";
import { indicatorColor, onThemeChange, readChartTheme, type ChartTheme } from "@/lib/chart-theme";
import { INDICATOR_BY_KIND, type IndicatorKind } from "@/lib/indicators";
import { type LiveBar, useMarketSocket } from "@/lib/market/use-market-socket";

const TIMEFRAME = "1m";

function toTime(iso: string): UTCTimestamp {
  return Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;
}

function barToCandle(bar: Bar): CandlestickData {
  return {
    time: toTime(bar.ts),
    open: Number(bar.open),
    high: Number(bar.high),
    low: Number(bar.low),
    close: Number(bar.close),
  };
}

/** One indicator series -> lightweight-charts LineData, dropping warm-up nulls. */
function toLineData(series: IndicatorSeries): LineData[] {
  const out: LineData[] = [];
  for (let i = 0; i < series.ts.length; i++) {
    const v = series.values[i];
    if (v == null) continue; // honest gap during warm-up (invariant #4)
    out.push({ time: toTime(series.ts[i]), value: v });
  }
  return out;
}

/**
 * An example StrategySpec so the signal card has something to evaluate on the chart
 * view. It is the same canonical reference (SMA 10/30 crossover) the backtest engine
 * runs — real math, honestly caveated by SignalCard as a non-executable illustration.
 */
function referenceSpec(symbol: string): StrategySpec {
  return {
    spec_version: "1.0",
    name: "SMA 10/30 crossover",
    universe: [symbol],
    timeframe: "1h",
    indicators: [
      { id: "sma_fast", type: "SMA", params: { period: 10 } },
      { id: "sma_slow", type: "SMA", params: { period: 30 } },
    ],
    entry_long: {
      type: "compare",
      left: { kind: "indicator", ref: "sma_fast", multiplier: 1, offset: 0 },
      op: "cross_above",
      right: { kind: "indicator", ref: "sma_slow", multiplier: 1, offset: 0 },
    },
    exit: {
      stop_loss_pct: 0.05,
      take_profit_pct: 0.1,
      exit_conditions: {
        type: "compare",
        left: { kind: "indicator", ref: "sma_fast", multiplier: 1, offset: 0 },
        op: "cross_below",
        right: { kind: "indicator", ref: "sma_slow", multiplier: 1, offset: 0 },
      },
    },
    sizing: { method: "percent_equity", value: 0.2 },
    risk: { max_position_pct: 0.2, max_open_positions: 1 },
  };
}

export function ChartWorkspace({ instrumentId }: { instrumentId: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const legendApiRef = useRef<ReturnType<typeof attachOhlcLegend> | null>(null);
  // Active line series keyed by indicator series key (`<id>` or `<id>:<output>`).
  const lineRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());

  const [active, setActive] = useState<Set<IndicatorKind>>(new Set());

  const { data: instruments } = useQuery({ queryKey: ["instruments"], queryFn: () => api.instruments() });
  const instrument = instruments?.find((i) => i.id === instrumentId);

  const { data: bars, isLoading } = useQuery({
    queryKey: ["bars", instrumentId],
    queryFn: () => api.bars(instrumentId, TIMEFRAME),
  });

  // Specs for the currently-active indicators (stable ref for the query key).
  const activeDefs = useMemo(
    () => [...active].map((kind) => INDICATOR_BY_KIND[kind]),
    [active],
  );
  const activeSpecs = useMemo(() => activeDefs.map((d) => d.spec), [activeDefs]);

  const { data: indicatorSeries } = useQuery({
    queryKey: ["indicators", instrumentId, activeSpecs.map((s) => s.id).sort()],
    queryFn: () => api.indicators(instrumentId, activeSpecs, TIMEFRAME),
    enabled: activeSpecs.length > 0,
  });

  function toggle(kind: IndicatorKind) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  // Create the chart once; recolor in place when the theme class on <html> flips.
  useEffect(() => {
    if (!containerRef.current) return;
    const layoutOptions = (theme: ChartTheme) => ({
      layout: { background: { color: "transparent" }, textColor: theme.text },
      grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
      rightPriceScale: { borderColor: theme.border },
    });
    const candleOptions = (theme: ChartTheme) => ({
      upColor: theme.up,
      downColor: theme.down,
      borderVisible: false,
      wickUpColor: theme.up,
      wickDownColor: theme.down,
    });
    const theme = readChartTheme();
    const chart: IChartApi = createChart(containerRef.current, {
      autoSize: true,
      timeScale: { timeVisible: true, secondsVisible: false },
      ...layoutOptions(theme),
    });
    const series = chart.addSeries(CandlestickSeries, candleOptions(theme));
    chartRef.current = chart;
    seriesRef.current = series;
    if (legendRef.current) {
      legendApiRef.current = attachOhlcLegend(chart, series, legendRef.current);
    }
    const lines = lineRef.current; // captured for the cleanup closure
    const unsubscribe = onThemeChange(() => {
      const next = readChartTheme();
      chart.applyOptions(layoutOptions(next));
      series.applyOptions(candleOptions(next));
    });
    return () => {
      unsubscribe();
      legendApiRef.current?.dispose();
      legendApiRef.current = null;
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      lines.clear();
    };
  }, []);

  // Load history.
  useEffect(() => {
    if (seriesRef.current && bars) {
      const candles = bars.map(barToCandle);
      seriesRef.current.setData(candles);
      legendApiRef.current?.setLatest(candles.at(-1) ?? null);
    }
  }, [bars]);

  // Reconcile indicator line series with the active toggles + fetched data.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const lines = lineRef.current;
    const incoming = indicatorSeries ?? [];
    const wanted = new Set(incoming.map((s) => s.key));

    // Remove series that are no longer active.
    for (const [key, s] of lines) {
      if (!wanted.has(key)) {
        chart.removeSeries(s);
        lines.delete(key);
      }
    }

    // Oscillators each get their own stacked pane (index 1, 2, …); overlays share
    // the price pane (index 0). Assign pane indices deterministically by order.
    let nextPane = 1;
    const paneFor = new Map<IndicatorKind, number>();
    for (const def of activeDefs) {
      if (def.placement === "oscillator") paneFor.set(def.kind, nextPane++);
    }

    for (const series of incoming) {
      const def = INDICATOR_BY_KIND[series.type as IndicatorKind];
      if (!def) continue;
      const paneIndex = def.placement === "oscillator" ? (paneFor.get(def.kind) ?? 1) : 0;
      const color = indicatorColor(series.type, series.output);
      let line = lines.get(series.key);
      if (!line) {
        line = chart.addSeries(LineSeries, { color, lineWidth: 2, priceLineVisible: false }, paneIndex);
        lines.set(series.key, line);
      } else {
        line.applyOptions({ color });
      }
      line.setData(toLineData(series));
    }
  }, [indicatorSeries, activeDefs]);

  // Live append (display-only floats; money precision lives server-side).
  useMarketSocket(instrumentId, (bar: LiveBar) => {
    const candle = {
      time: toTime(bar.ts),
      open: Number(bar.open ?? bar.close),
      high: Number(bar.high ?? bar.close),
      low: Number(bar.low ?? bar.close),
      close: Number(bar.close),
    };
    seriesRef.current?.update(candle);
    legendApiRef.current?.setLatest(candle);
  });

  const spec = useMemo(
    () => (instrument ? referenceSpec(instrument.symbol) : null),
    [instrument],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">{instrument?.symbol ?? "Chart"}</h1>
        <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
          {instrument?.name ? `${instrument.name} · ` : ""}1m{isLoading ? " · loading…" : ""}
          <DataBadge kind="DELAYED" title="Polled market data — delayed, not a live SIP feed." />
        </span>
      </div>
      <div className="relative">
        <div
          ref={containerRef}
          className="h-[420px] w-full rounded-lg border border-border bg-card sm:h-[480px] md:h-[560px]"
        />
        <div
          ref={legendRef}
          aria-hidden
          className="pointer-events-none absolute left-3 top-3 z-10 rounded-md border border-border/60 bg-background/70 px-2.5 py-1 font-mono text-xs tabular-nums text-foreground backdrop-blur empty:hidden"
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <IndicatorPanel active={active} onToggle={toggle} />
        {spec ? <SignalCard instrumentId={instrumentId} spec={spec} /> : null}
      </div>
    </div>
  );
}

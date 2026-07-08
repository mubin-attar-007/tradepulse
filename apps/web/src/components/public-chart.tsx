"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CandlestickSeries,
  createChart,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { api, type PublicChartBar } from "@/lib/api/client";
import { attachOhlcLegend } from "@/lib/chart-legend";
import { onThemeChange, readChartTheme, type ChartTheme } from "@/lib/chart-theme";

function toTime(iso: string): UTCTimestamp {
  return Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;
}

function barToCandle(bar: PublicChartBar): CandlestickData {
  return {
    time: toTime(bar.ts),
    open: Number(bar.open),
    high: Number(bar.high),
    low: Number(bar.low),
    close: Number(bar.close),
  };
}

/**
 * Read-only candlestick chart for the PUBLIC per-ticker pages. Unlike
 * ChartWorkspace it takes a slug (not an instrument id), fetches delayed OHLCV via
 * the public API, and has NO live WebSocket append — public data is delayed.
 */
export function PublicChart({ slug, timeframe }: { slug: string; timeframe: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const legendApiRef = useRef<ReturnType<typeof attachOhlcLegend> | null>(null);

  const { data: bars, isLoading } = useQuery({
    queryKey: ["public-bars", slug, timeframe],
    queryFn: () => api.publicBars(slug, timeframe),
  });

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
    seriesRef.current = series;
    if (legendRef.current) {
      legendApiRef.current = attachOhlcLegend(chart, series, legendRef.current);
    }
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
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (seriesRef.current && bars) {
      const candles = bars.map(barToCandle);
      seriesRef.current.setData(candles);
      seriesRef.current.priceScale().applyOptions({});
      legendApiRef.current?.setLatest(candles.at(-1) ?? null);
    }
  }, [bars]);

  const empty = !isLoading && (!bars || bars.length === 0);

  return (
    <div className="relative">
      <div
        ref={containerRef}
        className="h-[380px] w-full rounded-lg border border-border bg-card sm:h-[440px]"
      />
      <div
        ref={legendRef}
        aria-hidden
        className="pointer-events-none absolute left-3 top-3 z-10 rounded-md border border-border/60 bg-background/70 px-2.5 py-1 font-mono text-xs tabular-nums text-foreground backdrop-blur empty:hidden"
      />
      {(isLoading || empty) && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">
          {isLoading ? "Loading chart…" : "No recent bars available for this market yet."}
        </div>
      )}
    </div>
  );
}

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

import { api, type Bar } from "@/lib/api/client";
import { type LiveBar, useMarketSocket } from "@/lib/market/use-market-socket";

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

export function ChartWorkspace({ instrumentId }: { instrumentId: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const { data: instruments } = useQuery({ queryKey: ["instruments"], queryFn: () => api.instruments() });
  const instrument = instruments?.find((i) => i.id === instrumentId);

  const { data: bars, isLoading } = useQuery({
    queryKey: ["bars", instrumentId],
    queryFn: () => api.bars(instrumentId, "1m"),
  });

  // Create the chart once.
  useEffect(() => {
    if (!containerRef.current) return;
    const chart: IChartApi = createChart(containerRef.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: "#8b949e" },
      grid: { vertLines: { color: "#1a212b" }, horzLines: { color: "#1a212b" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: "#232a34" },
    });
    seriesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: "#16c784",
      downColor: "#ea3943",
      borderVisible: false,
      wickUpColor: "#16c784",
      wickDownColor: "#ea3943",
    });
    return () => {
      chart.remove();
      seriesRef.current = null;
    };
  }, []);

  // Load history.
  useEffect(() => {
    if (seriesRef.current && bars) {
      seriesRef.current.setData(bars.map(barToCandle));
    }
  }, [bars]);

  // Live append (display-only floats; money precision lives server-side).
  useMarketSocket(instrumentId, (bar: LiveBar) => {
    seriesRef.current?.update({
      time: toTime(bar.ts),
      open: Number(bar.open ?? bar.close),
      high: Number(bar.high ?? bar.close),
      low: Number(bar.low ?? bar.close),
      close: Number(bar.close),
    });
  });

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">{instrument?.symbol ?? "Chart"}</h1>
        <span className="text-sm text-muted-foreground">
          {instrument?.name ? `${instrument.name} · ` : ""}1m{isLoading ? " · loading…" : ""}
        </span>
      </div>
      <div ref={containerRef} className="h-[520px] w-full rounded-lg border border-border bg-card" />
    </div>
  );
}

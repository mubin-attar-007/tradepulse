"use client";

import { createChart, LineSeries, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api/client";

type Trade = {
  entry_ts: string;
  exit_ts: string;
  pnl: string;
  return_pct: number;
  exit_reason: string;
};
type ResultDict = {
  final_equity?: string;
  initial_cash?: string;
  num_trades?: number;
  metrics?: Record<string, number>;
  equity_curve?: { ts: string; equity: string }[];
  trades?: Trade[];
};

const METRICS: [string, string][] = [
  ["total_return", "Return"],
  ["cagr", "CAGR"],
  ["sharpe", "Sharpe"],
  ["sortino", "Sortino"],
  ["max_drawdown", "Max DD"],
  ["win_rate", "Win rate"],
  ["profit_factor", "Profit factor"],
  ["num_trades", "Trades"],
];
const PCT = new Set(["total_return", "cagr", "max_drawdown", "win_rate"]);

function fmtMetric(key: string, value: number): string {
  if (PCT.has(key)) return `${(value * 100).toFixed(2)}%`;
  if (key === "num_trades") return String(value);
  return value.toFixed(2);
}

export function BacktestResults({ result: raw }: { result: Record<string, unknown> }) {
  const result = raw as unknown as ResultDict;
  const ref = useRef<HTMLDivElement>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [loadingExplain, setLoadingExplain] = useState(false);

  useEffect(() => {
    if (!ref.current || !result.equity_curve?.length) return;
    const chart: IChartApi = createChart(ref.current, {
      autoSize: true,
      layout: { background: { color: "transparent" }, textColor: "#8b949e" },
      grid: { vertLines: { color: "#1a212b" }, horzLines: { color: "#1a212b" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: "#232a34" },
    });
    const series = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 2 });
    series.setData(
      result.equity_curve.map((p) => ({
        time: Math.floor(Date.parse(p.ts) / 1000) as UTCTimestamp,
        value: Number(p.equity),
      })),
    );
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [result]);

  async function explain() {
    setLoadingExplain(true);
    setExplanation(null);
    try {
      const resp = await api.aiExplain({
        metrics: result.metrics,
        num_trades: result.num_trades,
        final_equity: result.final_equity,
        initial_cash: result.initial_cash,
      });
      setExplanation(resp.text);
    } catch (err) {
      setExplanation(err instanceof ApiError ? `AI unavailable: ${err.message}` : "AI unavailable.");
    } finally {
      setLoadingExplain(false);
    }
  }

  const metrics = result.metrics ?? {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {METRICS.filter(([k]) => k in metrics).map(([key, label]) => (
          <div key={key} className="rounded-lg border border-border bg-card p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
            <div className="mt-1 text-lg font-semibold tabular-nums">
              {fmtMetric(key, metrics[key])}
            </div>
          </div>
        ))}
      </div>

      <div ref={ref} className="h-[360px] w-full rounded-lg border border-border bg-card" />

      <div>
        <Button variant="outline" size="sm" onClick={explain} disabled={loadingExplain}>
          {loadingExplain ? "Asking AI…" : "Explain with AI"}
        </Button>
        {explanation ? (
          <div className="mt-3 whitespace-pre-wrap rounded-lg border border-border bg-card p-4 text-sm">
            {explanation}
          </div>
        ) : null}
      </div>

      {result.trades?.length ? (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-card text-left text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Entry</th>
                <th className="px-3 py-2 font-medium">Exit</th>
                <th className="px-3 py-2 text-right font-medium">P&amp;L</th>
                <th className="px-3 py-2 text-right font-medium">Return</th>
                <th className="px-3 py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {[...result.trades]
                .slice(-25)
                .reverse()
                .map((t) => (
                  <tr key={`${t.entry_ts}-${t.exit_ts}`} className="border-t border-border">
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {t.entry_ts.replace("T", " ").slice(0, 16)}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {t.exit_ts.replace("T", " ").slice(0, 16)}
                    </td>
                    <td
                      className={`px-3 py-1.5 text-right tabular-nums ${
                        Number(t.pnl) >= 0 ? "text-profit" : "text-loss"
                      }`}
                    >
                      {Number(t.pnl).toFixed(2)}
                    </td>
                    <td
                      className={`px-3 py-1.5 text-right tabular-nums ${
                        t.return_pct >= 0 ? "text-profit" : "text-loss"
                      }`}
                    >
                      {(t.return_pct * 100).toFixed(2)}%
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">{t.exit_reason}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

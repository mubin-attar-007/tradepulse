"use client";

import {
  AreaSeries,
  createChart,
  LineSeries,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { HypotheticalBanner } from "@/components/hypothetical-banner";
import { api, ApiError } from "@/lib/api/client";
import { onThemeChange, readChartTheme, type ChartTheme } from "@/lib/chart-theme";
import { formatSigned } from "@/lib/utils";

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
  total_commission?: string;
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

const LOSS = "#ff5a6a";

function fmtMetric(key: string, value: number): string {
  if (PCT.has(key)) return `${(value * 100).toFixed(2)}%`;
  if (key === "num_trades") return String(value);
  return value.toFixed(2);
}

/** Underwater drawdown series (percent, <= 0) derived from the equity curve. */
function drawdownSeries(curve: { ts: string; equity: string }[]) {
  let peak = -Infinity;
  return curve.map((p) => {
    const eq = Number(p.equity);
    if (eq > peak) peak = eq;
    const dd = peak > 0 ? (eq / peak - 1) * 100 : 0;
    return { time: Math.floor(Date.parse(p.ts) / 1000) as UTCTimestamp, value: dd };
  });
}

function exportTradesCsv(trades: Trade[]) {
  const header = "entry_ts,exit_ts,pnl,return_pct,exit_reason";
  const rows = trades.map((t) =>
    [
      t.entry_ts,
      t.exit_ts,
      t.pnl,
      t.return_pct,
      `"${(t.exit_reason ?? "").replace(/"/g, '""')}"`,
    ].join(","),
  );
  const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "tradepulse-backtest-trades.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function BacktestResults({ result: raw }: { result: Record<string, unknown> }) {
  const result = raw as unknown as ResultDict;
  const equityRef = useRef<HTMLDivElement>(null);
  const ddRef = useRef<HTMLDivElement>(null);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [loadingExplain, setLoadingExplain] = useState(false);

  useEffect(() => {
    const curve = result.equity_curve;
    const equityEl = equityRef.current;
    const ddEl = ddRef.current;
    if (!curve?.length || !equityEl || !ddEl) return;

    const layoutOptions = (theme: ChartTheme) => ({
      layout: { background: { color: "transparent" }, textColor: theme.text },
      grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
      rightPriceScale: { borderColor: theme.border },
    });
    const timeScale = { timeVisible: true, secondsVisible: false } as const;
    const theme = readChartTheme();

    const equityChart: IChartApi = createChart(equityEl, {
      autoSize: true,
      timeScale,
      ...layoutOptions(theme),
    });
    const equitySeries = equityChart.addSeries(LineSeries, { color: theme.line, lineWidth: 2 });
    equitySeries.setData(
      curve.map((p) => ({
        time: Math.floor(Date.parse(p.ts) / 1000) as UTCTimestamp,
        value: Number(p.equity),
      })),
    );
    equityChart.timeScale().fitContent();

    const ddChart: IChartApi = createChart(ddEl, {
      autoSize: true,
      timeScale,
      ...layoutOptions(theme),
    });
    const ddSeries = ddChart.addSeries(AreaSeries, {
      lineColor: LOSS,
      topColor: "rgba(255,90,106,0.05)",
      bottomColor: "rgba(255,90,106,0.45)",
      lineWidth: 2,
      priceFormat: { type: "price", precision: 1, minMove: 0.1 },
    });
    ddSeries.setData(drawdownSeries(curve));
    ddChart.timeScale().fitContent();

    const unsubscribe = onThemeChange(() => {
      const next = readChartTheme();
      equityChart.applyOptions(layoutOptions(next));
      equitySeries.applyOptions({ color: next.line });
      ddChart.applyOptions(layoutOptions(next));
    });
    return () => {
      unsubscribe();
      equityChart.remove();
      ddChart.remove();
    };
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
  const trades = result.trades ?? [];
  return (
    <div className="space-y-4">
      <HypotheticalBanner />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {METRICS.filter(([k]) => k in metrics).map(([key, label]) => (
          <div key={key} className="rounded-lg border border-border bg-card p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
            <div className="mt-1 text-lg font-semibold tabular-nums">
              {fmtMetric(key, metrics[key])}
            </div>
          </div>
        ))}
        {result.total_commission != null ? (
          <div className="rounded-lg border border-border bg-card p-3">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">Fees paid</div>
            <div className="mt-1 text-lg font-semibold tabular-nums">
              $
              {Number(result.total_commission).toLocaleString(undefined, {
                maximumFractionDigits: 2,
              })}
            </div>
          </div>
        ) : null}
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Returns are net of modeled costs — commission 2&nbsp;bps/side + slippage 1&nbsp;bps. Sharpe
        &amp; Sortino are annualized with a risk-free rate of 0.
      </p>

      <div className="space-y-1">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Equity curve</div>
        <div
          ref={equityRef}
          className="h-[240px] w-full rounded-lg border border-border bg-card md:h-[320px]"
        />
      </div>

      <div className="space-y-1">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          Underwater drawdown (%)
        </div>
        <div
          ref={ddRef}
          className="h-[140px] w-full rounded-lg border border-border bg-card"
        />
      </div>

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

      {trades.length ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              Trades{" "}
              <span className="tabular-nums text-foreground">({trades.length})</span>
              {trades.length > 25 ? (
                <span className="text-muted-foreground"> · showing last 25</span>
              ) : null}
            </h2>
            <Button variant="outline" size="sm" onClick={() => exportTradesCsv(trades)}>
              Export CSV
            </Button>
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
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
                {[...trades]
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
                        {formatSigned(Number(t.pnl))}
                      </td>
                      <td
                        className={`px-3 py-1.5 text-right tabular-nums ${
                          t.return_pct >= 0 ? "text-profit" : "text-loss"
                        }`}
                      >
                        {formatSigned(t.return_pct * 100, "%")}
                      </td>
                      <td className="px-3 py-1.5 text-muted-foreground">{t.exit_reason}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}

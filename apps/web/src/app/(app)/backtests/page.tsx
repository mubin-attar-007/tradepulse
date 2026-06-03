"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { BacktestResults } from "@/components/backtest-results";
import { Button } from "@/components/ui/button";
import { api, ApiError, type Backtest } from "@/lib/api/client";

function localInput(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 86_400_000).toISOString().slice(0, 16);
}

export default function BacktestsPage() {
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: () => api.strategies() });
  const { data: history, refetch } = useQuery({
    queryKey: ["backtests"],
    queryFn: () => api.backtests(),
  });

  const [strategyId, setStrategyId] = useState("");
  const [start, setStart] = useState(localInput(2));
  const [end, setEnd] = useState(localInput(0));
  const [current, setCurrent] = useState<Backtest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    if (!strategyId) {
      setError("Pick a strategy first.");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const bt = await api.createBacktest(
        strategyId,
        new Date(start).toISOString(),
        new Date(end).toISOString(),
      );
      setCurrent(bt);
      if (bt.status === "failed") setError(bt.error ?? "Backtest failed.");
      await refetch();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to run backtest.");
    } finally {
      setRunning(false);
    }
  }

  const result = current?.result ?? null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Backtests</h1>

      <div className="space-y-3 rounded-lg border border-border bg-card p-4">
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="space-y-1 text-sm sm:col-span-2">
            Strategy
            <select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
            >
              <option value="">Select…</option>
              {(strategies ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            Start
            <input
              type="datetime-local"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
            />
          </label>
          <label className="space-y-1 text-sm">
            End
            <input
              type="datetime-local"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
            />
          </label>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={run} disabled={running}>
            {running ? "Running…" : "Run backtest"}
          </Button>
          {error ? <span className="text-sm text-loss">{error}</span> : null}
          {!strategies?.length ? (
            <span className="text-sm text-muted-foreground">
              No strategies yet — create one via <code>POST /strategies</code> or{" "}
              <code>/ai/strategy</code>.
            </span>
          ) : null}
        </div>
      </div>

      {result ? <BacktestResults result={result} /> : null}

      {history?.length ? (
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Recent runs</h2>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-card text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Symbol</th>
                  <th className="px-3 py-2 font-medium">Timeframe</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {history.map((b) => (
                  <tr key={b.id} className="border-t border-border">
                    <td className="px-3 py-1.5 tabular-nums">{b.symbol}</td>
                    <td className="px-3 py-1.5 text-muted-foreground">{b.timeframe}</td>
                    <td className="px-3 py-1.5">{b.status}</td>
                    <td className="px-3 py-1.5 text-right">
                      <button
                        type="button"
                        onClick={async () => setCurrent(await api.backtest(b.id))}
                        className="text-primary hover:underline"
                      >
                        View
                      </button>
                    </td>
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

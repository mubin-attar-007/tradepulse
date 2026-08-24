"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState, useSyncExternalStore } from "react";

import { BacktestResults } from "@/components/backtest-results";
import { QueryError } from "@/components/query-error";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type Backtest } from "@/lib/api/client";

const pad = (n: number): string => String(n).padStart(2, "0");

/**
 * Format a Date as the LOCAL wall-clock string `<input type="datetime-local">` expects.
 *
 * `toISOString().slice(0,16)` looks like the same thing and is not: it renders UTC, but
 * the input reads it as local time, so the whole default window silently slid by the
 * user's offset — at UTC+05:30 the default `end` landed five and a half hours in the
 * FUTURE and the most recent bars fell outside every default run. Building the string
 * from local components keeps what the user sees and what we send in agreement.
 */
function toLocalInput(d: Date): string {
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

const DEFAULT_WINDOW_DAYS = 2;
/** Nothing to subscribe to: the snapshot differs between server and client, never over time. */
const subscribeNothing = () => () => {};

export function BacktestsView() {
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: () => api.strategies() });
  const {
    data: history,
    isError: historyFailed,
    error: historyError,
    refetch,
  } = useQuery({
    queryKey: ["backtests"],
    queryFn: () => api.backtests(),
  });
  const { toast } = useToast();

  const [strategyId, setStrategyId] = useState("");
  // Only the BROWSER may produce one of these strings. `toLocalInput()` reads a local
  // wall-clock, and this is a client component rendered by a server page: seeding state with
  // it inline bakes the SERVER's clock and offset into the initial HTML — which is the exact
  // skew `toLocalInput` exists to remove, and it hydration-mismatches the instant the browser
  // re-renders with its own offset. `useSyncExternalStore` is how you read a client-only fact
  // honestly: `false` in the server snapshot, `true` once hydrated, no mismatch either way.
  const hydrated = useSyncExternalStore(
    subscribeNothing,
    () => true,
    () => false,
  );
  // Derived, not stored, so the empty server render can never be mistaken for a real window.
  // `end` doubles as the `max` bound on both inputs; a run past "now" is clamped in `run()`
  // anyway, so the bound aging by a render costs nothing.
  const defaultWindow = useMemo(() => {
    if (!hydrated) return { start: "", end: "" };
    const now = new Date();
    return {
      start: toLocalInput(new Date(now.getTime() - DEFAULT_WINDOW_DAYS * 86_400_000)),
      end: toLocalInput(now),
    };
  }, [hydrated]);
  // `null` means "untouched, use the default"; anything else is the user's own edit.
  const [startEdit, setStartEdit] = useState<string | null>(null);
  const [endEdit, setEndEdit] = useState<string | null>(null);
  const start = startEdit ?? defaultWindow.start;
  const end = endEdit ?? defaultWindow.end;
  const [current, setCurrent] = useState<Backtest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    if (!strategyId) {
      setError("Pick a strategy first.");
      return;
    }
    const startAt = new Date(start);
    const endAt = new Date(end);
    if (Number.isNaN(startAt.getTime()) || Number.isNaN(endAt.getTime())) {
      setError("Enter a valid start and end date.");
      return;
    }
    if (startAt >= endAt) {
      setError("Start must be before end.");
      return;
    }
    // There are no bars from the future. Silently simulating over a window that runs past
    // "now" would report a shorter effective sample than the one the user asked for.
    const now = new Date();
    const effectiveEnd = endAt > now ? now : endAt;
    if (endAt > now) setEndEdit(toLocalInput(now));

    setRunning(true);
    setError(null);
    try {
      const bt = await api.createBacktest(
        strategyId,
        startAt.toISOString(),
        effectiveEnd.toISOString(),
      );
      setCurrent(bt);
      if (bt.status === "failed") {
        toast({ description: bt.error ?? "Backtest failed.", variant: "error" });
      }
      await refetch();
    } catch (err) {
      toast({
        description: err instanceof ApiError ? err.message : "Failed to run backtest.",
        variant: "error",
      });
    } finally {
      setRunning(false);
    }
  }

  const result = current?.result ?? null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Backtests</h1>
        <p className="text-sm text-muted-foreground">
          A historical simulation of one strategy over a window of stored bars, under the
          assumptions shown with the result. Hypothetical — it is not a forecast and not a return.
        </p>
      </div>

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
              max={end || undefined}
              onChange={(e) => setStartEdit(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
            />
          </label>
          <label className="space-y-1 text-sm">
            End
            <input
              type="datetime-local"
              value={end}
              max={defaultWindow.end || undefined}
              onChange={(e) => setEndEdit(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
            />
          </label>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={run} disabled={running || !start || !end}>
            {running ? "Running…" : "Run backtest"}
          </Button>
          {error ? <span className="text-sm text-loss">{error}</span> : null}
          {!strategies?.length ? (
            <span className="text-sm text-muted-foreground">
              No strategies yet —{" "}
              <Link href="/strategies" className="text-primary hover:underline">
                create one on the Strategies page
              </Link>
              .
            </span>
          ) : null}
        </div>
      </div>

      {result ? <BacktestResults result={result} /> : null}

      {historyFailed ? (
        <QueryError
          title="Couldn't load your previous runs"
          error={historyError}
          onRetry={() => void refetch()}
        />
      ) : history?.length ? (
        <div>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Recent runs</h2>
          <div className="overflow-x-auto rounded-lg border border-border">
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

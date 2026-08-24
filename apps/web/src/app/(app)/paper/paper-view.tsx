"use client";

import { useQuery } from "@tanstack/react-query";
import { PlayCircle } from "lucide-react";
import Link from "next/link";

import { DataBadge } from "@/components/data-badge";
import { HypotheticalBanner } from "@/components/hypothetical-banner";
import { QueryError } from "@/components/query-error";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { formatSigned } from "@/lib/utils";

type Snapshot = {
  final_equity?: string;
  num_trades?: number;
  metrics?: Record<string, number>;
} | null;

export function PaperView() {
  const {
    data: sessions,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["paper-sessions"],
    queryFn: () => api.paperSessions(),
  });

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Paper Trading</h1>
          <DataBadge kind="PAPER" title="Simulated ledger — no real orders, no real money." />
        </div>
        <p className="text-sm text-muted-foreground">
          Deployed strategies simulated against delayed bars on a virtual ledger. Every figure
          below is simulated; no order reaches a market.
        </p>
      </div>

      <HypotheticalBanner kind="paper" />

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : isError ? (
        /* A failed fetch is not "you have no sessions" — say which one it is. */
        <QueryError
          title="Couldn't load paper sessions"
          error={error}
          onRetry={() => void refetch()}
        />
      ) : !sessions?.length ? (
        <EmptyState
          icon={PlayCircle}
          title="No paper sessions yet"
          description="Deploy a strategy to simulate it against delayed bars on a virtual ledger."
          action={
            <Link href="/strategies" className="text-sm text-primary hover:underline">
              Go to strategies →
            </Link>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-card text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">Symbol</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 text-right font-medium">Simulated equity</th>
                <th className="px-4 py-2 text-right font-medium">Return</th>
                <th className="px-4 py-2 text-right font-medium">Trades</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session) => {
                const snap = session.snapshot as unknown as Snapshot;
                const ret = snap?.metrics?.total_return;
                return (
                  <tr key={session.id} className="border-t border-border">
                    <td className="px-4 py-2 font-medium tabular-nums">{session.symbol}</td>
                    <td className="px-4 py-2">
                      <span
                        className={session.status === "running" ? "text-profit" : "text-muted-foreground"}
                      >
                        {session.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {/* Display-only formatting of a server-computed Decimal string — the
                          value is never arithmetic'd here (invariant #2). */}
                      {snap?.final_equity
                        ? `$${Number(snap.final_equity).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                        : "—"}
                    </td>
                    <td
                      className={`px-4 py-2 text-right tabular-nums ${
                        ret === undefined ? "" : ret >= 0 ? "text-profit" : "text-loss"
                      }`}
                    >
                      {ret === undefined ? "—" : formatSigned(ret * 100, "%")}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums">{snap?.num_trades ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

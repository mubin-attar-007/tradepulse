"use client";

import { useQuery } from "@tanstack/react-query";
import { PlayCircle } from "lucide-react";
import Link from "next/link";

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
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["paper-sessions"],
    queryFn: () => api.paperSessions(),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Paper Trading</h1>
        <p className="text-sm text-muted-foreground">
          Deployed strategies running against live data on a virtual ledger.{" "}
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs uppercase">Paper</span>
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : !sessions?.length ? (
        <EmptyState
          icon={PlayCircle}
          title="No paper sessions yet"
          description="Deploy a strategy to trade live data on a virtual ledger."
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
                <th className="px-4 py-2 text-right font-medium">Equity</th>
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

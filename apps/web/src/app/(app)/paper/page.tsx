"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";

type Snapshot = {
  final_equity?: string;
  num_trades?: number;
  metrics?: Record<string, number>;
} | null;

export default function PaperPage() {
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
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !sessions?.length ? (
        <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          No paper sessions yet. Create a strategy (<code>POST /strategies</code>) and deploy it
          (<code>POST /paper/deploy</code>). The visual strategy builder + one-click deploy land in a
          later slice.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
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
                      {ret === undefined ? "—" : `${(ret * 100).toFixed(2)}%`}
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

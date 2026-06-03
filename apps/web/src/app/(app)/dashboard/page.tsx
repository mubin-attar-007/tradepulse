"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api/client";

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

export default function DashboardPage() {
  const { data: user, isLoading } = useQuery({ queryKey: ["me"], queryFn: api.me });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          {isLoading
            ? "Loading…"
            : `Welcome${user?.display_name ? `, ${user.display_name}` : ""}.`}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Portfolio Value" value="$0.00" hint="Paper · no positions yet" />
        <StatCard label="Open Positions" value="0" />
        <StatCard label="Strategies" value="0" hint="Builder arrives in Phase 4" />
        <StatCard label="Backtests" value="0" hint="Engine arrives in Phase 5" />
      </div>
      <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
        Foundation ready. Market data, charts, the strategy builder, and the honest backtester
        arrive in the next phases.
      </div>
    </div>
  );
}

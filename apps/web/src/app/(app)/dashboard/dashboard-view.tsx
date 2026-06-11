"use client";

import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { LivePrice } from "@/components/live-price";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <Card className="p-5 hover:border-primary/30">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </Card>
  );
}

export function DashboardView() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: () => api.strategies() });
  const backtests = useQuery({ queryKey: ["backtests"], queryFn: () => api.backtests() });
  const paper = useQuery({ queryKey: ["paper-sessions"], queryFn: () => api.paperSessions() });
  const instruments = useQuery({ queryKey: ["instruments"], queryFn: () => api.instruments() });

  const runningSessions = paper.data?.filter((s) => s.status === "running") ?? [];
  const running = runningSessions.length;

  // Display-only aggregate of paper equity across active sessions (latest snapshot,
  // or starting cash before the first run). Money math that matters stays server-side.
  const portfolioValue = runningSessions.reduce((sum, s) => {
    const eq = (s.snapshot as { final_equity?: string } | null)?.final_equity;
    return sum + (eq ? Number(eq) : Number(s.initial_cash));
  }, 0);
  const portfolioLabel = paper.isLoading
    ? "…"
    : `$${portfolioValue.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome back{me.data?.display_name ? `, ${me.data.display_name}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">Your market intelligence at a glance.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Portfolio Value"
          value={portfolioLabel}
          hint={running ? `paper · ${running} active` : "deploy a strategy to begin"}
        />
        <Stat label="Strategies" value={strategies.data?.length ?? "—"} hint="canonical specs" />
        <Stat label="Backtests" value={backtests.data?.length ?? "—"} hint="runs stored" />
        <Stat label="Paper sessions" value={running ?? "—"} hint="running now" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Markets</CardTitle>
            <Link href="/markets" className="text-xs text-primary hover:underline">
              View all
            </Link>
          </CardHeader>
          <CardContent className="pt-3">
            {instruments.isLoading ? (
              <Skeleton className="h-40 w-full" />
            ) : (
              <div className="divide-y divide-border">
                {(instruments.data ?? []).slice(0, 6).map((i) => (
                  <Link
                    key={i.id}
                    href={`/chart/${i.id}`}
                    className="grid grid-cols-[5rem_1fr_auto_auto] items-center gap-3 py-2.5 text-sm transition-colors hover:text-primary"
                  >
                    <span className="font-medium tabular-nums">{i.symbol}</span>
                    <span className="truncate text-muted-foreground">{i.name}</span>
                    <LivePrice instrumentId={i.id} />
                    <Badge variant={i.asset_class === "crypto" ? "accent" : "default"}>
                      {i.asset_class}
                    </Badge>
                  </Link>
                ))}
                {!instruments.data?.length ? (
                  <p className="py-3 text-sm text-muted-foreground">
                    No markets available yet — instruments will appear here as soon as market data
                    is connected.
                  </p>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>AI Insights</CardTitle>
            <Sparkles size={15} className="text-primary" />
          </CardHeader>
          <CardContent className="space-y-3 pt-3 text-sm text-muted-foreground">
            <p>
              Ask the assistant to draft a strategy, explain a backtest, or summarize a market —
              grounded in your data, never financial advice.
            </p>
            <Link href="/strategies" className="inline-block text-xs text-primary hover:underline">
              Generate a strategy with AI →
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

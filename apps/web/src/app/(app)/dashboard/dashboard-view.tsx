"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
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

/**
 * A count tile that tells the truth about all three states. `data?.length ?? "—"` cannot:
 * it renders the same dash while loading and while failing, and `n ?? "—"` on a number
 * that is never nullish renders 0 during load — a confident, wrong zero.
 */
function count<T>(query: UseQueryResult<T[]>): { value: ReactNode; hint?: string } {
  if (query.isLoading) return { value: "…" };
  if (query.isError) return { value: "—", hint: "couldn't load" };
  return { value: query.data?.length ?? 0 };
}

export function DashboardView() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: () => api.strategies() });
  const backtests = useQuery({ queryKey: ["backtests"], queryFn: () => api.backtests() });
  const paper = useQuery({ queryKey: ["paper-sessions"], queryFn: () => api.paperSessions() });
  const instruments = useQuery({ queryKey: ["instruments"], queryFn: () => api.instruments() });

  const runningCount = paper.data?.filter((s) => s.status === "running").length ?? 0;

  /*
   * There is deliberately NO aggregate "Portfolio Value" tile here.
   *
   * The previous version summed `Number(final_equity)` across running sessions in the
   * browser. That broke the platform's core invariant — money is Decimal server-side and
   * crosses the wire as a string, never arithmetic'd on the client — and the sum was not
   * even a coherent quantity: it mixed post-run equity with pre-run starting cash for
   * sessions that had never executed, and filtered to `running`, so stopping a session
   * made the headline number drop to zero as if capital had evaporated.
   *
   * No endpoint returns an owner-level portfolio aggregate today, so rather than invent
   * one in floating point we show counts here and let /paper display each session's own
   * server-computed equity string. Restore a tile here only behind a real API aggregate.
   */
  const strategyStat = count(strategies);
  const backtestStat = count(backtests);
  const instrumentStat = count(instruments);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Welcome back{me.data?.display_name ? `, ${me.data.display_name}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">
          Your research workspace at a glance. Prices are delayed; paper balances are simulated.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Strategies" value={strategyStat.value} hint={strategyStat.hint ?? "canonical specs"} />
        <Stat label="Simulations" value={backtestStat.value} hint={backtestStat.hint ?? "backtest runs stored"} />
        <Stat
          label="Paper sessions"
          value={paper.isLoading ? "…" : paper.isError ? "—" : runningCount}
          hint={paper.isError ? "couldn't load" : "running now · simulated"}
        />
        <Stat
          label="Instruments"
          value={instrumentStat.value}
          hint={instrumentStat.hint ?? "tracked in your universe"}
        />
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
            ) : instruments.isError ? (
              <p className="py-3 text-sm text-loss">
                Couldn&apos;t load instruments. This is a connection problem, not an empty universe.
              </p>
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
            {/* Named for what it is: a link to the copilot. A card titled "AI Insights" that
                never produces one is vaporware in the middle of the app. */}
            <CardTitle>AI copilot</CardTitle>
            <Sparkles size={15} className="text-primary" />
          </CardHeader>
          <CardContent className="space-y-3 pt-3 text-sm text-muted-foreground">
            <p>
              Describe a strategy and the copilot drafts a canonical spec for you to review, or ask
              it to narrate a finished simulation. It proposes and explains — it never places an
              order, and it is not financial advice.
            </p>
            <Link href="/strategies" className="inline-block text-xs text-primary hover:underline">
              Draft a strategy with AI →
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

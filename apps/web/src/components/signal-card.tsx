"use client";

import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";

import { DataBadge } from "@/components/data-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Signal, type StrategySpec } from "@/lib/api/client";

/**
 * Display-only formatter for a server-sent Decimal-string price. The MONEY math
 * (stop = fill·(1-stop%), target, size) is all done server-side (invariant #2);
 * here we only trim the string for the eye — never compute with it.
 */
function fmtPrice(v: string): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  const places = Math.abs(n) >= 100 ? 2 : Math.abs(n) >= 1 ? 4 : 6;
  return n.toLocaleString(undefined, {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  });
}

function fmtSize(v: string): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return v;
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

/**
 * The F2 signal card. Evaluates a StrategySpec against an instrument's latest CLOSED
 * bar (server-side, real engine math) and shows the INTENDED entry/stop/target/size.
 *
 * HONESTY: every price carries a DELAYED DataBadge (invariant #3). This is NOT an
 * executable order — the footer says so and live trading stays gated. Numbers are
 * the engine's own output (invariant #4); the client never does money math.
 */
export function SignalCard({
  instrumentId,
  spec,
  equity,
}: {
  instrumentId: string;
  spec: StrategySpec;
  /** Optional buying power (Decimal string) for an absolute `size`. */
  equity?: string;
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["signal", instrumentId, JSON.stringify(spec), equity ?? null],
    queryFn: () => api.signal(instrumentId, spec, equity),
    retry: false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Signal · {spec.name}</CardTitle>
        {data ? (
          data.should_enter ? (
            <Badge variant="profit">Entry signal</Badge>
          ) : (
            <Badge variant="default">No entry</Badge>
          )
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4 pt-3">
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : isError ? (
          <p className="text-sm text-muted-foreground">
            {(error as Error)?.message ?? "Could not evaluate a signal for this market yet."}
          </p>
        ) : data ? (
          <Body data={data} hasEquity={Boolean(equity)} />
        ) : null}
      </CardContent>
    </Card>
  );
}

function Body({ data, hasEquity }: { data: Signal; hasEquity: boolean }) {
  return (
    <>
      <p className="text-sm text-muted-foreground">
        {data.should_enter
          ? "The entry rule fires on the latest closed bar. If taken, the engine would intend:"
          : "The entry rule does not fire on the latest closed bar. If it did, the engine would intend:"}
      </p>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <Metric label="Entry" value={fmtPrice(data.entry)} priced />
        <Metric label="Stop" value={data.stop ? fmtPrice(data.stop) : "—"} priced={!!data.stop} tone="loss" />
        <Metric
          label="Target"
          value={data.target ? fmtPrice(data.target) : "—"}
          priced={!!data.target}
          tone="profit"
        />
        <Metric
          label={hasEquity ? "Size (units)" : "Size / $10k"}
          value={fmtSize(hasEquity && data.size ? data.size : data.size_per_10k)}
        />
      </dl>

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          Ref {fmtPrice(data.reference_price)} <DataBadge kind="DELAYED" title="Latest closed bar" />
        </span>
        <span aria-hidden>·</span>
        <span>{data.timeframe} bar</span>
        <span aria-hidden>·</span>
        <span>as of {new Date(data.as_of).toLocaleString()}</span>
      </div>

      <div
        role="note"
        className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
      >
        <Info size={14} className="mt-0.5 shrink-0" />
        <span>
          Not an executable order. Prices are DELAYED and modeled on the last closed bar; a real fill
          would occur at the next bar&apos;s open. Live trading is not enabled.
        </span>
      </div>
    </>
  );
}

function Metric({
  label,
  value,
  priced = false,
  tone,
}: {
  label: string;
  value: string;
  priced?: boolean;
  tone?: "profit" | "loss";
}) {
  const toneClass = tone === "profit" ? "text-profit" : tone === "loss" ? "text-loss" : "text-foreground";
  return (
    <div className="space-y-1">
      <dt className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
        {priced ? <DataBadge kind="DELAYED" title="Modeled on the latest closed bar" /> : null}
      </dt>
      <dd className={`font-mono text-sm tabular-nums ${toneClass}`}>{value}</dd>
    </div>
  );
}

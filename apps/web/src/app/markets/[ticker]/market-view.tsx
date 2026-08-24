"use client";

import { ArrowLeft, ArrowRight } from "lucide-react";
import Link from "next/link";

import type { FaqItem } from "@/components/faq-jsonld";

import { ChartAttribution } from "@/components/chart-attribution";
import { DataBadge } from "@/components/data-badge";
import { HypotheticalBanner } from "@/components/hypothetical-banner";
import { PublicChart } from "@/components/public-chart";
import { buttonVariants } from "@/components/ui/button";
import type { PublicMarket } from "@/lib/api/client";
import { BRAND_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

// Reference-backtest metrics we surface, in display order (keys from
// backtesting/metrics.compute_metrics). Percent-valued keys are formatted as %.
//
// PUBLIC surface: annualized metrics (CAGR/Sharpe/Sortino) are deliberately OMITTED.
// The reference run may cover only a short sample, over which annualization produces
// absurd, misleading figures — and these pages are crawlable. The server also strips
// them from the response (see public_router._public_metrics), so this is belt-and-
// suspenders. We show only honest, per-run, non-annualized figures.
const METRICS: [string, string][] = [
  ["total_return", "Return / run"],
  ["max_drawdown", "Max DD"],
  ["win_rate", "Win rate"],
  ["profit_factor", "Profit factor"],
  ["num_trades", "Trades"],
];
const PCT = new Set(["total_return", "max_drawdown", "win_rate"]);

/**
 * A metric the server withheld arrives as `null`, and that is information, not a
 * gap: an annualized figure is suppressed below a documented sample-size floor, and
 * a ratio with no denominator (profit factor with no losing trade) is undefined
 * rather than zero. Rendering "n/a" is the honest answer; coercing null to 0 would
 * present "we could not measure this" as "this measured zero".
 */
function fmtMetric(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  // Never print "NaN"/"Infinity" on a crawlable page — an unrepresentable metric is
  // honestly a dash, not a number a reader might take at face value.
  if (!Number.isFinite(value)) return "—";
  if (PCT.has(key)) return `${(value * 100).toFixed(2)}%`;
  if (key === "num_trades") return String(value);
  return value.toFixed(2);
}

/** Latest real (non-warm-up) value in an indicator series, or null if all blank. */
function latestValue(values: (number | null)[]): number | null {
  for (let i = values.length - 1; i >= 0; i -= 1) {
    if (values[i] !== null) return values[i];
  }
  return null;
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().replace("T", " ").slice(0, 16)} UTC`;
}

export function MarketView({
  market,
  slug,
  faq,
}: {
  market: PublicMarket;
  slug: string;
  faq: FaqItem[];
}) {
  const {
    instrument,
    latest,
    indicators,
    reference_backtest: ref,
    timeframe,
    quote_currency: quoteCurrency,
  } = market;
  const displayName = instrument.name ?? instrument.ticker;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-border/60 bg-background/70 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="h-6 w-6 rounded-md gradient-brand" />
            <span className="font-semibold tracking-tight">{BRAND_NAME}</span>
          </Link>
          <Link href="/" className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "gap-2")}>
            <ArrowLeft size={15} /> Home
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-10">
        {/* Hero: symbol + name + delayed price. */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-primary">{instrument.asset_class}</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight md:text-4xl">
              {instrument.ticker}
            </h1>
            <p className="mt-1 text-muted-foreground">{displayName}</p>
          </div>
          <div className="text-right">
            {latest ? (
              <>
                <div className="flex items-center justify-end gap-2">
                  <span className="text-2xl font-semibold tabular-nums">
                    {Number(latest.price).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                    <span className="ml-1 text-sm text-muted-foreground">{quoteCurrency}</span>
                  </span>
                  <DataBadge kind="DELAYED" title="Delayed market data — not a live quote." />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  As of {fmtDateTime(latest.as_of)}
                </p>
              </>
            ) : (
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="text-sm">No delayed price yet</span>
                <DataBadge kind="DELAYED" />
              </div>
            )}
          </div>
        </div>

        {/* Delayed candlestick chart. */}
        <section className="mt-8 space-y-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-muted-foreground">
              Price chart · {timeframe}
            </h2>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Delayed OHLCV</span>
              <DataBadge kind="DELAYED" title="Polled historical bars — not a live feed." />
            </div>
          </div>
          <PublicChart
            slug={slug}
            timeframe={timeframe}
            label={`${displayName} (${instrument.ticker})`}
          />
        </section>

        {/* Real indicators (latest values). */}
        {indicators.length ? (
          <section className="mt-8 space-y-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              Technical indicators
            </h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {indicators.map((series) => {
                const v = latestValue(series.values);
                return (
                  <div key={series.key} className="rounded-lg border border-border bg-card p-3">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">
                      {series.label}
                    </div>
                    <div className="mt-1 text-lg font-semibold tabular-nums">
                      {v === null ? "—" : v.toFixed(2)}
                    </div>
                  </div>
                );
              })}
            </div>
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              Computed causally (no look-ahead) with the same engine that powers backtests. Values
              during an indicator&apos;s warm-up window are shown as &ldquo;—&rdquo; rather than
              back-filled.
            </p>
          </section>
        ) : null}

        {/* Reference backtest — a HYPOTHETICAL research illustration, under the banner.
            This block is the one on the page that could be mistaken for a trading signal
            offered to a visitor, so it is framed three times over: what the strategy is,
            that it was fixed in advance, and that nobody is being told to do anything. */}
        <section className="mt-10 space-y-3">
          <h2 className="text-lg font-medium">Reference strategy illustration</h2>
          <p className="text-sm text-muted-foreground">
            One fixed, un-optimised SMA-crossover rule — chosen in advance and identical on every
            ticker page — replayed over {instrument.ticker}&apos;s delayed historical bars. It
            exists to show how the engine reports a result, not to suggest a position. It is not a
            signal, not a recommendation, and not tailored to anyone.
          </p>
          <HypotheticalBanner />
          {ref.available ? (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {METRICS.filter(([k]) => k in ref.metrics).map(([key, label]) => (
                  <div key={key} className="rounded-lg border border-border bg-card p-3">
                    <div className="text-xs uppercase tracking-wide text-muted-foreground">
                      {label}
                    </div>
                    <div className="mt-1 text-lg font-semibold tabular-nums">
                      {fmtMetric(key, ref.metrics[key])}
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {ref.strategy} · {ref.timeframe} · {ref.bars} bars
                {ref.start && ref.end
                  ? ` · ${ref.start.slice(0, 10)} → ${ref.end.slice(0, 10)}`
                  : ""}
                . Reproducible: spec {ref.spec_hash.slice(0, 12)} on engine {ref.engine_version}.
                Figures are the outcome of a historical simulation under the assumptions shown, net
                of modeled commission &amp; slippage — hypothetical, and not predictive of future
                performance. These are{" "}
                <strong>per-run figures over a limited sample and are NOT annualized</strong>{" "}
                (annualized metrics like CAGR/Sharpe/Sortino are omitted here — they are
                meaningless over a short window).{" "}
                <Link
                  href="/methodology"
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  How these numbers are computed
                </Link>
                .
              </p>
            </>
          ) : (
            <p className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
              {ref.note || "Not enough history to run the reference backtest for this market yet."}
            </p>
          )}
        </section>

        {/* FAQ — visible copy matches the FAQPage JSON-LD emitted server-side. */}
        <section className="mt-10 space-y-3">
          <h2 className="text-lg font-medium">Frequently asked questions</h2>
          <div className="space-y-3">
            {faq.map((item) => (
              <div key={item.question} className="rounded-xl border border-border bg-card p-4">
                <h3 className="text-sm font-medium">{item.question}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{item.answer}</p>
              </div>
            ))}
          </div>
        </section>

        <div className="mt-10 flex flex-wrap items-center gap-3">
          {/* A research CTA, not a trading one: it invites the visitor to test their own
              idea, never to act on the illustration above. */}
          <Link href="/login" className={cn(buttonVariants({ size: "lg" }), "gap-2")}>
            Test your own idea <ArrowRight size={16} />
          </Link>
          <Link
            href="/methodology"
            className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
          >
            Methodology
          </Link>
        </div>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-4xl flex-col items-center justify-between gap-3 px-6 py-8 text-sm text-muted-foreground sm:flex-row">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded gradient-brand" />
            {BRAND_NAME}
          </div>
          <div className="flex flex-col items-center gap-2 text-center sm:flex-row sm:gap-4">
            <ChartAttribution />
            <span>Delayed data. Hypothetical results. Not investment advice.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { HypotheticalBanner } from "@/components/hypothetical-banner";
import { api, type PublicTrackRecord } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * Landing-page track record: a REAL, curated, caveated aggregate of the platform's own
 * reference SMA-crossover backtest across the covered universe. Every number is real
 * compute_metrics() output served by GET /public/track-record — no fabricated figures
 * (invariant #4). The whole block sits UNDER a HypotheticalBanner (invariant #3): it is
 * a per-run, equal-weight AVERAGE, never compounded, never a real/achievable return.
 *
 * Metric tiles mirror components/backtest-results.tsx (same labels, same net-of-cost
 * formatting) so the marketing surface shows numbers the exact way the app does.
 */

// Same subset + labels the backtest results grid shows; num_trades is a summed count.
const METRICS: [string, string][] = [
  ["total_return", "Avg return / run"],
  ["cagr", "Avg CAGR"],
  ["sharpe", "Avg Sharpe"],
  ["sortino", "Avg Sortino"],
  ["max_drawdown", "Avg max DD"],
  ["win_rate", "Avg win rate"],
];
const PCT = new Set(["total_return", "cagr", "max_drawdown", "win_rate"]);

function fmtMetric(key: string, value: number): string {
  if (PCT.has(key)) return `${(value * 100).toFixed(2)}%`;
  return value.toFixed(2);
}

/** Server-fetch the aggregate; null when the backend is unreachable so the landing
 * still renders (the section simply hides rather than showing a fabricated fallback). */
async function loadTrackRecord(): Promise<PublicTrackRecord | null> {
  try {
    return await api.publicTrackRecord({ next: { revalidate: 3600 } });
  } catch {
    return null;
  }
}

export async function TrackRecord() {
  const tr = await loadTrackRecord();
  // Hide entirely when unreachable or nothing has enough history yet — never invent a number.
  if (!tr || !tr.available) return null;

  const tiles = METRICS.filter(([k]) => k in tr.metrics);
  const numTrades = tr.metrics.num_trades;

  return (
    <section className="mx-auto max-w-6xl px-6 py-20">
      <div className="mx-auto max-w-2xl text-center">
        <p className="text-sm font-medium text-primary">A real, reproducible illustration</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
          The same engine, run in the open
        </h2>
        <p className="mt-3 text-sm text-muted-foreground">
          One un-optimized {tr.strategy} run through the exact engine your backtests use, over{" "}
          <span className="tabular-nums text-foreground">{tr.symbols_covered}</span> of{" "}
          <span className="tabular-nums text-foreground">{tr.symbols_total}</span> instruments and{" "}
          <span className="tabular-nums text-foreground">
            {tr.total_bars.toLocaleString()}
          </span>{" "}
          delayed historical bars. Equal-weight, per-run average — not a portfolio, not compounded.
        </p>
      </div>

      <div className="mx-auto mt-8 max-w-3xl space-y-4">
        <HypotheticalBanner />

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {tiles.map(([key, label]) => (
            <div key={key} className="rounded-lg border border-border bg-card p-3">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
              <div className="mt-1 text-lg font-semibold tabular-nums">
                {fmtMetric(key, tr.metrics[key])}
              </div>
            </div>
          ))}
        </div>

        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Net of modeled costs — commission&nbsp;{tr.commission_bps}&nbsp;bps/side +
          slippage&nbsp;{tr.slippage_bps}&nbsp;bps. Aggregated across{" "}
          {numTrades != null ? (
            <span className="tabular-nums">{Math.round(numTrades).toLocaleString()} </span>
          ) : null}
          hypothetical trades. Sharpe &amp; Sortino annualized at a 0 risk-free rate. Per-run
          average, not indicative of future results and not an achievable return. Engine{" "}
          <span className="tabular-nums">{tr.engine_version}</span>
          {tr.spec_hash ? (
            <>
              {" · spec "}
              <span className="tabular-nums">{tr.spec_hash.slice(0, 10)}</span>
            </>
          ) : null}
          .
        </p>

        {tr.components.length ? (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-card text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Instrument</th>
                  <th className="px-3 py-2 text-right font-medium">Return / run</th>
                  <th className="px-3 py-2 text-right font-medium">Max DD</th>
                  <th className="px-3 py-2 text-right font-medium">Trades</th>
                  <th className="px-3 py-2 text-right font-medium">Bars</th>
                </tr>
              </thead>
              <tbody>
                {tr.components.map((c) => (
                  <tr key={c.symbol} className="border-t border-border">
                    <td className="px-3 py-1.5 font-medium">{c.symbol}</td>
                    <td
                      className={`px-3 py-1.5 text-right tabular-nums ${
                        (c.metrics.total_return ?? 0) >= 0 ? "text-profit" : "text-loss"
                      }`}
                    >
                      {c.metrics.total_return != null
                        ? `${(c.metrics.total_return * 100).toFixed(2)}%`
                        : "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-loss">
                      {c.metrics.max_drawdown != null
                        ? `${(c.metrics.max_drawdown * 100).toFixed(2)}%`
                        : "—"}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                      {Math.round(c.metrics.num_trades ?? 0)}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                      {c.bars.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <p className="text-[11px] leading-relaxed text-muted-foreground">{tr.data_note}</p>

        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Link
            href="/backtests"
            className={cn(buttonVariants({ variant: "outline", size: "sm" }), "gap-2")}
          >
            Run your own backtest <ArrowRight size={15} />
          </Link>
          <Link
            href="/methodology"
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            How these numbers are computed
          </Link>
        </div>
      </div>
    </section>
  );
}

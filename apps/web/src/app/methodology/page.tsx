import {
  ArrowLeft,
  BadgeCheck,
  FlaskConical,
  Gauge,
  Info,
  LineChart,
  Lock,
  Sparkles,
  Wallet,
} from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ChartAttribution } from "@/components/chart-attribution";
import { buttonVariants } from "@/components/ui/button";
import { BRAND_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Methodology",
  description:
    "How TradePulse computes what it shows — a look-ahead-free simulation engine, costs modelled by default, honest metric conventions, delayed-data provenance — and what it deliberately does not claim.",
};

type Section = { icon: typeof FlaskConical; title: string; points: string[] };

const REAL: Section[] = [
  {
    icon: FlaskConical,
    title: "Event-driven backtest engine",
    points: [
      "Bars are replayed one at a time — the engine can only act on information available up to that bar, so it is structurally look-ahead-free.",
      "Orders fill at the next bar's open, never the signal bar's close. No same-bar hindsight.",
      "Every run is reproducible: it records a spec hash, an engine version, and a data fingerprint.",
    ],
  },
  {
    icon: Gauge,
    title: "Costs are modeled by default",
    points: [
      "Commission of 2 bps per side and 1 bps of adverse slippage are applied to every fill.",
      "Reported returns are therefore net of costs — the total commission paid is shown alongside every result.",
      "A zero-cost mode exists only for internal tests and is loudly flagged; it is never the default.",
    ],
  },
  {
    icon: Lock,
    title: "Risk controls are enforced, not decorative",
    points: [
      "Position caps, a max-daily-loss halt, and consecutive-loss limits run inside the engine.",
      "Each risk event is recorded on the result — you can see exactly when a control fired.",
      "Real-money trading stays gated behind these hard controls by design.",
    ],
  },
  {
    icon: BadgeCheck,
    title: "How performance is reported",
    points: [
      "Drawdown is always shown next to returns — an equity curve on its own hides risk.",
      "Sharpe and Sortino are annualized with a risk-free rate of 0. That is stated wherever they appear so the numbers are auditable.",
      "Every trade is exportable to CSV. Backtest numbers carry a persistent 'hypothetical performance' notice.",
      "The only performance figures we publish anywhere are runs of one fixed, un-optimized reference SMA-crossover strategy: one aggregate on the landing page and one per public ticker page. All of them come from this exact engine over delayed historical bars, shown per run (never compounded), net of costs, and under the same hypothetical notice. They illustrate the method; they are not a claimed or achievable return.",
    ],
  },
  {
    icon: LineChart,
    title: "Market data & provenance",
    points: [
      "Prices are polled on roughly a 30-second cadence and are delayed — they are labeled DELAYED with a last-updated time, never presented as a live tick. Some deployments poll less often; the badge tells you when a value was last fetched.",
      "There is no claim of a real-time consolidated (SIP) feed, and no sub-second or streaming-tick claim anywhere in the product.",
    ],
  },
  {
    icon: Wallet,
    title: "Paper trading",
    points: [
      "Paper sessions run the exact same engine as a backtest, against the same delayed, polled bars — it is a simulation, not a broker connection.",
      "Fills are simulated on those bars — there is no real-market liquidity, latency, or partial fills. This is disclosed on the paper screen.",
    ],
  },
  {
    icon: Sparkles,
    title: "The AI copilot is grounded",
    points: [
      "It generates a validated strategy spec from plain English — and never auto-executes it.",
      "Explanations are instructed to use only the numbers actually present in a result, and to refuse rather than invent.",
      "The model is instructed to close every response with a not-investment-advice note. That is a prompt instruction, not a server-side guarantee — we do not currently append it if the model omits it.",
    ],
  },
];

const NOT_CLAIMED: string[] = [
  "A real-time, full-market consolidated (SIP) data feed — data is delayed/polled.",
  "Real-money order placement. The live-trading path refuses by construction: the controls it requires (opt-in, 2FA, step-up auth, kill-switch, per-order confirmation) are not implemented, so it returns 403 rather than pretending to be switchable.",
  "A survivorship-free reference universe. The landing-page track record covers a small, hand-picked list of currently-listed large caps and major crypto pairs, chosen with hindsight, and a symbol only counts once enough history has been backfilled for it.",
  "Survivorship-bias-free or point-in-time fundamentals.",
  "A drag-and-drop or node-graph strategy builder. Strategies are one canonical JSON spec, authored by hand or drafted by the copilot — there is no second authoring path.",
  "An automatic in-sample / out-of-sample (train/test) split on backtests.",
  "Deflated-Sharpe or multiple-testing correction for strategy search.",
  "A buy-and-hold benchmark overlay on the reference/track-record numbers — the delayed price series is exposed on the public ticker pages, but the side-by-side benchmark comparison is still on the roadmap.",
];

export default function MethodologyPage() {
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

      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-14">
        <p className="text-sm font-medium text-primary">Methodology &amp; honest limits</p>
        <h1 className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
          How the numbers are computed — and what we don&apos;t claim
        </h1>
        <p className="mt-4 max-w-2xl text-muted-foreground">
          The line between a real analytics tool and a get-rich-quick tout is transparency. Here is
          exactly how {BRAND_NAME} produces every figure it shows you, the conventions behind each
          metric, and the things we deliberately do not pretend to do.
        </p>
        <p className="mt-3 max-w-2xl text-muted-foreground">
          The organising principle is a division of labour: <strong>the AI proposes and explains;
          deterministic code validates, calculates, simulates, and enforces the risk
          boundaries.</strong> {BRAND_NAME} is a research workbench and a paper-trading simulator —
          not a signal service, not an autonomous trading bot, and not a source of financial
          advice.
        </p>

        <div className="mt-6 flex items-start gap-2 rounded-lg border border-primary/25 bg-primary/[0.06] px-3 py-2 text-xs text-foreground/80">
          <Info size={14} className="mt-0.5 shrink-0 text-primary" />
          <span>
            Backtest and paper results are hypothetical, benefit from hindsight, and do not reflect
            real trading. Past performance is not indicative of future results. Not investment advice.
          </span>
        </div>

        <div className="mt-10 space-y-4">
          {REAL.map((s) => {
            const Icon = s.icon;
            return (
              <section key={s.title} className="rounded-xl border border-border bg-card p-5">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon size={18} />
                  </div>
                  <h2 className="text-lg font-medium">{s.title}</h2>
                </div>
                <ul className="mt-3 space-y-1.5 pl-1 text-sm text-muted-foreground">
                  {s.points.map((p) => (
                    <li key={p} className="flex gap-2">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/60" />
                      <span>{p}</span>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>

        <section className="mt-8 rounded-xl border border-border bg-muted/30 p-5">
          <h2 className="text-lg font-medium">What we deliberately don&apos;t claim</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Honesty is structural here — if something can&apos;t be genuinely real on this stack, we
            don&apos;t fake it in the UI. These are on the roadmap, not in the product today:
          </p>
          <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground">
            {NOT_CLAIMED.map((p) => (
              <li key={p} className="flex gap-2">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/50" />
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-8 rounded-xl border border-border bg-card p-5">
          <h2 className="text-lg font-medium">Third-party notices</h2>
          <ul className="mt-3 space-y-1.5 text-sm text-muted-foreground">
            <li className="flex gap-2">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/60" />
              <span>
                Price and equity charts are drawn with TradingView&apos;s Lightweight Charts&trade;
                library (Apache-2.0), whose licence requires this attribution:{" "}
                <ChartAttribution className="underline underline-offset-2 hover:text-foreground" />.
                We license the library; TradingView does not endorse or review {BRAND_NAME}.
              </span>
            </li>
            <li className="flex gap-2">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/60" />
              <span>
                Market data is sourced from public providers and is delayed. {BRAND_NAME} is not a
                broker, exchange, or registered investment adviser.
              </span>
            </li>
          </ul>
        </section>

        <div className="mt-10 flex flex-wrap items-center gap-3">
          <Link href="/backtests" className={cn(buttonVariants({ size: "lg" }), "gap-2")}>
            Run a historical simulation
          </Link>
          <Link href="/" className={cn(buttonVariants({ variant: "outline", size: "lg" }))}>
            Back to home
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
            <span>Not investment advice. For research &amp; education.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

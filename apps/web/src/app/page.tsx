import {
  ArrowRight,
  Boxes,
  FlaskConical,
  LineChart,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const FEATURES = [
  {
    icon: FlaskConical,
    title: "Honest backtesting",
    body: "An event-driven engine that's structurally look-ahead-free and models real commission, slippage, and spread. Every result is reproducible.",
  },
  {
    icon: Sparkles,
    title: "AI strategy copilot",
    body: "Describe a strategy in plain English and get a validated spec back — never auto-executed. Grounded explanations of every result.",
  },
  {
    icon: LineChart,
    title: "Live charting",
    body: "TradingView-grade candles with real-time data over WebSockets, indicators, and a fast, fluid workspace.",
  },
  {
    icon: Boxes,
    title: "Strategy builder",
    body: "One canonical spec across AI, code, and a visual builder. Mandatory exits, sizing, and enforced risk limits — by design.",
  },
  {
    icon: Wallet,
    title: "Paper trading",
    body: "Deploy a strategy and watch it trade live against a virtual ledger using the exact same engine as your backtest.",
  },
  {
    icon: ShieldCheck,
    title: "Risk-first & gated",
    body: "Position caps, daily-loss halts, and a kill-switch are enforced — not decorative. Real-money trading stays gated behind hard controls.",
  },
];

const STATS = [
  ["US equities + crypto", "Markets"],
  ["Look-ahead-free", "Backtest engine"],
  ["Sub-second", "Live data"],
  ["AI-assisted", "Strategy authoring"],
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-10 border-b border-border/60 bg-background/70 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <div className="h-6 w-6 rounded-md gradient-brand" />
            <span className="font-semibold tracking-tight">Quanta</span>
          </div>
          <nav className="flex items-center gap-2">
            <Link
              href="/login"
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
            >
              Sign in
            </Link>
            <Link href="/login" className={cn(buttonVariants({ size: "sm" }))}>
              Get started
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="hero-glow relative">
        <div className="mx-auto max-w-6xl px-6 pb-16 pt-20 text-center md:pt-28">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs text-muted-foreground animate-fade-up">
            <Sparkles size={13} className="text-primary" />
            AI-Powered Trading Intelligence
          </div>
          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight md:text-6xl animate-fade-up">
            Build, analyze &amp; automate
            <br />
            <span className="gradient-text">trading strategies</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-balance text-muted-foreground md:text-lg animate-fade-up">
            Institutional-grade analytics, an honest backtesting engine, and an AI copilot — for
            US equities and crypto. The terminal that respects your edge.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3 animate-fade-up">
            <Link href="/login" className={cn(buttonVariants({ size: "lg" }), "gap-2")}>
              Start free <ArrowRight size={16} />
            </Link>
            <Link
              href="/dashboard"
              className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
            >
              Launch app
            </Link>
          </div>

          {/* Preview card */}
          <div className="mx-auto mt-14 max-w-3xl rounded-2xl border border-border glass p-2 animate-fade-up">
            <div className="rounded-xl border border-border bg-card p-5 text-left">
              <div className="flex items-center justify-between">
                <div className="text-sm text-muted-foreground">BTC/USD · Composite strategy</div>
                <span className="rounded-full bg-profit/10 px-2 py-0.5 text-xs font-medium text-profit">
                  +18.4% · Sharpe 1.7
                </span>
              </div>
              <svg viewBox="0 0 600 120" className="mt-4 h-28 w-full" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#4f8cff" stopOpacity="0.35" />
                    <stop offset="100%" stopColor="#4f8cff" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path
                  d="M0 96 L60 88 L120 92 L180 70 L240 78 L300 54 L360 60 L420 38 L480 44 L540 22 L600 28 V120 H0 Z"
                  fill="url(#eq)"
                />
                <path
                  d="M0 96 L60 88 L120 92 L180 70 L240 78 L300 54 L360 60 L420 38 L480 44 L540 22 L600 28"
                  fill="none"
                  stroke="#4f8cff"
                  strokeWidth="2"
                />
              </svg>
              <div className="mt-3 grid grid-cols-4 gap-3 text-center">
                {[
                  ["Win rate", "57%"],
                  ["Max DD", "-6.2%"],
                  ["Trades", "143"],
                  ["Profit factor", "1.9"],
                ].map(([label, value]) => (
                  <div key={label}>
                    <div className="text-sm font-semibold tabular-nums">{value}</div>
                    <div className="text-[11px] text-muted-foreground">{label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-center text-2xl font-semibold tracking-tight md:text-3xl">
          A premium quant workflow, end to end
        </h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-border bg-card p-6 transition-colors hover:border-primary/40"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <f.icon size={18} />
              </div>
              <h3 className="mt-4 font-medium">{f.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-border bg-card/40">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-px px-6 py-12 md:grid-cols-4">
          {STATS.map(([value, label]) => (
            <div key={label} className="text-center">
              <div className="text-lg font-semibold gradient-text md:text-xl">{value}</div>
              <div className="mt-1 text-xs uppercase tracking-wide text-muted-foreground">
                {label}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-6 py-24 text-center">
        <h2 className="mx-auto max-w-2xl text-3xl font-semibold tracking-tight md:text-4xl">
          Trade with an edge you can <span className="gradient-text">actually trust</span>.
        </h2>
        <p className="mx-auto mt-4 max-w-lg text-muted-foreground">
          Honest numbers, enforced risk, AI that explains instead of guesses.
        </p>
        <Link
          href="/login"
          className={cn(buttonVariants({ size: "lg" }), "mt-8 inline-flex gap-2")}
        >
          Create your account <ArrowRight size={16} />
        </Link>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 py-8 text-sm text-muted-foreground sm:flex-row">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded gradient-brand" />
            Quanta
          </div>
          <div>Not investment advice. For research &amp; education.</div>
        </div>
      </footer>
    </div>
  );
}

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
import { BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";
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
            <span className="font-semibold tracking-tight">{BRAND_NAME}</span>
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
            {BRAND_TAGLINE}
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
          <p className="mt-4 text-xs text-muted-foreground animate-fade-up">
            Not investment advice · For research &amp; education
          </p>

          {/* No fabricated performance shown — the honest positioning is the pitch. */}
          <div className="mx-auto mt-14 max-w-xl animate-fade-up">
            <p className="text-sm text-muted-foreground">
              No cherry-picked numbers here. Run a real backtest on your own strategy and see the
              actual result — net of commission &amp; slippage, measured against buy &amp; hold.
            </p>
            <Link
              href="/backtests"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-4 gap-2")}
            >
              Run a real backtest <ArrowRight size={16} />
            </Link>
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
            {BRAND_NAME}
          </div>
          <div>Not investment advice. For research &amp; education.</div>
        </div>
      </footer>
    </div>
  );
}

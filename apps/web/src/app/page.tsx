import {
  ArrowRight,
  Boxes,
  Fingerprint,
  FlaskConical,
  Gauge,
  LineChart,
  ShieldCheck,
  Sparkles,
  Wallet,
} from "lucide-react";
import Link from "next/link";

import { ChartAttribution } from "@/components/chart-attribution";
import { TrackRecord } from "@/components/track-record";
import { buttonVariants } from "@/components/ui/button";
import { BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";
import { cn } from "@/lib/utils";

/**
 * Landing copy is held to the same standard as the app: every line here has to be true
 * of the code that ships. Anything the /methodology page lists under "what we
 * deliberately do not claim" must never appear on this page in the present tense —
 * that contradiction is the fastest way a research tool starts reading like a tout.
 */
const FEATURES = [
  {
    icon: FlaskConical,
    title: "Look-ahead-free by construction",
    body: "Bars are replayed one at a time and orders fill at the next bar's open — never the signal bar's close. The engine cannot act on a price it would not have had.",
  },
  {
    icon: Gauge,
    title: "Costs modelled by default",
    body: "Commission (2 bps per side) and adverse slippage (1 bps) hit every fill, and the API exposes no way to switch them off. Reported figures are net, with total commission shown beside them.",
  },
  {
    icon: Fingerprint,
    title: "Runs you can re-derive",
    body: "Every simulation records a spec hash, an engine version, and a data fingerprint — so a figure you saw last month traces back to the exact inputs that produced it.",
  },
  {
    icon: Sparkles,
    title: "Plain English to a validated spec",
    body: "Describe an idea and the copilot drafts one canonical JSON spec. It has to pass schema validation before it can run, and nothing is auto-executed — the AI proposes, the engine decides.",
  },
  {
    icon: ShieldCheck,
    title: "Risk limits inside the loop",
    body: "Position caps, a max-daily-loss halt, and consecutive-loss limits run inside the engine, not as a warning label. Every time one fires it is recorded on the result.",
  },
  {
    icon: Wallet,
    title: "Simulation, and a door that stays shut",
    body: "Paper sessions run the same engine against delayed bars on a virtual ledger. The real-money seam refuses by construction: the controls it requires are not built, so it answers 403.",
  },
];

const STATS = [
  ["US equities + crypto", "Markets covered"],
  ["Look-ahead-free", "Simulation engine"],
  ["Delayed, polled", "Market data"],
  ["Spec-hashed", "Reproducible runs"],
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
              href="/methodology"
              className={cn(
                buttonVariants({ variant: "ghost", size: "sm" }),
                "hidden sm:inline-flex",
              )}
            >
              How it works
            </Link>
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
            Test a trading idea
            <br />
            <span className="gradient-text">before you believe it</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-balance text-muted-foreground md:text-lg animate-fade-up">
            A research workbench for US equities and crypto. The AI proposes and explains; a
            deterministic engine validates, simulates, and enforces the risk boundaries — and every
            figure you see is that engine&apos;s own output.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3 animate-fade-up">
            <Link href="/login" className={cn(buttonVariants({ size: "lg" }), "gap-2")}>
              Start free <ArrowRight size={16} />
            </Link>
            <Link
              href="/methodology"
              className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
            >
              Read the methodology
            </Link>
          </div>
          <p className="mt-4 text-xs text-muted-foreground animate-fade-up">
            Simulation only · Not investment advice · For research &amp; education
          </p>

          {/* The honest positioning IS the pitch. The only performance figure on this page
              is the real, caveated reference backtest rendered by <TrackRecord/> below —
              never a fabricated marketing stat. */}
          <div className="mx-auto mt-14 max-w-xl animate-fade-up">
            <p className="text-sm text-muted-foreground">
              The only performance figure on this page is our own fixed reference strategy, run in
              the open over a disclosed universe — net of costs, per run, hypothetical. Then run a
              simulation on your own idea and see what it actually did.
            </p>
            <Link
              href="/backtests"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-4 gap-2")}
            >
              Run a historical simulation <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </section>

      {/* Real, caveated track record — the reference backtest under a HypotheticalBanner.
          Renders nothing if the backend is unreachable or lacks enough history. */}
      <TrackRecord />

      {/* Features */}
      <section className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="text-center text-2xl font-semibold tracking-tight md:text-3xl">
          Evidence, end to end
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-sm text-muted-foreground">
          Six things the platform actually does today — each one visible in the engine, none of
          them a roadmap item written in the present tense.
        </p>
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

      {/* Authoring + charting, described exactly as they ship (no visual builder exists). */}
      <section className="mx-auto max-w-6xl px-6">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Boxes size={18} />
            </div>
            <h3 className="mt-4 font-medium">One canonical strategy spec</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Indicators, entry and exit rules, sizing, and risk limits live in a single versioned
              JSON spec. Write it by hand in the editor or have the copilot draft it — the same
              validator and the same engine run either way. There is no separate drag-and-drop
              builder: one spec, one execution path, nothing hidden between them.
            </p>
          </div>
          <div className="rounded-xl border border-border bg-card p-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <LineChart size={18} />
            </div>
            <h3 className="mt-4 font-medium">Charts with stated provenance</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              Candles with SMA/EMA/RSI overlays and oscillator panes, computed causally by the same
              indicator code the engine uses — warm-up windows left blank rather than back-filled.
              Prices are polled, not streamed, and are labelled{" "}
              <span className="font-medium text-foreground">DELAYED</span> with the time they were
              last fetched, wherever they appear.
            </p>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="mt-20 border-y border-border bg-card/40">
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
          Find out what your idea <span className="gradient-text">actually did</span>.
        </h2>
        <p className="mx-auto mt-4 max-w-lg text-muted-foreground">
          A historical simulation under assumptions you can read — not a forecast and not a
          promise. Results are hypothetical; past performance says nothing about the future.
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
          <div className="flex flex-col items-center gap-2 text-center sm:flex-row sm:gap-4">
            <Link href="/methodology" className="transition-colors hover:text-foreground">
              Methodology
            </Link>
            <ChartAttribution />
            <span>Not investment advice. For research &amp; education.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

"use client";

import { Calculator, Info, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NumberInput } from "@/components/ui/number-input";
import { Toggle } from "@/components/ui/toggle";
import { useToast } from "@/components/ui/toast";
import { ApiError, api, type PositionSizeResult } from "@/lib/api/client";

/** Only the price-driven methods make sense with an entry+stop form. */
type Method = "risk_per_trade" | "percent_equity" | "fixed_units";

const METHODS: { id: Method; label: string; hint: string }[] = [
  { id: "risk_per_trade", label: "Risk per trade", hint: "Size so a stop-out loses a fixed % of equity." },
  { id: "percent_equity", label: "% of equity", hint: "Allocate a fixed % of equity as notional." },
  { id: "fixed_units", label: "Fixed shares", hint: "A fixed share count, regardless of equity." },
];

/** Present a server-provided decimal string as currency without doing money math on it. */
function money(s: string): string {
  const n = Number(s);
  if (Number.isNaN(n)) return s;
  return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

/** Present a server-provided share-count string, trimming trailing zeros for display only. */
function shares(s: string): string {
  const n = Number(s);
  if (Number.isNaN(n)) return s;
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function pct(s: string): string {
  const n = Number(s);
  if (Number.isNaN(n)) return s;
  return `${(n * 100).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
}

export function CalculatorView() {
  const { toast } = useToast();
  const [method, setMethod] = useState<Method>("risk_per_trade");
  const [equity, setEquity] = useState("100000");
  const [riskPct, setRiskPct] = useState("1"); // risk_per_trade %
  const [allocPct, setAllocPct] = useState("25"); // percent_equity %
  const [units, setUnits] = useState("100"); // fixed_units
  const [entry, setEntry] = useState("100");
  const [stop, setStop] = useState("95");
  const [result, setResult] = useState<PositionSizeResult | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const needsStop = method === "risk_per_trade";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      // `value` semantics follow the engine: a fraction for the %-methods, a raw
      // count for fixed_units. We never compute the SIZE here — the server does.
      const value =
        method === "risk_per_trade"
          ? Number(riskPct) / 100
          : method === "percent_equity"
            ? Number(allocPct) / 100
            : Number(units);
      const res = await api.positionSize({
        method,
        value,
        equity,
        entry,
        stop: needsStop ? stop : null,
      });
      setResult(res);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Could not compute size.";
      toast({ description: message, variant: "error" });
      setResult(null);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Position Calculator</h1>
        <p className="text-sm text-muted-foreground">
          Sizing guidance from the same engine math the backtester uses — not an order.
        </p>
      </div>

      {/* Honesty banner — the output is guidance, never an executable order (live trading gated). */}
      <div
        role="note"
        className="flex items-start gap-2 rounded-lg border border-primary/25 bg-primary/[0.06] px-3 py-2 text-xs text-foreground/80"
      >
        <ShieldAlert size={14} className="mt-0.5 shrink-0 text-primary" />
        <span>
          This is <strong>sizing guidance, not an order</strong>. TradePulse does not place live
          trades — real-money execution is intentionally gated behind hard risk controls.
        </span>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4">
              <div>
                <span className="text-xs font-medium text-muted-foreground">Method</span>
                <div className="mt-1.5 flex flex-wrap gap-2">
                  {METHODS.map((m) => (
                    <Toggle
                      key={m.id}
                      pressed={method === m.id}
                      onClick={() => setMethod(m.id)}
                      aria-label={m.label}
                    >
                      {m.label}
                    </Toggle>
                  ))}
                </div>
                <p className="mt-1.5 text-[11px] text-muted-foreground/70">
                  {METHODS.find((m) => m.id === method)?.hint}
                </p>
              </div>

              <NumberInput
                name="equity"
                label="Account size"
                prefix="$"
                min={0}
                step="any"
                value={equity}
                onChange={(e) => setEquity(e.target.value)}
              />

              {method === "risk_per_trade" && (
                <NumberInput
                  name="riskPct"
                  label="Risk per trade"
                  suffix="%"
                  min={0}
                  step="any"
                  value={riskPct}
                  onChange={(e) => setRiskPct(e.target.value)}
                  hint="Percent of equity lost if the stop is hit."
                />
              )}
              {method === "percent_equity" && (
                <NumberInput
                  name="allocPct"
                  label="Allocation"
                  suffix="%"
                  min={0}
                  step="any"
                  value={allocPct}
                  onChange={(e) => setAllocPct(e.target.value)}
                  hint="Percent of equity to allocate as notional."
                />
              )}
              {method === "fixed_units" && (
                <NumberInput
                  name="units"
                  label="Shares"
                  min={0}
                  step="any"
                  value={units}
                  onChange={(e) => setUnits(e.target.value)}
                />
              )}

              <div className="grid grid-cols-2 gap-3">
                <NumberInput
                  name="entry"
                  label="Entry price"
                  prefix="$"
                  min={0}
                  step="any"
                  value={entry}
                  onChange={(e) => setEntry(e.target.value)}
                />
                <NumberInput
                  name="stop"
                  label="Stop price"
                  prefix="$"
                  min={0}
                  step="any"
                  value={stop}
                  disabled={!needsStop}
                  onChange={(e) => setStop(e.target.value)}
                  hint={needsStop ? "Protective stop." : "Used for risk-per-trade sizing."}
                />
              </div>

              <Button type="submit" disabled={submitting} className="w-full">
                <Calculator size={16} />
                {submitting ? "Computing…" : "Calculate size"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Result
            </div>
            {result ? (
              <dl className="space-y-3">
                <Row label="Shares" value={shares(result.qty)} big />
                <Row label="Notional" value={money(result.notional)} />
                <Row label="Risk amount" value={money(result.risk_amount)} />
                <Row label="Portfolio risk" value={pct(result.pct_of_equity)} />
              </dl>
            ) : (
              <p className="text-sm text-muted-foreground">
                Enter your account size, entry, and stop, then calculate to see the suggested share
                count and portfolio exposure.
              </p>
            )}
            <p className="flex items-start gap-1.5 border-t border-border pt-3 text-[11px] text-muted-foreground/70">
              <Info size={12} className="mt-0.5 shrink-0" />
              All figures are computed server-side as exact decimals from the engine&apos;s sizing
              math; nothing is calculated in your browser.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className={`tabular-nums ${big ? "text-2xl font-semibold" : "text-sm font-medium"}`}>
        {value}
      </dd>
    </div>
  );
}

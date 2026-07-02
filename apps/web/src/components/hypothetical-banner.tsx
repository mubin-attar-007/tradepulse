import { Info } from "lucide-react";

/**
 * Persistent, equal-weight performance disclosure shown ABOVE any backtest/paper result — not
 * buried as footer fine print. Backtest numbers are hypothetical (hindsight, no live execution);
 * paper fills are simulated. This is the NFA/SEC-style standard for honest performance display.
 */
export function HypotheticalBanner({ kind = "backtest" }: { kind?: "backtest" | "paper" }) {
  const text =
    kind === "paper"
      ? "Paper results are simulated on historical/live bars — no real-market liquidity, latency, or partial fills. Not investment advice."
      : "Backtest results are hypothetical, benefit from hindsight, and do not reflect real trading. Past performance is not indicative of future results.";
  return (
    <div
      role="note"
      className="flex items-start gap-2 rounded-lg border border-primary/25 bg-primary/[0.06] px-3 py-2 text-xs text-foreground/80"
    >
      <Info size={14} className="mt-0.5 shrink-0 text-primary" />
      <span>{text}</span>
    </div>
  );
}

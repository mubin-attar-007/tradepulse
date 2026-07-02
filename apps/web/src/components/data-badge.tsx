import { cn } from "@/lib/utils";

type Provenance = "LIVE" | "DELAYED" | "EOD" | "SIMULATED" | "PAPER";

const STYLES: Record<Provenance, string> = {
  LIVE: "border-profit/40 bg-profit/10 text-profit",
  DELAYED: "border-border bg-muted text-muted-foreground",
  EOD: "border-border bg-muted text-muted-foreground",
  SIMULATED: "border-primary/40 bg-primary/10 text-primary",
  PAPER: "border-primary/40 bg-primary/10 text-primary",
};

/**
 * Data-provenance chip (TradingView-style). We never claim "LIVE" for polled/delayed data —
 * a bare price number with no provenance is a tout tell.
 */
export function DataBadge({ kind, title }: { kind: Provenance; title?: string }) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center rounded border px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
        STYLES[kind],
      )}
    >
      {kind}
    </span>
  );
}

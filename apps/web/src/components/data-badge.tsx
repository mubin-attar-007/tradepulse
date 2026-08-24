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
 * Data-provenance chip. A bare price with no provenance is a tout tell, so every number
 * sourced from market data or a simulated ledger wears one of these.
 *
 * `LIVE` is defined and deliberately never used: the ingestion path is a periodic REST
 * poll, so there is no live feed to label. It stays in the union so the day a real
 * streaming source exists there is one obvious place to wire it — not so that someone
 * reaches for it to make delayed data look better.
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

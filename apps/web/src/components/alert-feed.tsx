"use client";

import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";

import { QueryError } from "@/components/query-error";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { type Alert, api } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/** Human label + Badge variant per alert kind. */
const KIND_META: Record<string, { label: string; variant: "profit" | "loss" | "accent" | "default" }> = {
  entry: { label: "Entry", variant: "accent" },
  exit: { label: "Exit", variant: "default" },
  risk_event: { label: "Risk", variant: "loss" },
};

function formatWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function detailLine(alert: Alert): string {
  const d = alert.detail as Record<string, unknown>;
  const price = d.price != null ? `@ ${String(d.price)}` : "";
  const qty = d.qty != null ? `${String(d.qty)} sh` : "";
  if (alert.kind === "exit") {
    const pnl = d.pnl != null ? `pnl ${String(d.pnl)}` : "";
    const reason = d.reason != null ? String(d.reason) : "";
    return [qty, price, pnl, reason].filter(Boolean).join(" · ");
  }
  if (alert.kind === "risk_event") {
    const kind = d.kind != null ? String(d.kind) : "";
    const detail = d.detail != null ? String(d.detail) : "";
    return [kind, detail].filter(Boolean).join(" · ");
  }
  return [qty, price].filter(Boolean).join(" · ");
}

export function AlertFeed() {
  const { data: alerts, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.alerts(),
    // Alerts are produced by the ~30s paper-session cron; poll so the feed stays fresh.
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-14 w-full" />
      </div>
    );
  }

  // A feed that cannot be fetched is not a quiet feed. Distinguish the two, otherwise
  // a user whose sessions ARE firing alerts is told nothing is happening.
  if (isError) {
    return (
      <QueryError title="Couldn't load alerts" error={error} onRetry={() => void refetch()} />
    );
  }

  if (!alerts?.length) {
    return (
      <EmptyState
        icon={Bell}
        title="Nothing recorded yet"
        description="Simulated entry/exit fills and risk-control events from your paper sessions will appear here as the engine produces them."
      />
    );
  }

  return (
    <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border">
      {alerts.map((alert) => {
        const meta = KIND_META[alert.kind] ?? { label: alert.kind, variant: "default" as const };
        return (
          <li key={alert.id} className="flex items-center gap-3 bg-card px-4 py-3">
            <Badge variant={meta.variant} className="shrink-0">
              {meta.label}
            </Badge>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="font-medium tabular-nums">{alert.symbol}</span>
                <span className={cn("truncate text-xs text-muted-foreground")}>
                  {detailLine(alert)}
                </span>
              </div>
            </div>
            <time
              dateTime={alert.created_at}
              className="shrink-0 text-xs tabular-nums text-muted-foreground"
            >
              {formatWhen(alert.created_at)}
            </time>
          </li>
        );
      })}
    </ul>
  );
}

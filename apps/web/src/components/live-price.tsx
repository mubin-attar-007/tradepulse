"use client";

import { useQuery } from "@tanstack/react-query";

import { DataBadge } from "@/components/data-badge";
import { api } from "@/lib/api/client";

/**
 * Real last price for one instrument. Hits GET /market/instruments/{id}/latest,
 * which returns the Redis live price (from the worker's poll) or falls back to the
 * latest stored bar. Shows "—" until a bar has been backfilled/polled. Money is
 * rendered, never computed on (the API sends it as a decimal string).
 */
export function LivePrice({ instrumentId }: { instrumentId: string }) {
  const { data, isError, dataUpdatedAt } = useQuery({
    queryKey: ["latest", instrumentId],
    queryFn: () => api.latest(instrumentId),
    refetchInterval: 30_000, // matches the worker's 30s poll cadence
    retry: false,
  });

  if (isError || !data) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="tabular-nums">
        ${Number(data.price).toLocaleString(undefined, { maximumFractionDigits: 2 })}
      </span>
      {/* The client refetches every 30s but the SERVER's poll cadence varies by deployment
          (the documented free-tier path is driven by an external ~5-minute cron), so the
          tooltip states what we can actually observe — when this value last changed hands —
          instead of asserting an interval we may not be meeting. */}
      <DataBadge
        kind="DELAYED"
        title={`Delayed price, polled periodically. Fetched ${new Date(dataUpdatedAt).toLocaleTimeString()}.`}
      />
    </span>
  );
}

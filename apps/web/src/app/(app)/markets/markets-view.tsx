"use client";

import { useQuery } from "@tanstack/react-query";
import { ChartCandlestick } from "lucide-react";
import Link from "next/link";

import { LivePrice } from "@/components/live-price";
import { QueryError } from "@/components/query-error";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";

export function MarketsView() {
  const {
    data: instruments,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["instruments"],
    queryFn: () => api.instruments(),
  });

  // Order matters: a failed request is NOT an empty universe. Reporting "no markets
  // available" when the API is down states something false about the platform.
  if (isError) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Markets</h1>
        <QueryError title="Couldn't load markets" error={error} onRetry={() => void refetch()} />
      </div>
    );
  }

  if (!isLoading && !instruments?.length) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Markets</h1>
        <EmptyState
          icon={ChartCandlestick}
          title="No markets available"
          description="Instruments will appear here as soon as market data is connected."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Markets</h1>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-card text-left text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Symbol</th>
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Class</th>
              <th className="px-4 py-2 text-right font-medium">Last</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 6 }, (_, row) => (
                <tr key={row} className="border-t border-border">
                  <td className="px-4 py-3" colSpan={5}>
                    <Skeleton className="h-5 w-full" />
                  </td>
                </tr>
              ))
            ) : (
              (instruments ?? []).map((instrument) => (
                <tr key={instrument.id} className="border-t border-border">
                  <td className="px-4 py-2 font-medium tabular-nums">{instrument.symbol}</td>
                  <td className="px-4 py-2 text-muted-foreground">{instrument.name}</td>
                  <td className="px-4 py-2 text-muted-foreground">{instrument.asset_class}</td>
                  <td className="px-4 py-2 text-right">
                    <LivePrice instrumentId={instrument.id} />
                  </td>
                  <td className="px-4 py-2 text-right">
                    <Link className="text-primary hover:underline" href={`/chart/${instrument.id}`}>
                      Open chart →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        Prices are delayed, polled data — not a live feed. Poll cadence is deployment-specific,
        so the authority on freshness is the fetch time on each DELAYED badge, not an interval.
      </p>
    </div>
  );
}

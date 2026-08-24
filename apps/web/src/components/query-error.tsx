"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";

/**
 * The failure counterpart to <EmptyState/>.
 *
 * "No data" and "we could not ask" are different facts, and collapsing the second into
 * the first is a lie about the platform: a 500 or a dropped connection rendered as
 * "No markets available — instruments will appear as soon as market data is connected"
 * tells the user the system is fine and empty when it is neither. Every list view that
 * can fail should branch loading / error / empty / data, in that order.
 *
 * 401s never reach here — the client redirects to sign-in before the query settles
 * (see lib/api/client.ts).
 */
export function QueryError({
  title = "Couldn't load this",
  error,
  onRetry,
}: {
  title?: string;
  error: unknown;
  onRetry?: () => void;
}) {
  const detail =
    error instanceof ApiError
      ? `The server returned ${error.status}: ${error.message}`
      : error instanceof Error && error.message
        ? error.message
        : "The request did not complete. The API may be unreachable.";

  return (
    <div
      role="alert"
      className="flex flex-col items-center rounded-xl border border-loss/30 bg-card p-8 text-center"
    >
      <div className="rounded-full bg-loss/10 p-3 text-loss">
        <AlertTriangle size={20} />
      </div>
      <h2 className="mt-3 text-sm font-semibold">{title}</h2>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">{detail}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-4 gap-2" onClick={onRetry}>
          <RefreshCw size={14} /> Try again
        </Button>
      ) : null}
    </div>
  );
}

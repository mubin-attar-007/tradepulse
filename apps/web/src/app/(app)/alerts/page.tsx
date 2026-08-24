import type { Metadata } from "next";

import { AlertFeed } from "@/components/alert-feed";
import { DataBadge } from "@/components/data-badge";

export const metadata: Metadata = { title: "Activity" };

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">Activity</h1>
          <DataBadge kind="PAPER" title="Simulated fills and risk events — no real orders." />
        </div>
        {/* Named for what it is. The backend exposes only GET /alerts: this is a read-only
            event log of what the paper engine did, not configurable alerting — there are no
            rules to create, no thresholds to set, and nothing to acknowledge. */}
        <p className="text-sm text-muted-foreground">
          A read-only log of simulated entry/exit fills and risk-control events from your paper
          sessions. There are no alert rules to configure yet — this records what the engine did.
        </p>
      </div>

      <AlertFeed />
    </div>
  );
}

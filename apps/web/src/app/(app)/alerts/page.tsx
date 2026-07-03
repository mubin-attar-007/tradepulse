import type { Metadata } from "next";

import { AlertFeed } from "@/components/alert-feed";

export const metadata: Metadata = { title: "Alerts" };

export default function AlertsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Alerts</h1>
        <p className="text-sm text-muted-foreground">
          Entry/exit fills and risk-control events from your running paper sessions.{" "}
          <span className="rounded bg-muted px-1.5 py-0.5 text-xs uppercase">Paper</span>
        </p>
      </div>

      <AlertFeed />
    </div>
  );
}

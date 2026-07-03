"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Toggle } from "@/components/ui/toggle";
import { indicatorColor } from "@/lib/chart-theme";
import { INDICATOR_CATALOG, type IndicatorKind } from "@/lib/indicators";

/**
 * Toggle panel for the on-chart indicators. It only owns the toggle UI; the actual
 * series are computed server-side and drawn by ChartWorkspace (overlays on the price
 * pane, oscillators in stacked panes). The color swatch on each toggle is read from
 * chart-theme.ts so panel and chart never disagree on a series' color.
 */
export function IndicatorPanel({
  active,
  onToggle,
}: {
  active: Set<IndicatorKind>;
  onToggle: (kind: IndicatorKind) => void;
}) {
  const overlays = INDICATOR_CATALOG.filter((d) => d.placement === "overlay");
  const oscillators = INDICATOR_CATALOG.filter((d) => d.placement === "oscillator");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Indicators</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 pt-3">
        <Group label="Overlays">
          {overlays.map((d) => (
            <Toggle
              key={d.kind}
              pressed={active.has(d.kind)}
              onClick={() => onToggle(d.kind)}
              aria-label={`Toggle ${d.label}`}
            >
              <span
                aria-hidden
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: indicatorColor(d.kind) }}
              />
              {d.label}
            </Toggle>
          ))}
        </Group>
        <Group label="Oscillators">
          {oscillators.map((d) => (
            <Toggle
              key={d.kind}
              pressed={active.has(d.kind)}
              onClick={() => onToggle(d.kind)}
              aria-label={`Toggle ${d.label}`}
            >
              <span
                aria-hidden
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: indicatorColor(d.kind) }}
              />
              {d.label}
            </Toggle>
          ))}
        </Group>
      </CardContent>
    </Card>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

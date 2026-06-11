import type { Metadata } from "next";

import { ChartWorkspace } from "@/components/chart-workspace";

export const metadata: Metadata = { title: "Chart" };

export default async function ChartPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChartWorkspace instrumentId={id} />;
}

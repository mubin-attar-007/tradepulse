import { ChartWorkspace } from "@/components/chart-workspace";

export default async function ChartPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ChartWorkspace instrumentId={id} />;
}

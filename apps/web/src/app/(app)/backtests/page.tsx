import type { Metadata } from "next";

import { BacktestsView } from "./backtests-view";

export const metadata: Metadata = { title: "Backtests" };

export default function BacktestsPage() {
  return <BacktestsView />;
}

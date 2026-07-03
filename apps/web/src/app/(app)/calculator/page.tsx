import type { Metadata } from "next";

import { CalculatorView } from "./calculator-view";

export const metadata: Metadata = { title: "Position Calculator" };

export default function CalculatorPage() {
  return <CalculatorView />;
}

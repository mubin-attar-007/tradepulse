import type { FaqItem } from "@/components/faq-jsonld";
import { BRAND_NAME } from "@/lib/brand";

/**
 * The per-ticker FAQ copy. Single source of truth shared by the page's FAQPage
 * JSON-LD and the visible on-page FAQ block, so structured data can never claim
 * something the user isn't also shown (product honesty invariant #3).
 *
 * Answers are deliberately hedged and non-promissory — delayed data, hypothetical
 * backtest, not investment advice.
 */
export function tickerFaq(ticker: string, name: string | null): FaqItem[] {
  const label = name ? `${name} (${ticker})` : ticker;
  return [
    {
      question: `Is the ${ticker} price on this page live?`,
      answer:
        `No. The ${ticker} price shown is delayed market data, labeled DELAYED with the ` +
        `time it was last updated. ${BRAND_NAME} does not present a real-time consolidated ` +
        `(SIP) feed.`,
    },
    {
      question: `What does the ${ticker} reference backtest show?`,
      answer:
        `It shows a single, un-optimized SMA crossover strategy run on ${label} through the ` +
        `same event-driven engine that powers user backtests, with realistic commission and ` +
        `slippage. The result is hypothetical, benefits from hindsight, and is not a trade ` +
        `recommendation or a prediction of future returns.`,
    },
    {
      question: `Are the ${ticker} indicators computed the same way as in a backtest?`,
      answer:
        `Yes. The SMA, EMA, and RSI series are computed causally with the exact same code the ` +
        `backtest engine uses, so there is no look-ahead. Warm-up periods are left blank rather ` +
        `than back-filled.`,
    },
    {
      question: `Can I trade ${ticker} on ${BRAND_NAME}?`,
      answer:
        `${BRAND_NAME} is a research and education tool. You can build and backtest strategies ` +
        `and run them in paper (simulated) trading. Nothing here is investment advice.`,
    },
  ];
}

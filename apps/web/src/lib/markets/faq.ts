import type { FaqItem } from "@/components/faq-jsonld";
import { BRAND_NAME } from "@/lib/brand";

/**
 * The per-ticker FAQ copy. Single source of truth shared by the page's FAQPage
 * JSON-LD and the visible on-page FAQ block, so structured data can never claim
 * something the user isn't also shown (product honesty invariant #3).
 *
 * These pages are the product's most public surface and the one most easily mistaken
 * for a signal service, so the answers are deliberately non-promissory: delayed data,
 * a fixed reference strategy chosen in advance, hypothetical results, no advice, and
 * no live execution anywhere on the platform.
 */
export function tickerFaq(ticker: string, name: string | null): FaqItem[] {
  const label = name ? `${name} (${ticker})` : ticker;
  return [
    {
      question: `Is the ${ticker} price on this page live?`,
      // Deliberately states NO poll interval. This answer ships as FAQPage JSON-LD, the one
      // surface that cannot carry the "some deployments poll less often" qualifier /methodology
      // attaches — and a cadence is a per-deployment fact, not a product guarantee. The DataBadge
      // publishes the actual fetch time, which is the honest and always-correct version.
      answer:
        `No. The ${ticker} price shown is delayed, polled market data, labeled DELAYED with the ` +
        `time it was last fetched. ${BRAND_NAME} does not present a real-time consolidated ` +
        `(SIP) feed.`,
    },
    {
      question: `Is the ${ticker} reference strategy a trading signal?`,
      answer:
        `No. It is a research illustration. One fixed, un-optimised SMA crossover rule — the ` +
        `same rule on every ticker page, chosen in advance rather than picked to look good on ` +
        `${label} — is replayed over historical bars so you can see how the engine reports a ` +
        `result. It is not a recommendation, not personalised, and nobody is being told to buy ` +
        `or sell anything.`,
    },
    {
      question: `What do the ${ticker} reference numbers actually mean?`,
      answer:
        `They are the output of a historical simulation under the assumptions displayed with ` +
        `them: bars replayed one at a time, orders filled at the next bar's open, and modelled ` +
        `commission and slippage on every fill. The figures are hypothetical, benefit from ` +
        `hindsight, cover a limited sample, and are not predictive of future performance.`,
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
        `No. ${BRAND_NAME} is a research and education tool. You can build strategies, simulate ` +
        `them on historical data, and run them in paper (simulated) trading against delayed ` +
        `bars. Real-money order placement is not enabled — the live-trading path refuses by ` +
        `construction. Nothing here is investment advice.`,
    },
  ];
}

import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { FaqJsonLd } from "@/components/faq-jsonld";
import { api, ApiError, type PublicMarket } from "@/lib/api/client";
import { BRAND_NAME, SITE_URL } from "@/lib/brand";
import { tickerFaq } from "@/lib/markets/faq";
import { symbolToSlug } from "@/lib/markets/slug";

import { MarketView } from "./market-view";

type Params = { ticker: string };

// Unknown slugs (not returned by generateStaticParams) still resolve at request
// time; get_public_market 404s -> notFound() below.
export const dynamicParams = true;

/** Pre-render one page per seeded instrument at build time (best-effort). */
export async function generateStaticParams(): Promise<Params[]> {
  try {
    const instruments = await api.publicMarkets({ cache: "no-store" });
    return instruments.map((i) => ({ ticker: symbolToSlug(i.ticker) }));
  } catch {
    // Backend unreachable during build — pages render on demand instead.
    return [];
  }
}

/** Fetch the public bundle for a slug, or null when the ticker is unknown. */
async function loadMarket(ticker: string): Promise<PublicMarket | null> {
  try {
    return await api.publicMarket(ticker, { cache: "no-store" });
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<Params>;
}): Promise<Metadata> {
  const { ticker } = await params;
  const market = await loadMarket(ticker);
  if (!market) {
    return { title: "Market not found", robots: { index: false } };
  }

  const { instrument } = market;
  const displayName = instrument.name ?? instrument.ticker;
  const assetLabel = instrument.asset_class === "crypto" ? "crypto" : "stock";
  const title = `${instrument.ticker} — ${displayName} chart, indicators & backtest`;
  const description =
    `Delayed ${instrument.ticker} (${displayName}) ${assetLabel} price with a live candlestick ` +
    `chart, real SMA/EMA/RSI indicators, and a hypothetical reference backtest — computed the same ` +
    `way ${BRAND_NAME} computes every number. Not investment advice.`;
  // Canonical is the ticker page itself (never the homepage).
  const canonicalPath = `/markets/${symbolToSlug(instrument.ticker)}`;

  return {
    title,
    description,
    alternates: { canonical: canonicalPath },
    openGraph: {
      type: "website",
      title: `${title} · ${BRAND_NAME}`,
      description,
      url: `${SITE_URL}${canonicalPath}`,
    },
    twitter: { card: "summary_large_image", title, description },
  };
}

export default async function MarketPage({ params }: { params: Promise<Params> }) {
  const { ticker } = await params;
  const market = await loadMarket(ticker);
  if (!market) notFound();

  const { instrument } = market;
  const slug = symbolToSlug(instrument.ticker);
  const displayName = instrument.name ?? instrument.ticker;
  const faq = tickerFaq(instrument.ticker, instrument.name);

  // FinancialProduct structured data — describes what the page is about. It links
  // back to the canonical URL and carries only non-promissory descriptors.
  const financialProductLd = {
    "@context": "https://schema.org",
    "@type": "FinancialProduct",
    name: `${displayName} (${instrument.ticker})`,
    category: instrument.asset_class,
    url: `${SITE_URL}/markets/${slug}`,
    description:
      `Delayed ${instrument.ticker} price, real technical indicators (SMA/EMA/RSI), and a ` +
      `hypothetical reference backtest on ${BRAND_NAME}. For research and education; not ` +
      `investment advice.`,
    provider: { "@type": "Organization", name: BRAND_NAME, url: SITE_URL },
  };

  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(financialProductLd) }}
      />
      <FaqJsonLd items={faq} />
      <MarketView market={market} slug={slug} faq={faq} />
    </>
  );
}

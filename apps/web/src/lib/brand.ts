/** Single source of truth for product branding — import these instead of hardcoding the name. */
export const BRAND_NAME = "TradePulse";
/**
 * What the product IS, not what it aspires to. The AI proposes and explains;
 * deterministic code validates, simulates and enforces the risk boundaries — so the
 * tagline names the workbench, never "trading intelligence".
 */
export const BRAND_TAGLINE = "Quantitative Research & Backtesting Workbench";
export const BRAND_DESCRIPTION =
  "Compile a plain-English strategy into a validated spec, simulate it on historical bars " +
  "with a look-ahead-free engine, and paper-trade it on delayed data.";

/**
 * Canonical public origin (no trailing slash), or `null` when NEXT_PUBLIC_SITE_URL is
 * not configured.
 *
 * There is deliberately NO placeholder default. A hardcoded fallback domain does not
 * degrade quietly — it asserts to every crawler that the canonical URL, the sitemap
 * location and the organization all live somewhere the app is not served from, which
 * is simply false. When the origin is unknown the app says nothing about it: noindex,
 * no sitemap, no absolute URLs (see layout.tsx / robots.ts / sitemap.ts).
 *
 * NEXT_PUBLIC_* is inlined at build time, so in Docker this must arrive as a build arg
 * (infra/Dockerfile.web), never as runtime container env.
 */
const rawSiteUrl = process.env.NEXT_PUBLIC_SITE_URL?.trim();
export const SITE_URL: string | null = rawSiteUrl ? rawSiteUrl.replace(/\/+$/, "") : null;

/**
 * Absolute URL for a path when the origin is known, otherwise `undefined` so callers
 * can omit the field entirely rather than emit a guess.
 */
export function absoluteUrl(path = "/"): string | undefined {
  if (!SITE_URL) return undefined;
  return path === "/" ? SITE_URL : `${SITE_URL}${path}`;
}

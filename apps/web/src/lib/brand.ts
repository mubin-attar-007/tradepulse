/** Single source of truth for product branding — import these instead of hardcoding the name. */
export const BRAND_NAME = "TradePulse";
export const BRAND_TAGLINE = "AI-Powered Trading Intelligence";
export const BRAND_DESCRIPTION =
  "Build, analyze, backtest, and automate trading strategies with institutional-grade analytics and AI — for US equities and crypto.";
/**
 * Canonical public origin (no trailing slash). Used for metadata, robots, and
 * sitemap. Env-driven so the real origin is injected at deploy time; the default
 * is a placeholder for local builds (do NOT rely on it in production).
 */
export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://tradepulse.app";

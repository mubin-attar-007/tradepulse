/**
 * Symbol <-> public-URL-slug mapping for the per-ticker SEO pages.
 *
 * The backend (`public_router._normalize_slug`) maps a hyphen back to the crypto
 * pair separator (`btc-usd` -> `BTC/USD`) and matches case-insensitively, so the
 * canonical public slug is the lowercased symbol with `/` replaced by `-`:
 *   "AAPL"    -> "aapl"
 *   "BTC/USD" -> "btc-usd"
 */
export function symbolToSlug(symbol: string): string {
  return symbol.replace(/\//g, "-").toLowerCase();
}

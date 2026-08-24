import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/brand";

// The proxy matcher excludes robots.txt/sitemap.xml, so this route serves directly.
// Crawlers get the marketing/docs surface; authenticated app + API stay unindexed.
export default function robots(): MetadataRoute.Robots {
  // Origin unknown (NEXT_PUBLIC_SITE_URL unset): we cannot name our own canonical
  // host, so we decline indexing outright instead of publishing a sitemap URL and a
  // `Host:` line pointing at a domain this build is not served from.
  if (!SITE_URL) {
    return { rules: { userAgent: "*", disallow: "/" } };
  }

  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // /markets/<ticker> is intentionally allowed — the public per-ticker SEO pages
      // live there. Everything session-gated is listed; keep this in sync with the
      // (app) route group so a new authed screen is never quietly crawlable.
      disallow: [
        "/api/",
        "/account",
        "/alerts",
        "/backtests",
        "/calculator",
        "/chart",
        "/dashboard",
        "/paper",
        "/strategies",
      ],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}

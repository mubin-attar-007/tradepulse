import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/brand";

// The proxy matcher excludes robots.txt/sitemap.xml, so this route serves directly.
// Crawlers get the marketing/docs surface; authenticated app + API stay unindexed.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // /markets is intentionally allowed — the public per-ticker SEO pages live there.
      disallow: ["/api/", "/dashboard", "/account", "/backtests", "/chart", "/paper", "/strategies"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}

import type { MetadataRoute } from "next";

import { api } from "@/lib/api/client";
import { SITE_URL } from "@/lib/brand";
import { symbolToSlug } from "@/lib/markets/slug";

// Publicly reachable, indexable surfaces: the marketing landing, the methodology
// docs, the sign-in entry, and one entry per public per-ticker page. The ticker
// list is fetched from the public API — if the backend is unreachable at build
// time we degrade to the static surfaces rather than fail the build.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const lastModified = new Date();

  let tickerEntries: MetadataRoute.Sitemap = [];
  try {
    const instruments = await api.publicMarkets({ cache: "no-store" });
    tickerEntries = instruments.map((i) => ({
      url: `${SITE_URL}/markets/${symbolToSlug(i.ticker)}`,
      lastModified,
      changeFrequency: "daily",
      priority: 0.7,
    }));
  } catch {
    // Backend unavailable (e.g. `next build` with no API running) — ship the
    // static surfaces only.
  }

  return [
    {
      url: SITE_URL,
      lastModified,
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${SITE_URL}/methodology`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      url: `${SITE_URL}/login`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.5,
    },
    ...tickerEntries,
  ];
}

import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/brand";

// Only publicly reachable, indexable surfaces — the marketing landing, the
// methodology docs, and the sign-in entry. Authenticated app routes are gated
// and intentionally omitted.
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
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
  ];
}

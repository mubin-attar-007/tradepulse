import type { MetadataRoute } from "next";

import { BRAND_DESCRIPTION, BRAND_NAME, BRAND_TAGLINE } from "@/lib/brand";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${BRAND_NAME} — ${BRAND_TAGLINE}`,
    short_name: BRAND_NAME,
    description: BRAND_DESCRIPTION,
    start_url: "/dashboard",
    display: "standalone",
    background_color: "#07090d",
    theme_color: "#07090d",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }],
  };
}

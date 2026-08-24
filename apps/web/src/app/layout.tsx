import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Providers } from "@/components/providers";
import { BRAND_DESCRIPTION, BRAND_NAME, BRAND_TAGLINE, SITE_URL } from "@/lib/brand";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const TITLE = `${BRAND_NAME} — ${BRAND_TAGLINE}`;

export const metadata: Metadata = {
  // Resolves relative URLs (canonical, OG/Twitter images from opengraph-image.tsx).
  // With no configured origin we fall back to localhost — an unmistakable "this build
  // was not told where it lives" rather than a plausible-looking wrong domain — and
  // pair it with noindex below so nothing acts on it. See lib/brand.ts.
  metadataBase: new URL(SITE_URL ?? "http://localhost:3000"),
  title: {
    default: TITLE,
    template: `%s · ${BRAND_NAME}`,
  },
  description: BRAND_DESCRIPTION,
  applicationName: BRAND_NAME,
  // Inherited by every route unless a page overrides it: an origin-less build must not
  // invite indexing of URLs it cannot name correctly.
  robots: SITE_URL ? undefined : { index: false, follow: false },
  openGraph: {
    type: "website",
    siteName: BRAND_NAME,
    title: TITLE,
    description: BRAND_DESCRIPTION,
    ...(SITE_URL ? { url: SITE_URL } : {}),
    // opengraph-image.tsx supplies the og:image tags automatically.
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: BRAND_DESCRIPTION,
  },
};

export const viewport: Viewport = { themeColor: "#07090d" };

// Set the theme before paint to avoid a flash of the wrong palette.
const THEME_INIT =
  "try{if(localStorage.theme==='light')document.documentElement.classList.add('light')}catch(e){}";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="min-h-full bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

import { ImageResponse } from "next/og";

import { BRAND_NAME } from "@/lib/brand";

// Branded 1200x630 social card. Rendered by satori: inline styles only, explicit
// display:flex on any element with >1 child, system fonts, no network fetches.
export const alt = `${BRAND_NAME} — honest, look-ahead-free backtesting`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Palette pulled from globals.css (dark theme) so the card matches the app.
const BG = "#07090d";
const FG = "#e7ebf0";
const MUTED = "#8b95a4";
const BORDER = "#1e2632";
const ACCENT_FROM = "#4f8cff";
const ACCENT_TO = "#7c5cff";
const GRADIENT = `linear-gradient(135deg, ${ACCENT_FROM} 0%, ${ACCENT_TO} 100%)`;

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: BG,
          padding: "80px",
          fontFamily: "system-ui, sans-serif",
          position: "relative",
        }}
      >
        {/* Ambient brand glow, echoing the landing hero. */}
        <div
          style={{
            position: "absolute",
            top: "-260px",
            left: "50%",
            width: "900px",
            height: "600px",
            transform: "translateX(-50%)",
            background:
              "radial-gradient(50% 50% at 50% 50%, rgba(124,92,255,0.22), rgba(7,9,13,0))",
            display: "flex",
          }}
        />

        {/* Wordmark: pulse mark + brand name */}
        <div style={{ display: "flex", alignItems: "center", gap: "22px" }}>
          <svg width="72" height="72" viewBox="0 0 32 32" fill="none">
            <defs>
              <linearGradient
                id="pulse"
                x1="0"
                y1="0"
                x2="32"
                y2="32"
                gradientUnits="userSpaceOnUse"
              >
                <stop offset="0" stopColor={ACCENT_FROM} />
                <stop offset="1" stopColor={ACCENT_TO} />
              </linearGradient>
            </defs>
            <rect width="32" height="32" rx="7" fill="#0e1219" />
            <path
              d="M5 19h5l3-8 4 12 3-8h7"
              stroke="url(#pulse)"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span
            style={{
              fontSize: "44px",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: FG,
            }}
          >
            {BRAND_NAME}
          </span>
        </div>

        {/* Headline + tagline */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              fontSize: "80px",
              fontWeight: 700,
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
              color: FG,
            }}
          >
            Honest, look-ahead-free
          </div>
          <div
            style={{
              display: "flex",
              fontSize: "80px",
              fontWeight: 700,
              lineHeight: 1.05,
              letterSpacing: "-0.03em",
              backgroundImage: GRADIENT,
              backgroundClip: "text",
              WebkitBackgroundClip: "text",
              color: "transparent",
              marginTop: "6px",
            }}
          >
            backtesting.
          </div>
          <div
            style={{
              display: "flex",
              fontSize: "30px",
              lineHeight: 1.35,
              color: MUTED,
              marginTop: "28px",
              maxWidth: "900px",
            }}
          >
            Net of commission &amp; slippage, measured against buy &amp; hold — every
            result reproducible. For US equities and crypto.
          </div>
        </div>

        {/* Footer strip */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "16px",
            fontSize: "24px",
            color: MUTED,
            borderTop: `1px solid ${BORDER}`,
            paddingTop: "28px",
          }}
        >
          <span style={{ display: "flex", color: FG, fontWeight: 600 }}>
            AI-Powered Trading Intelligence
          </span>
          <span style={{ display: "flex" }}>·</span>
          <span style={{ display: "flex" }}>Not investment advice</span>
        </div>
      </div>
    ),
    { ...size },
  );
}

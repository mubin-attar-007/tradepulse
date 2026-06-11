import { ImageResponse } from "next/og";

// Same pulse mark as icon.svg, rendered at Apple touch-icon size. iOS applies its
// own corner mask, so the background stays full-bleed.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#07090d",
        }}
      >
        <svg width="128" height="128" viewBox="0 0 32 32" fill="none">
          <defs>
            <linearGradient id="pulse" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
              <stop offset="0" stopColor="#4f8cff" />
              <stop offset="1" stopColor="#7c5cff" />
            </linearGradient>
          </defs>
          <path
            d="M5 19h5l3-8 4 12 3-8h7"
            stroke="url(#pulse)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
    ),
    { ...size },
  );
}

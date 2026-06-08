import type { NextConfig } from "next";

// Proxy /api/* to the FastAPI backend so the browser only ever talks to the web
// origin. This keeps session/CSRF cookies same-origin (readable + sent) in dev,
// mirroring the Caddy reverse-proxy setup used in production.
const API_TARGET = process.env.API_PROXY_TARGET ?? "http://localhost:8080";

// Content-Security-Policy at the web layer (the API layer/Caddy set their own headers).
// 'unsafe-inline' is required for the Next runtime + the theme-init inline script + Tailwind;
// 'unsafe-eval' is intentionally NOT allowed. connect-src includes ws/wss for the market-data
// WebSocket; the API is same-origin via the /api rewrite.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  "font-src 'self' data:",
  "connect-src 'self' ws: wss:",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
];

const nextConfig: NextConfig = {
  output: "standalone", // self-contained server bundle for the production Docker image
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_TARGET}/:path*` }];
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;

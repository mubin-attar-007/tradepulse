import type { NextConfig } from "next";

// Proxy /api/* to the FastAPI backend so the browser only ever talks to the web
// origin. This keeps session/CSRF cookies same-origin (readable + sent) in dev,
// mirroring the Caddy reverse-proxy setup used in production.
const API_TARGET = process.env.API_PROXY_TARGET ?? "http://localhost:8080";

const nextConfig: NextConfig = {
  output: "standalone", // self-contained server bundle for the production Docker image
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_TARGET}/:path*` }];
  },
};

export default nextConfig;

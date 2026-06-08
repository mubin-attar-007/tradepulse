// Client-side instrumentation (Next.js 16 `instrumentation-client` file convention).
// Runs after the HTML document loads and before React hydration. See
// node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/instrumentation-client.md
//
// DSN-gated: a no-op unless NEXT_PUBLIC_SENTRY_DSN is set, so local/dev and any
// environment without a DSN ships zero Sentry network traffic.
import * as Sentry from "@sentry/nextjs";

if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  Sentry.init({
    dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
    // Do not send PII (IP addresses, headers, cookies, request bodies, etc.).
    sendDefaultPii: false,
    // Sample 10% of transactions for performance tracing.
    tracesSampleRate: 0.1,
  });
}

// Next.js 16 router-navigation hook. Sentry's client SDK exports a ready-made
// handler that records navigation transitions; the build is verified by typecheck.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;

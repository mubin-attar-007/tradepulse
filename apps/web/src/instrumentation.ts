// Server-side instrumentation (Next.js 16 `instrumentation` file convention).
// `register()` runs once per server instance; Next calls it in every runtime, so
// runtime-specific code is gated on process.env.NEXT_RUNTIME. See
// node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/instrumentation.md
//
// DSN-gated: a no-op unless SENTRY_DSN (or NEXT_PUBLIC_SENTRY_DSN) is set.
import * as Sentry from "@sentry/nextjs";

export async function register() {
  const dsn = process.env.SENTRY_DSN ?? process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return;

  if (process.env.NEXT_RUNTIME === "nodejs" || process.env.NEXT_RUNTIME === "edge") {
    Sentry.init({
      dsn,
      // Do not send PII (IP addresses, headers, cookies, request bodies, etc.).
      sendDefaultPii: false,
      // Sample 10% of transactions for performance tracing.
      tracesSampleRate: 0.1,
    });
  }
}

// Next.js 16 server-error hook: forwards captured request errors to Sentry.
export const onRequestError = Sentry.captureRequestError;

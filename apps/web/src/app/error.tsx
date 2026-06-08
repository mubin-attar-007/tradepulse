"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

// Next.js 16: the recovery prop is `unstable_retry` (re-fetches + re-renders the segment),
// not `reset`. See node_modules/next/dist/docs/.../file-conventions/error.md.
export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    // DSN-gated upstream: captureException is a no-op until Sentry.init runs.
    Sentry.captureException(error);
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 px-6 text-center">
      <h2 className="text-xl font-semibold">Something went wrong</h2>
      <p className="text-sm opacity-70">
        An unexpected error occurred. Try again, and reload the page if it persists.
      </p>
      <button
        onClick={() => unstable_retry()}
        className="rounded-md border px-4 py-2 text-sm font-medium transition hover:opacity-80"
      >
        Try again
      </button>
    </div>
  );
}

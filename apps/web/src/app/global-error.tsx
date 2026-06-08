"use client";

import { useEffect } from "react";

// Global error boundary for the root layout. Must render its own <html>/<body>.
// Next.js 16 recovery prop is `unstable_retry`.
export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
        <h2 className="text-xl font-semibold">Something went wrong</h2>
        <p className="text-sm opacity-70">A critical error occurred. Please reload the page.</p>
        <button
          onClick={() => unstable_retry()}
          className="rounded-md border px-4 py-2 text-sm font-medium transition hover:opacity-80"
        >
          Try again
        </button>
      </body>
    </html>
  );
}

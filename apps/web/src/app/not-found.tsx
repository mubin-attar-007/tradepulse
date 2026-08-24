import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { BRAND_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

/**
 * Branded 404. The public per-ticker pages call `notFound()` for unknown slugs, and those
 * URLs are crawlable and linkable — without this, an unrecognised ticker rendered Next's
 * unstyled default page with none of the product's chrome or disclosures.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border/60">
        <div className="mx-auto flex h-16 max-w-4xl items-center px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="h-6 w-6 rounded-md gradient-brand" />
            <span className="font-semibold tracking-tight">{BRAND_NAME}</span>
          </Link>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col items-center justify-center px-6 py-20 text-center">
        <p className="text-sm font-medium text-primary">404</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">
          We don&apos;t have a page here
        </h1>
        <p className="mt-4 max-w-md text-muted-foreground">
          The link may be out of date, or the ticker may not be one of the instruments this
          deployment tracks.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link href="/" className={cn(buttonVariants({ size: "lg" }))}>
            Back to home
          </Link>
          <Link
            href="/methodology"
            className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
          >
            Methodology
          </Link>
        </div>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto max-w-4xl px-6 py-8 text-center text-sm text-muted-foreground">
          Delayed data. Hypothetical results. Not investment advice.
        </div>
      </footer>
    </div>
  );
}

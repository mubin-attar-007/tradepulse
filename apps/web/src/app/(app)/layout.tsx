import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { ChartAttribution } from "@/components/chart-attribution";

// Kept in sync with proxy.ts — the cookie names that signal a session is present.
const SESSION_COOKIES = ["session", "__Host-session"];

export default async function AppLayout({ children }: { children: ReactNode }) {
  // Defense-in-depth (B5): the proxy already gates the (app) group on session-cookie
  // presence, but guard here too so a routing/config regression can't leak the private
  // shell to logged-out users. Real authorization is still enforced by the API.
  const cookieStore = await cookies();
  if (!SESSION_COOKIES.some((c) => cookieStore.has(c))) {
    redirect("/login");
  }

  return (
    <div className="flex min-h-screen">
      {/* Sighted keyboard users otherwise tab through the whole sidebar and topbar on
          every route before reaching content. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppTopbar />
        <main id="main-content" className="flex-1 animate-fade-up p-4 md:p-6">
          {children}
        </main>
        {/* Standing disclosure for the authed shell: everything inside it is simulated,
            prices are delayed, and the charting library's licence requires attribution. */}
        <footer className="border-t border-border px-4 py-4 text-xs text-muted-foreground md:px-6">
          <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
            <span>
              Delayed market data · simulated results · not investment advice. Real-money trading
              is not enabled.
            </span>
            <ChartAttribution />
          </div>
        </footer>
      </div>
    </div>
  );
}

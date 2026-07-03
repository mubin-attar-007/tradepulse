import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { AppSidebar } from "@/components/app-sidebar";
import { AppTopbar } from "@/components/app-topbar";

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
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppTopbar />
        <main className="flex-1 animate-fade-up p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}

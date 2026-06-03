import Link from "next/link";
import type { ReactNode } from "react";

import { UserMenu } from "@/components/user-menu";

const NAV: { label: string; href?: string }[] = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Markets", href: "/markets" },
  { label: "Strategies", href: "/strategies" },
  { label: "Backtests", href: "/backtests" },
  { label: "Paper Trading", href: "/paper" },
  { label: "Portfolio" },
];

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-[220px_1fr]">
      <aside className="border-r border-border bg-card p-4">
        <div className="mb-6 px-2 text-lg font-semibold">Trading Platform</div>
        <nav className="flex flex-col gap-1">
          {NAV.map((item) =>
            item.href ? (
              <Link
                key={item.label}
                href={item.href}
                className="rounded-md px-3 py-2 text-sm hover:bg-muted"
              >
                {item.label}
              </Link>
            ) : (
              <span
                key={item.label}
                className="flex items-center justify-between rounded-md px-3 py-2 text-sm text-muted-foreground"
              >
                {item.label}
                <span className="text-[10px] uppercase tracking-wide">soon</span>
              </span>
            ),
          )}
        </nav>
      </aside>
      <div className="flex flex-col">
        <header className="flex h-14 items-center justify-between border-b border-border px-6">
          <span className="text-sm text-muted-foreground">Personal · Paper</span>
          <UserMenu />
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

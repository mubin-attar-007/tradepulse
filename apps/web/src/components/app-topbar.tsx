"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";

import { GlobalSearch } from "@/components/global-search";
import { MarketStatus } from "@/components/market-status";
import { MobileNav } from "@/components/mobile-nav";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { BRAND_NAME } from "@/lib/brand";

export function AppTopbar() {
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center gap-4 border-b border-border bg-background/80 px-4 backdrop-blur md:px-6">
      <MobileNav />
      {/* Compact brand mark — the sidebar (and its header) is hidden below md. */}
      <div className="flex items-center gap-2 md:hidden">
        <div className="h-5 w-5 rounded-md gradient-brand" />
        <span className="text-sm font-semibold tracking-tight">{BRAND_NAME}</span>
      </div>
      <GlobalSearch />
      <div className="ml-auto flex items-center gap-1.5">
        <MarketStatus />
        <Link
          href="/strategies"
          aria-label="Generate a strategy with AI"
          title="Generate a strategy with AI"
          className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Sparkles size={16} />
        </Link>
        <ThemeToggle />
        <div className="ml-1 border-l border-border pl-2">
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

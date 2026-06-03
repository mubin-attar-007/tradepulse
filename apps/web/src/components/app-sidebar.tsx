"use client";

import {
  Bell,
  Boxes,
  CandlestickChart,
  FileText,
  Filter,
  FlaskConical,
  LayoutDashboard,
  LineChart,
  type LucideIcon,
  PlayCircle,
  Radio,
  Settings,
  Sparkles,
  Star,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type Item = { label: string; href?: string; icon: LucideIcon };

const NAV: { title: string; items: Item[] }[] = [
  {
    title: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Markets", href: "/markets", icon: LineChart },
      { label: "Watchlists", icon: Star },
    ],
  },
  {
    title: "Research",
    items: [
      { label: "Charts", icon: CandlestickChart },
      { label: "Screeners", icon: Filter },
      { label: "AI Insights", icon: Sparkles },
    ],
  },
  {
    title: "Trade",
    items: [
      { label: "Strategies", href: "/strategies", icon: Boxes },
      { label: "Backtesting", href: "/backtests", icon: FlaskConical },
      { label: "Paper Trading", href: "/paper", icon: PlayCircle },
      { label: "Live Trading", icon: Radio },
    ],
  },
  {
    title: "Manage",
    items: [
      { label: "Portfolio", icon: Wallet },
      { label: "Alerts", icon: Bell },
      { label: "Reports", icon: FileText },
      { label: "Settings", icon: Settings },
    ],
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card/50 md:flex">
      <div className="flex h-14 items-center gap-2.5 border-b border-border px-5">
        <div className="h-6 w-6 rounded-md gradient-brand" />
        <span className="text-sm font-semibold tracking-tight">Quanta</span>
      </div>
      <nav className="flex-1 space-y-6 overflow-y-auto p-3">
        {NAV.map((group) => (
          <div key={group.title}>
            <div className="px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {group.title}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = item.icon;
                const active =
                  item.href && (pathname === item.href || pathname.startsWith(`${item.href}/`));
                return item.href ? (
                  <Link
                    key={item.label}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                      active
                        ? "bg-primary/10 font-medium text-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground",
                    )}
                  >
                    <Icon size={16} />
                    {item.label}
                  </Link>
                ) : (
                  <span
                    key={item.label}
                    className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground/40"
                  >
                    <Icon size={16} />
                    {item.label}
                    <span className="ml-auto text-[9px] uppercase tracking-wide">soon</span>
                  </span>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}

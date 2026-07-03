"use client";

import {
  Bell,
  Boxes,
  Calculator,
  FlaskConical,
  LayoutDashboard,
  LineChart,
  type LucideIcon,
  PlayCircle,
  Radio,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type Item = { label: string; href?: string; icon: LucideIcon; gated?: boolean };

const NAV: { title: string; items: Item[] }[] = [
  {
    title: "Overview",
    items: [
      { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { label: "Markets", href: "/markets", icon: LineChart },
    ],
  },
  {
    title: "Trade",
    items: [
      { label: "Strategies", href: "/strategies", icon: Boxes },
      { label: "Backtesting", href: "/backtests", icon: FlaskConical },
      { label: "Paper Trading", href: "/paper", icon: PlayCircle },
      { label: "Calculator", href: "/calculator", icon: Calculator },
      { label: "Alerts", href: "/alerts", icon: Bell },
      // Deliberately gated behind hard risk controls — not an unbuilt "coming soon".
      { label: "Live Trading", icon: Radio, gated: true },
    ],
  },
];

/** Grouped nav list shared by the desktop sidebar and the mobile drawer. */
export function AppNavList({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
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
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active
                      ? "relative bg-primary/10 font-medium text-primary before:absolute before:left-0 before:top-1/2 before:h-4 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon size={16} />
                  {item.label}
                </Link>
              ) : (
                <span
                  key={item.label}
                  title="Real-money trading is intentionally gated behind hard risk controls."
                  className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground/70"
                >
                  <Icon size={16} />
                  {item.label}
                  <span className="ml-auto rounded border border-border px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-muted-foreground">
                    Gated
                  </span>
                </span>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

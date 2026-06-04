"use client";

import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { api } from "@/lib/api/client";

type Result = { key: string; label: string; sub: string; href: string };

/** Real client-side command search over seeded instruments + the user's strategies
 * (both already cached by TanStack Query elsewhere, so this adds no extra round-trips
 * on a warm cache). Selecting a result navigates to the chart or strategies screen. */
export function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const instruments = useQuery({ queryKey: ["instruments"], queryFn: () => api.instruments() });
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: () => api.strategies() });

  const results = useMemo<Result[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const inst = (instruments.data ?? [])
      .filter((i) => i.symbol.toLowerCase().includes(q) || (i.name ?? "").toLowerCase().includes(q))
      .map((i) => ({
        key: `i-${i.id}`,
        label: i.symbol,
        sub: i.name ?? i.asset_class,
        href: `/chart/${i.id}`,
      }));
    const strat = (strategies.data ?? [])
      .filter((s) => s.name.toLowerCase().includes(q))
      .map((s) => ({ key: `s-${s.id}`, label: s.name, sub: "strategy", href: "/strategies" }));
    return [...inst, ...strat].slice(0, 8);
  }, [query, instruments.data, strategies.data]);

  function go(href: string) {
    setOpen(false);
    setQuery("");
    router.push(href);
  }

  return (
    <div className="relative hidden w-full max-w-md sm:block">
      <Search
        size={15}
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
      />
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && results[0]) go(results[0].href);
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Search markets, strategies…"
        className="h-9 w-full rounded-lg border border-border bg-muted/40 pl-9 pr-3 text-sm outline-none transition focus:ring-2 focus:ring-ring"
      />
      {open && results.length > 0 ? (
        <ul className="absolute inset-x-0 top-11 z-20 overflow-hidden rounded-lg border border-border bg-card shadow-lg">
          {results.map((r) => (
            <li key={r.key}>
              <button
                type="button"
                // onMouseDown fires before the input's blur, so the click isn't cancelled.
                onMouseDown={(e) => {
                  e.preventDefault();
                  go(r.href);
                }}
                className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <span className="font-medium">{r.label}</span>
                <span className="truncate text-xs text-muted-foreground">{r.sub}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

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
function useSearchResults(query: string): Result[] {
  const instruments = useQuery({ queryKey: ["instruments"], queryFn: () => api.instruments() });
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: () => api.strategies() });

  return useMemo<Result[]>(() => {
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
}

function ResultsList({ results, onSelect }: { results: Result[]; onSelect: (href: string) => void }) {
  return (
    <ul className="overflow-hidden rounded-lg border border-border bg-card shadow-lg">
      {results.map((r) => (
        <li key={r.key}>
          <button
            type="button"
            // onMouseDown fires before the input's blur, so the click isn't cancelled.
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(r.href);
            }}
            className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
          >
            <span className="font-medium">{r.label}</span>
            <span className="truncate text-xs text-muted-foreground">{r.sub}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function DesktopSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const results = useSearchResults(query);

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
        <div className="absolute inset-x-0 top-11 z-20">
          <ResultsList results={results} onSelect={go} />
        </div>
      ) : null}
    </div>
  );
}

function MobileSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const results = useSearchResults(query);

  function close() {
    setOpen(false);
    setQuery("");
  }

  function go(href: string) {
    close();
    router.push(href);
  }

  return (
    <div className="sm:hidden">
      <button
        type="button"
        aria-label="Search"
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
        className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Search size={16} />
      </button>
      {open ? (
        <div className="fixed inset-x-0 top-14 z-20 border-b border-border bg-background p-3">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && results[0]) go(results[0].href);
              if (e.key === "Escape") close();
            }}
            placeholder="Search markets, strategies…"
            className="h-9 w-full rounded-lg border border-border bg-muted/40 px-3 text-sm outline-none transition focus:ring-2 focus:ring-ring"
          />
          {results.length > 0 ? (
            <div className="mt-2">
              <ResultsList results={results} onSelect={go} />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function GlobalSearch() {
  return (
    <>
      <DesktopSearch />
      <MobileSearch />
    </>
  );
}

"use client";

import { useEffect, useState } from "react";

/**
 * Real market-status pill. Crypto is 24/7; US equities follow the NYSE regular
 * session (09:30–16:00 America/New_York, Mon–Fri). Computed from the live clock —
 * not hardcoded. (Holidays/half-days are not yet modelled; that needs the calendar
 * table — tracked as a follow-up.)
 */
function equitiesOpen(now: Date): boolean {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  const weekday = get("weekday");
  if (weekday === "Sat" || weekday === "Sun") return false;
  const minutes = Number(get("hour")) * 60 + Number(get("minute"));
  return minutes >= 9 * 60 + 30 && minutes < 16 * 60;
}

export function MarketStatus() {
  const [open, setOpen] = useState<boolean | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setOpen(equitiesOpen(new Date()));
    const id = setInterval(() => setOpen(equitiesOpen(new Date())), 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="hidden items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground lg:flex">
      <span
        className={`h-1.5 w-1.5 rounded-full motion-reduce:animate-none ${open ? "animate-pulse bg-profit" : "bg-muted-foreground"}`}
      />
      Crypto 24/7 · Equities {open === null ? "—" : open ? "open" : "closed"}
    </span>
  );
}

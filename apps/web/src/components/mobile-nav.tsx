"use client";

import { Menu, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AppNavList } from "@/components/app-nav";
import { BRAND_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

/** Hamburger trigger + slide-in navigation drawer for viewports under `md`. */
export function MobileNav() {
  // Remounting on route change resets the drawer to closed — this covers
  // back/forward navigation without a setState-in-effect.
  const pathname = usePathname();
  return <MobileNavDrawer key={pathname} />;
}

function MobileNavDrawer() {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // While open: Escape closes, body scroll is locked, and focus moves to the
  // close button. On close, focus returns to the hamburger trigger.
  useEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.documentElement.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.documentElement.style.overflow = "";
      trigger?.focus();
    };
  }, [open]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label="Open navigation"
        aria-expanded={open}
        aria-controls="mobile-nav"
        onClick={() => setOpen(true)}
        className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
      >
        <Menu size={18} />
      </button>
      <div className={cn("fixed inset-0 z-50 md:hidden", !open && "pointer-events-none")}>
        <div
          aria-hidden="true"
          onClick={() => setOpen(false)}
          className={cn(
            "absolute inset-0 bg-black/60 transition-all motion-reduce:transition-none",
            open ? "visible opacity-100" : "invisible opacity-0",
          )}
        />
        <div
          id="mobile-nav"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation"
          className={cn(
            "fixed inset-y-0 left-0 flex w-72 flex-col border-r border-border bg-card transition-all duration-200 ease-out motion-reduce:transition-none",
            open ? "visible translate-x-0" : "invisible -translate-x-full",
          )}
        >
          <div className="flex h-14 shrink-0 items-center gap-2.5 border-b border-border px-5">
            <div className="h-6 w-6 rounded-md gradient-brand" />
            <span className="text-sm font-semibold tracking-tight">{BRAND_NAME}</span>
            <button
              ref={closeRef}
              type="button"
              aria-label="Close navigation"
              onClick={() => setOpen(false)}
              className="ml-auto rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X size={16} />
            </button>
          </div>
          <AppNavList onNavigate={() => setOpen(false)} />
        </div>
      </div>
    </>
  );
}

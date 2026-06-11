"use client";

import { X } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "default";
type ToastInput = { description: string; variant?: ToastVariant };
type Toast = { id: number; description: string; variant: ToastVariant };

const ToastContext = createContext<{ toast: (input: ToastInput) => void } | null>(null);

const AUTO_DISMISS_MS = 4500;

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>.");
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    ({ description, variant = "default" }: ToastInput) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev, { id, description, variant }]);
      setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.variant === "error" ? "alert" : "status"}
            aria-live={t.variant === "error" ? "assertive" : "polite"}
            className={cn(
              "flex w-72 items-start gap-2 rounded-lg border bg-elevated p-3 text-sm shadow-lg motion-safe:animate-fade-up",
              t.variant === "success" && "border-profit/40",
              t.variant === "error" && "border-loss/40",
              t.variant === "default" && "border-border",
            )}
          >
            <span className="flex-1">{t.description}</span>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(t.id)}
              className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

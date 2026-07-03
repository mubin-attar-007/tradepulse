import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * A labelled numeric input in the same CVA + cn() + CSS-var style as the other
 * ui/ primitives. It renders `<input type="number">` (with an optional prefix /
 * suffix affix, e.g. "$" or "%") and is fully controlled by the parent — this is
 * pure form input, never money math, which stays server-side (invariant #2).
 */
const inputVariants = cva(
  "w-full rounded-md border bg-background text-sm tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none",
  {
    variants: {
      invalid: {
        true: "border-loss/60",
        false: "border-border",
      },
    },
    defaultVariants: { invalid: false },
  },
);

export type NumberInputProps = Omit<ComponentProps<"input">, "type"> &
  VariantProps<typeof inputVariants> & {
    label?: string;
    prefix?: string;
    suffix?: string;
    hint?: string;
  };

export function NumberInput({
  className,
  invalid,
  label,
  prefix,
  suffix,
  hint,
  id,
  ...props
}: NumberInputProps) {
  const inputId = id ?? props.name;
  return (
    <label htmlFor={inputId} className="block space-y-1.5">
      {label ? (
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
      ) : null}
      <span className="relative flex items-center">
        {prefix ? (
          <span className="pointer-events-none absolute left-3 text-sm text-muted-foreground">
            {prefix}
          </span>
        ) : null}
        <input
          id={inputId}
          type="number"
          inputMode="decimal"
          aria-invalid={invalid ?? undefined}
          className={cn(
            inputVariants({ invalid }),
            "h-10 px-3 py-2",
            prefix && "pl-7",
            suffix && "pr-8",
            className,
          )}
          {...props}
        />
        {suffix ? (
          <span className="pointer-events-none absolute right-3 text-sm text-muted-foreground">
            {suffix}
          </span>
        ) : null}
      </span>
      {hint ? <span className="text-[11px] text-muted-foreground/70">{hint}</span> : null}
    </label>
  );
}

export { inputVariants };

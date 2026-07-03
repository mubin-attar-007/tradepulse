import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

/**
 * A small on/off pill toggle in the same CVA + cn() + CSS-var style as the other
 * ui/ primitives. It is a controlled `<button role="switch">` (not a checkbox
 * input) so it composes with a color swatch and label inline on the indicator
 * panel. `pressed` drives the active styling; the parent owns the state.
 */
const toggleVariants = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      pressed: {
        true: "border-primary/40 bg-primary/10 text-primary",
        false: "border-border bg-transparent text-muted-foreground hover:bg-muted",
      },
    },
    defaultVariants: { pressed: false },
  },
);

export type ToggleProps = Omit<ComponentProps<"button">, "type"> &
  VariantProps<typeof toggleVariants> & { pressed?: boolean };

export function Toggle({ className, pressed = false, ...props }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={pressed}
      data-state={pressed ? "on" : "off"}
      className={cn(toggleVariants({ pressed }), className)}
      {...props}
    />
  );
}

export { toggleVariants };

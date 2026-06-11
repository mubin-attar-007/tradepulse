import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Formats with an explicit +/- sign so gains vs. losses don't rely on color alone. */
export function formatSigned(n: number, suffix = ""): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}${suffix}`;
}

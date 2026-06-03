/**
 * Minimal typed API client. Talks to the same-origin `/api/*` proxy (see
 * next.config.ts), so session/CSRF cookies are first-party. Response shapes are
 * sourced from the backend's OpenAPI schema (generated; drift-guarded in CI).
 */
import type { components } from "./schema";

export type User = components["schemas"]["UserOut"];

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (UNSAFE.has(method)) {
    const csrf = readCookie("csrf_token");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const res = await fetch(`${BASE}${path}`, { ...init, method, headers, credentials: "include" });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  csrf: () => apiFetch<{ csrf_token: string }>("/auth/csrf"),
  me: () => apiFetch<User>("/auth/me"),
  login: (email: string, password: string) =>
    apiFetch<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  register: (email: string, password: string, display_name: string | null) =>
    apiFetch<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    }),
  logout: () => apiFetch<{ status: string }>("/auth/logout", { method: "POST" }),
};

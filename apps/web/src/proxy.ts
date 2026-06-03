/**
 * Proxy (Next.js 16's renamed Middleware): a coarse auth gate.
 *
 * Redirects unauthenticated requests for app pages to /login based on session
 * cookie *presence* only — real authorization is enforced server-side by the
 * API (/auth/me). `/api/*` is excluded (it is reverse-proxied to the backend).
 */
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/", "/login"];
const SESSION_COOKIES = ["session", "__Host-session"];

export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  const hasSession = SESSION_COOKIES.some((c) => request.cookies.has(c));

  if (!isPublic && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  if (isPublic && hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/dashboard";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.svg).*)"],
};

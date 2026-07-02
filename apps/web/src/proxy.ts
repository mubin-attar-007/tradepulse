/**
 * Proxy (Next.js 16's renamed Middleware): a coarse auth gate.
 *
 * Redirects unauthenticated requests for app pages to /login based on session
 * cookie *presence* only — real authorization is enforced server-side by the
 * API (/auth/me). `/api/*` is excluded (it is reverse-proxied to the backend).
 */
import { NextResponse, type NextRequest } from "next/server";

// Reachable without a session.
const PUBLIC_PATHS = ["/", "/login", "/methodology", "/forgot-password", "/reset-password"];
// The subset that logged-in users should be bounced away from (login / marketing entry) into the
// app. Open docs like /methodology stay viewable whether or not you're signed in.
const AUTHED_REDIRECT_PATHS = ["/", "/login"];
const SESSION_COOKIES = ["session", "__Host-session"];

/** Only honor same-origin relative paths ("//host" and "/\host" are open redirects). */
function isSafeNext(next: string | null): next is string {
  return next !== null && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\");
}

export function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  const bounceWhenAuthed = AUTHED_REDIRECT_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
  const hasSession = SESSION_COOKIES.some((c) => request.cookies.has(c));

  if (!isPublic && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    // Remember where the user was headed so login can return them there.
    if (pathname !== "/") url.searchParams.set("next", pathname + request.nextUrl.search);
    return NextResponse.redirect(url);
  }
  if (bounceWhenAuthed && hasSession) {
    const next = request.nextUrl.searchParams.get("next");
    return NextResponse.redirect(
      new URL(isSafeNext(next) ? next : "/dashboard", request.nextUrl),
    );
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|manifest.webmanifest|icon|apple-icon|robots.txt|sitemap.xml|.*\\.svg).*)",
  ],
};

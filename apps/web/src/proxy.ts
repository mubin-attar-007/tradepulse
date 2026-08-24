/**
 * Proxy (Next.js 16's renamed Middleware): a coarse auth gate.
 *
 * Redirects unauthenticated requests for app pages to /login based on session
 * cookie *presence* only — real authorization is enforced server-side by the
 * API (/auth/me). `/api/*` is excluded (it is reverse-proxied to the backend).
 */
import { NextResponse, type NextRequest } from "next/server";

// Reachable without a session. NOTE: bare `/markets` is intentionally NOT here — it
// resolves to the AUTHED (app) markets shell and must stay gated (B5). Only the public
// per-ticker subtree `/markets/[ticker]` is crawlable, handled by the startsWith check
// in `proxy()` below.
const PUBLIC_PATHS = [
  "/",
  "/login",
  "/methodology",
  "/forgot-password",
  "/reset-password",
];
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
  // The public per-ticker pages live under `/markets/<ticker>`. Bare `/markets` is
  // the authed app shell, so match ONLY the subtree — never the exact path (B5).
  const isPublicMarket = pathname.startsWith("/markets/");
  const isPublic =
    isPublicMarket || PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  // `?reauth=1` is set by the API client when a request came back 401 (lib/api/client.ts).
  // The cookie is HttpOnly, so an EXPIRED session still counts as "present" here — without
  // this escape hatch the user bounces /login -> /dashboard -> 401 -> /login forever and can
  // never reach the form. Presence is not validity; this is where that distinction lands.
  //
  // Scoped to /login, because reaching the sign-in FORM is the entire job. Honouring the flag
  // on every AUTHED_REDIRECT_PATH also honours it on "/", so a signed-in user following any
  // link carrying `?reauth=1` lands on the marketing page instead of their dashboard.
  const wantsReauth =
    (pathname === "/login" || pathname.startsWith("/login/")) &&
    request.nextUrl.searchParams.has("reauth");
  const bounceWhenAuthed =
    !wantsReauth &&
    AUTHED_REDIRECT_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
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
    "/((?!api|_next/static|_next/image|favicon.ico|manifest.webmanifest|icon|apple-icon|opengraph-image|robots.txt|sitemap.xml|.*\\.svg).*)",
  ],
};

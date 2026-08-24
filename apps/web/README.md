# TradePulse web

Next.js 16 (App Router) frontend. Talks to the FastAPI backend exclusively through a **same-origin
`/api/*` rewrite**, so session and CSRF cookies stay first-party.

> This is not stock create-next-app. Read `AGENTS.md` before writing code — this Next version has
> breaking changes relative to most training data, and the local docs in
> `node_modules/next/dist/docs/` are the source of truth.

## Route map

| Path | Auth | Notes |
| --- | --- | --- |
| `/` | public | Landing. Includes the reference-backtest track record (server component). |
| `/methodology` | public | What we compute, and what we deliberately don't claim. |
| `/markets/[ticker]` | **public** | Crawlable per-ticker SEO pages: delayed price, chart, indicators, reference-strategy illustration, FAQ + JSON-LD. |
| `/login`, `/forgot-password`, `/reset-password` | public | `(auth)` group. |
| `/dashboard`, `/markets`, `/chart/[id]`, `/strategies`, `/backtests`, `/paper`, `/calculator`, `/alerts`, `/account` | session | `(app)` group behind the sidebar shell. |

Bare `/markets` is the **authed** listing; only the `/markets/<ticker>` subtree is public. That
distinction is enforced by a `startsWith("/markets/")` check in `src/proxy.ts` — do not add
`app/(app)/markets/[id]/page.tsx`, it would collide.

## Auth model

- `src/proxy.ts` (Next 16's renamed middleware) gates the `(app)` group on session-cookie
  **presence**; `(app)/layout.tsx` repeats the check server-side. Real authorization is the API's job.
- Presence is not validity. The cookie is HttpOnly, so an *expired* session still looks present —
  `src/lib/api/client.ts` turns any `401` into a redirect to `/login?reauth=1&next=…`, and the
  `reauth` flag is what stops the proxy bouncing that request straight back into the app.
- 401s on credential-submitting endpoints (login, register, change-password, delete, reset) are
  *not* redirected — there a 401 means "wrong password", and swallowing it would hide the message.

## Environment

See `.env.example`. The one rule worth internalising: **`NEXT_PUBLIC_*` is inlined at
`next build` time.** Setting it as runtime container env is too late and silently ships the
in-code fallback. In Docker these arrive as build args (`infra/Dockerfile.web`).

| Variable | Scope | Purpose |
| --- | --- | --- |
| `API_PROXY_TARGET` | server | Rewrite target for `/api/*`, and the origin server components use for public endpoints. |
| `NEXT_PUBLIC_API_BASE` | build | Client-side API base. `/api` (same-origin) in every normal setup. |
| `NEXT_PUBLIC_WS_URL` | build | Optional override. Leave **empty** when the WS is same-origin — the client derives `ws(s)://<origin>/api/market/ws`. |
| `NEXT_PUBLIC_SITE_URL` | build | Canonical origin. **Unset means "unknown"**: the app emits `noindex`, ships an empty sitemap, and omits absolute canonical/OG/JSON-LD URLs rather than asserting a domain it isn't served from. |
| `NEXT_PUBLIC_SENTRY_DSN` | build | Empty leaves the browser instrumentation a no-op. |

## Generated API client

`src/lib/api/schema.ts` is **generated** from the backend's OpenAPI contract — never hand-edit it.
Regenerate after any backend schema change:

```bash
npm run gen:api    # openapi-typescript ../../packages/contracts/openapi.json -> src/lib/api/schema.ts
```

CI has a drift guard, so a stale contract fails the build rather than diverging quietly.
`src/lib/api/client.ts` wraps it with the typed `api.*` surface, CSRF header attachment, and the
401 handling described above.

## Honesty invariants this UI must keep

These are product requirements, not style preferences:

1. **Money is never computed in the browser.** The API sends Decimal strings; the client formats
   them. No client-side P&L, no sums across records, no sizing or risk math — if a user could
   read it as an amount of money, it arrived from the server as a string. The single sanctioned
   derivation is the *display-only* underwater series in `components/backtest-results.tsx`
   (`drawdownSeries()`), which float-divides the server's own equity curve by its running peak to
   draw the drawdown chart's shape. It is geometry, never currency; the drawdown figure the user
   actually reads is `metrics.max_drawdown`, computed server-side. Adding a second exception
   needs the same test: it renders a shape, not a number anyone could quote.
2. **Every price carries provenance.** Polled prices render a `DELAYED` badge with a fetch time.
   `DataBadge`'s `LIVE` variant is intentionally unused — we do not have a live feed.
3. **Every simulated result sits under `<HypotheticalBanner/>`**, above the numbers, not as
   footnote fine print. Paper surfaces additionally carry a `PAPER` badge.
4. **Loading, empty, error and unauthenticated are four different states.** Rendering an API
   failure as "nothing here yet" states something false about the platform — use `<QueryError/>`.
5. **Marketing copy may not outrun the code.** Anything listed on `/methodology` under "what we
   deliberately don't claim" must not appear elsewhere in the present tense.

## Scripts

```bash
npm run dev        # next dev
npm run build      # next build (standalone output)
npm run lint       # eslint
npm run typecheck  # tsc --noEmit
```

There is currently **no frontend test suite** — CI runs lint, typecheck and build only.

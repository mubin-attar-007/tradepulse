# Claim Audit — TradePulse (product positioning & public claims)

**Audit date:** 2026-08-21
**Anchor commit:** `8b82368` (`feat(web): flagship pass — OHLC crosshair legend, trades pagination, a11y contrast`), branch `main`
**Scope:** every user-visible or crawler-visible assertion the product makes about itself — landing page, OG card, methodology page, public per-ticker SEO pages, FAQ/JSON-LD, in-app copy, README, SECURITY.md, ADRs, deploy docs, LICENSE, package metadata, and the public API surface that feeds them.

Every `file:line` reference below resolves against commit `8b82368` and can be re-checked with
`git show 8b82368:<path>`. Line numbers are pinned to that commit deliberately: the working tree was
being actively edited during this audit (see §1.3), so tree-relative line numbers would have been
stale before the document was finished.

---

## 1. Methodology

### 1.1 What was searched

| Surface | Files read |
|---|---|
| Marketing / SEO | `apps/web/src/app/page.tsx`, `opengraph-image.tsx`, `layout.tsx`, `manifest.ts`, `robots.ts`, `sitemap.ts`, `methodology/page.tsx`, `markets/[ticker]/page.tsx`, `markets/[ticker]/market-view.tsx`, `lib/brand.ts`, `lib/markets/faq.ts`, `components/faq-jsonld.tsx` |
| In-app copy | `components/track-record.tsx`, `backtest-results.tsx`, `signal-card.tsx`, `chart-workspace.tsx`, `public-chart.tsx`, `live-price.tsx`, `data-badge.tsx`, `hypothetical-banner.tsx`, `market-status.tsx`, `app-nav.tsx`, `(app)/dashboard/dashboard-view.tsx`, `(app)/paper/paper-view.tsx`, `(app)/calculator/calculator-view.tsx`, `(app)/strategies/strategies-view.tsx` |
| Backing code | `modules/backtesting/{engine,metrics,types,schemas,service,orchestration,compute}.py`, `modules/market_data/{public_router,reference_backtest,signal,streaming,repository,router,seed,schemas}.py`, `modules/strategies/spec.py`, `modules/ai/{service,prompts,schemas,router,budget}.py` + `providers/*`, `modules/trading/{live_router,live_gate,service,calc,schemas}.py`, `core/{config,ratelimit,security}.py`, `main.py`, `worker.py` |
| Docs / metadata | `README.md`, `apps/web/README.md`, `SECURITY.md`, `LICENSE`, `pyproject.toml`, `docs/DEPLOY*.md`, `docs/adr/000{2,4,5,8}-*.md`, `.github/workflows/ci.yml`, `.github/pull_request_template.md` |
| Tests | `apps/api/tests/test_backtest.py`, `test_market_data.py`, `test_streaming.py`, `test_ingestion.py`, `test_ai.py` |

### 1.2 How each claim was adjudicated

Every claim was traced to the code path that would have to be true for it to hold, and a verdict was
assigned from a fixed vocabulary:

| Verdict | Meaning |
|---|---|
| **verified** | The code does what the claim says. No change required. |
| **partially supported** | One half of a compound claim holds; the other does not, or holds only under a narrower condition than stated. |
| **unsupported** | No implementation exists for the asserted capability. |
| **contradictory** | The repository asserts the opposite elsewhere — often in the same file, or one click away in the UI. |
| **misleading without context** | Literally defensible, but reads to a lay visitor as a materially stronger claim than the code supports. |
| **blocked pending measurement** | Cannot be settled from source alone (needs network access or binary inspection). Recorded, not guessed. |

Two negative searches were run, and both came back clean — which is itself a finding:

- A case-insensitive repo-wide search for `open source` / `open-source` (excluding `node_modules`, `.venv`, `.next`, lockfiles) returns **zero** hits.
- A search for return-promissory vocabulary — `guaranteed`, `profitable`, `risk free`, `no risk`, `beat the market`, `outperform`, `alpha` (as a claim), `always wins` — returns **zero** marketing hits. The apparent matches are engineering-internal and are enumerated in §4.6.

### 1.3 Working-tree state at time of audit

The tree was **not** clean while this audit ran. `git status` showed ~24 modified files plus three
module renames, and file mtimes confirmed that `apps/web/src/app/page.tsx`, `opengraph-image.tsx`,
`lib/brand.ts` and `apps/api/app/modules/backtesting/metrics.py` were being edited **during** the
audit window. Three consequences for the reader:

1. The register in §3 describes commit `8b82368` — the same commit `BASELINE_VERIFICATION.md` records, and the last stable, reproducible reference point.
2. Three modules have since been relocated: `market_data/public_router.py`, `market_data/reference_backtest.py` and `market_data/signal.py` now live under `apps/api/app/modules/research/`. Baseline paths are used throughout §3; apply this mapping when navigating the current tree.
3. Several baseline defects have already been remediated in the uncommitted tree. They are **excluded from the register** to avoid re-work, and listed once here so the lead can confirm rather than re-investigate:

| Baseline defect | Remediation observed in working tree |
|---|---|
| `BRAND_TAGLINE = "AI-Powered Trading Intelligence"` (`brand.ts:3`) | Now `"Quantitative Research & Backtesting Workbench"`, with a docstring stating the tagline must name the workbench, never "trading intelligence" |
| `SITE_URL` falling back to the placeholder `https://tradepulse.app` (`brand.ts:11`) | `SITE_URL` is now `string \| null`; `layout.tsx` emits `robots: { index: false }` and `sitemap.ts` returns `[]` when the origin is unset |
| `profit_factor` returning gross dollar P&L when a run has no losing trade (`metrics.py:65`) | Returns `None`; `sample_size_notes()` explains the resulting "n/a" |
| 24/7 annualization constant applied to equities (`metrics.py:37`) | `periods_per_year(timeframe, calendar)` with `XNYS = 252 sessions × 390 min`; CAGR now derived from wall-clock elapsed time; Sharpe/Sortino/CAGR gated on sample-size floors |
| Zero-trade runs averaged into the track record as 0% win rate | `win_rate` is `None` with no trades, and the aggregate filters `None` before averaging |
| `entry_short` accepted, validated, then silently ignored by a long-only engine | Rejected at spec validation with an explicit engine-capability error |
| `time_of_day.timezone: "exchange"` silently evaluated in UTC | Bars converted via `astimezone(tod_zone)` before the window comparison |
| `ws://localhost:8080` inlined into the production bundle | WS URL derived from `window.location`; `NEXT_PUBLIC_*` passed as Docker build args |
| `universe` beyond `[0]` silently truncated | Rejected at spec validation |

One source finding was **refuted on verification and is dropped**: the assertion that the AI
prompt-injection surface is a distinct high-severity defect independent of the ungrounded `context`
dict. The injection risk is a consequence of the unconstrained `context` field (§4.5), not a separate
defect, and it is bounded — `/ai/strategy` output is schema-validated before it reaches the user, and
`/ai/explain` output is ephemeral client state that is never persisted nor shown to another user.

### 1.4 Limits of this audit

- No network calls were made. Demo liveness and the rendered content of committed screenshots are recorded as **blocked pending measurement**, not assumed.
- No code was executed. Behavioural claims are adjudicated by reading the code path. Execution results belong to `BASELINE_VERIFICATION.md`.
- Third-party data-licensing questions (Yahoo/yfinance, IEX, venue terms) are flagged where they intersect a public claim, but a legal opinion is out of scope.

---

## 2. Positioning assessment

### 2.1 Current positioning

At the anchor commit the product sells itself as **"AI-powered algorithmic trading intelligence"**
(`README.md:5`; `pyproject.toml:4` as "AI-powered algorithmic trading platform"; `brand.ts:3` as
"AI-Powered Trading Intelligence"). That string is not local — `brand.ts:3` propagates to the HTML
`<title>` (`apps/web/src/app/layout.tsx:11`), the PWA manifest name (`manifest.ts:7`), the landing
hero pill (`page.tsx:94`) and the OG card footer (`opengraph-image.tsx:146`). The hero paragraph adds
"Institutional-grade analytics" and "The terminal that respects your edge" (`page.tsx:102-103`), and
the closing CTA reads "Trade with an edge you can actually trust" (`page.tsx:181`).

### 2.2 Required positioning

The v2 target is an **evidence-driven agentic quant research platform**. Measured against that
target, the gap runs in three directions — and only one of them is a marketing problem.

**Direction 1 — "intelligence" vs. "workbench" (overclaim; must change).**
The current claim positions the product as a *source* of trading views. The code is a place to *test
your own*. `apps/api/app/modules/ai/service.py:39-59` is a natural-language → `StrategySpec`
translator with a validate-and-repair loop; `explain_backtest` (`:61-70`) is a narration call.
Neither produces a forecast, a ranked opportunity, or a market view. Nothing in the repository ranks,
screens, or recommends an instrument. "Intelligence" asserts an output the system does not generate.

**Direction 2 — "algorithmic trading" vs. "cannot trade" (overclaim; must change).**
`apps/api/app/modules/trading/live_router.py:52-61` evaluates the live gate and then raises
`PermissionDeniedError` unconditionally — there is no reachable execution path at any configuration.
To the project's credit this is disclosed in the UI: `apps/web/src/components/app-nav.tsx:38` labels
Live Trading **"Gated"**, not "Coming soon". But "algorithmic trading platform" in the README and
package metadata implies autonomous execution that does not exist.

**Direction 3 — "evidence-driven" is *under*-claimed (must be amplified).**
This is the finding that matters most for v2. The product's genuine differentiator is buried beneath
the marketing layer:

- A structurally look-ahead-free engine with a *perturbation canary test* that mutates future bars and asserts prior equity is unchanged (`apps/api/tests/test_backtest.py:73-85`, `test_lookahead_canary`).
- Costs users **cannot** turn off — `CreateBacktestRequest` exposes no friction fields (`apps/api/app/modules/backtesting/schemas.py:12-15`), so the disclosed "2 bps + 1 bps" footnote cannot drift from the actual run.
- Annualized metrics stripped **server-side** before they can reach a crawlable page (`market_data/public_router.py:46-51`) *and* independently omitted client-side (`track-record.tsx:20-29`) — belt and braces.
- A `HypotheticalBanner` on all four result surfaces (`track-record.tsx:74`, `market-view.tsx:164`, `backtest-results.tsx:184`, `paper-view.tsx:35`).
- A "What we deliberately don't claim" section (`methodology/page.tsx:92-98`) that is accurate against the code line by line.
- Reproducibility triples (`spec_hash`, `engine_version`, `data_fingerprint` — `backtesting/types.py:59-61`) surfaced in the UI rather than kept internal.

**Assessment.** The interior of the product already behaves like an evidence-driven research
platform; the exterior sells a signal product. The correction is therefore *not* a rewrite — it is
deleting four or five specific strings and promoting what is already true to the hero. The strongest
available positioning line is already in the repository, as a code comment (`page.tsx:120-122`):
*"the only performance figure on this page is the real, caveated reference backtest — never a
fabricated marketing stat."* That is the pitch.

**On "agentic."** The v2 target says *agentic*. The current AI is a one-shot form field: two
endpoints (`/ai/strategy`, `/ai/explain`), no chat UI, no tool use, no planning loop, no memory, no
per-run trace record. The dashboard already advertises an assistant that "summarize[s] a market"
(`dashboard-view.tsx:109`) — a capability that exists at no endpoint. **Do not deepen that claim
before the capability lands.** "Agentic" should be earned by shipping traces, evals and tool-use, not
asserted in copy. Today the honest word is "AI-assisted", which `page.tsx:54` already uses correctly.

---

## 3. Claims register

Grouped by surface. Locations are `file:line` at commit `8b82368`.

### 3.1 Landing page — `apps/web/src/app/page.tsx`

| Claim | Location | Verdict | Evidence | Required fix |
|---|---|---|---|---|
| "An event-driven engine that's structurally look-ahead-free" | `page.tsx:21` | **verified** | Decisions at bar *i*'s close (`engine.py:264-278`), fills at bar *i+1*'s open (`engine.py:196-231`); indicators causal (`compute.py`); canary test perturbs the future and asserts prior equity unchanged (`tests/test_backtest.py:73-85`) | None — lead with this |
| "…and models real commission, slippage, **and spread**" | `page.tsx:21` | **unsupported** | `ExecutionConfig` has exactly two friction fields, `commission_bps` and `slippage_bps` (`backtesting/types.py:14-15`); the engine applies only those (`engine.py:64-66,116`). A repo-wide case-insensitive search for `spread` outside `node_modules` returns **one** hit: this marketing string | Delete "and spread" |
| "Every result is reproducible." | `page.tsx:21` | **verified** | `spec_hash` / `engine_version` / `data_fingerprint` on every result (`types.py:59-61`), exposed publicly (`reference_backtest.py:214-218`), rendered (`market-view.tsx:184`, `track-record.tsx:96-101`) | None |
| "Describe a strategy in plain English and get a validated spec back — never auto-executed." | `page.tsx:26` | **verified** | `ai/service.py:42` returns a validated `StrategySpec` and never persists or runs it; `ai/router.py:22-28` returns it to the client; `strategies-view.tsx:51` only fills the textarea | None |
| "Grounded explanations of every result." | `page.tsx:26` | **unsupported** | The narrated payload is an unconstrained client dict — `ExplainRequest.context: dict[str, Any]` (`ai/schemas.py:21-23`) — forwarded verbatim to the prompt (`ai/service.py:61-70`). Nothing binds it to a stored backtest row | Take a `backtest_id`; rebuild context server-side under owner scoping |
| "TradingView-grade candles with **real-time data** over WebSockets" | `page.tsx:30-31` | **misleading without context** | The WebSocket transport is real (`market_data/router.py:229-252`, `use-market-socket.ts`), but it fans out bars produced by a 30-second REST poll (`streaming.py:63-81`). Real-time transport of delayed data is not real-time data | "Streaming bar updates over WebSockets (delayed, ~30s polled bars)" |
| "One canonical spec across AI, code, and **a visual builder**." | `page.tsx:36` | **unsupported** | The strategies screen is an AI prompt input plus a raw `<textarea rows={16}>` of spec JSON (`strategies-view.tsx:100-116`). No builder component exists under `apps/web/src/components`; a search for `drag` in `apps/web/src` returns nothing | "across AI and code" until a builder ships |
| "Mandatory exits, sizing, and enforced risk limits — by design." | `page.tsx:36` | **verified** | `StrategySpec` requires exit/sizing/risk (`strategies/spec.py`; ADR `docs/adr/0008:9`); the engine enforces the position clamp (`engine.py:208-213`), daily-loss halt (`:254-262`) and consecutive-loss halt (`:177-183`) | None |
| "Deploy a strategy and watch it trade **live** against a virtual ledger using the exact same engine" | `page.tsx:41` | **partially supported** | "Exact same engine" is true — `trading/service.py:80-85` calls the backtest `engine.run` with `close_at_end=False`. "Live" is not: it replays the same 30s-polled delayed bars (`service.py:76-78` → `md_repo.get_bars`) | "…against a virtual ledger **on delayed bars**, using the exact same engine" |
| "Position caps, daily-loss halts, and a kill-switch are enforced — not decorative." | `page.tsx:46` | **verified** | `engine.py:208-213` clamps to `max_position_pct` and records a `RiskEvent`; `:254-262` halts on `max_daily_loss_pct`; `:177-186` halts on `max_consecutive_losses`; risk events returned on the result (`types.py:54`) | None |
| "Real-money trading stays gated behind hard controls." | `page.tsx:46` | **verified** | `live_router.py:52-61` evaluates the gate then raises regardless; `live_trading_enabled` defaults `False` (`core/config.py:76`); the nav shows "Gated" (`app-nav.tsx:38`) | None |
| STATS tile: **"Sub-second" / "Live data"** | `page.tsx:53` | **contradictory** | `worker.py:112` `cron(poll_quotes, second={0, 30})`; `streaming.py:1-7` "MVP uses a periodic REST poll"; `live-price.tsx:19` `refetchInterval: 30_000` under a DELAYED badge (`:28-31`); the methodology page one click away says "~30-second cadence and can be delayed" (`methodology/page.tsx:69`) | Replace with "~30s polled / Delayed data", or a non-latency stat |
| "AI-assisted / Strategy authoring" | `page.tsx:54` | **verified** | Accurately describes `/ai/strategy` (`ai/router.py:22-28`) — assistive, not autonomous | None — this is the correct register for the whole page |
| "**Institutional-grade analytics**, an honest backtesting engine, and an AI copilot" | `page.tsx:102` | **unsupported** (first clause) / **verified** (second) | The metric set is total_return / CAGR / Sharpe / Sortino / max_dd / win_rate / profit_factor (`metrics.py:21-31`) with no benchmark, no factor attribution, no multiple-testing correction — the methodology page concedes the last two (`methodology/page.tsx:95-96`) | Delete "Institutional-grade"; keep the honest-engine clause. "Auditable, cost-aware analytics" is both true and more distinctive |
| "The terminal that respects your edge." | `page.tsx:103` | **misleading without context** | Presupposes the user has, and the product preserves, an alpha edge. The only strategy artifact shipped is one un-optimized SMA crossover (`reference_backtest.py:107-139`), and no attribution or benchmarking exists to establish any edge | Replace with a capability statement, e.g. "Your strategies, tested without hindsight" |
| "Start free" | `page.tsx:107` | **verified** | No billing, plan, price or payment code anywhere; `POST /auth/register` is open (`auth/router.py:49-57`) | None — but note the AI copilot needs an operator-supplied `GEMINI_API_KEY` (`ai/providers/gemini.py:19-21`) to function at all |
| "Not investment advice · For research & education" | `page.tsx:117`, `:204` | **verified** | Repeated in the footer (`:204`), methodology footer (`methodology/page.tsx:190`), public ticker footer (`market-view.tsx:237`), `LICENSE:31-33`, and the FAQ (`faq.ts:41`) | None |
| "No cherry-picked numbers here. The one performance figure below is our own reference strategy run in the open" | `page.tsx:124-128` | **partially supported** | True *within* the universe: `get_track_record` includes every covered instrument and never re-runs with different parameters (`reference_backtest.py:327-342`). Not true *of* the universe: five hand-picked 2026 survivors (`seed.py:21-61`), further filtered to symbols with enough manually backfilled history (`reference_backtest.py:196-201`; backfill is an operator command, `README.md:45`) | Add: "the universe is a fixed list of large caps and major crypto pairs chosen today — it is not survivorship-free" |
| "Trade with an edge you can actually trust." | `page.tsx:181` | **misleading without context** | The product cannot trade (`live_router.py:61`) and produces no edge estimate. The subhead three lines later — "Honest numbers, enforced risk" (`:184`) — *is* supported | "Test with numbers you can actually trust." |

### 3.2 Open Graph card — `apps/web/src/app/opengraph-image.tsx`

| Claim | Location | Verdict | Evidence | Required fix |
|---|---|---|---|---|
| "Honest, look-ahead-free backtesting." | `opengraph-image.tsx:100,116` | **verified** | `engine.py:264-278` plus the canary test (`tests/test_backtest.py:73-85`) | None |
| "Net of commission & slippage, **measured against buy & hold** — every result reproducible." | `opengraph-image.tsx:128-129` | **contradictory** | "Net of commission & slippage" and "reproducible" are verified (`types.py:14-15`, `:59-61`). "Measured against buy & hold" is listed by the product's own methodology page under **What we deliberately don't claim** (`methodology/page.tsx:97`), and no benchmark series is computed anywhere in `backtesting/metrics.py` | Delete the clause. Social platforms cache OG cards — fix before any further sharing |
| Footer: "AI-Powered Trading Intelligence · Not investment advice" | `opengraph-image.tsx:146-149` | **misleading without context** | The NFA half is fine; the tagline half puts signal-seller framing on the most-shared asset. Note the string is **hardcoded**, not read from `brand.ts` — so the working-tree tagline fix does **not** propagate here | Replace with the honest positioning **and** source it from `BRAND_TAGLINE` so it cannot drift again |

### 3.3 Methodology page — `apps/web/src/app/methodology/page.tsx`

This page is the product's strongest asset. Most rows are `verified`; the exceptions are precise.

| Claim | Location | Verdict | Evidence | Required fix |
|---|---|---|---|---|
| "Orders fill at the next bar's open, never the signal bar's close. No same-bar hindsight." | `:33` | **verified** | `engine.py:264-278` sets pending entry/exit at bar *i*'s close; `engine.py:196-231` fills at bar *i+1*'s open | None |
| "Commission of 2 bps per side and 1 bps of adverse slippage are applied to every fill… A zero-cost mode exists only for internal tests" | `:41-43` | **verified** | `types.py:14-17` defaults `commission_bps=2.0`, `slippage_bps=1.0`, `frictionless=False` ("TEST-ONLY"); applied at `engine.py:64-66,116`; `CreateBacktestRequest` exposes no friction fields (`backtesting/schemas.py:12-15`), so users cannot silently zero them | None — the non-overridability is a genuine strength |
| "Sharpe and Sortino are annualized with a risk-free rate of 0. That is stated wherever they appear so the numbers are auditable." | `:60` | **partially supported** | The rf=0 convention is real (`metrics.py:47-48`) and restated at `backtest-results.tsx:207-208`. But the periods-per-year constant assumed a 24/7 market for every asset class (`metrics.py:37`) — an undisclosed and incorrect convention | State the periods-per-year assumption alongside the risk-free rate. *(The constant itself is fixed in the working tree — §1.3.)* |
| "**The one performance figure** on our marketing pages…" | `:62` | **contradictory** | Every public ticker page also publishes five metrics of a per-symbol reference run (`market-view.tsx:23-29`), on pages explicitly crawl-allowed (`robots.ts:12-13`) and enumerated in the sitemap (`sitemap.ts:17-22`) | "The only performance figures we publish are reference-backtest runs of one fixed strategy — one aggregate on the landing page and one per public ticker page" |
| "Prices are polled on a ~30-second cadence and can be delayed — labeled DELAYED with a last-updated time, never presented as a live tick." | `:69` | **verified** | `worker.py:112`; `live-price.tsx:19,28-31`; `DataBadge`'s `LIVE` variant is never used anywhere in the app | None — but see the free-tier cadence conflict in §3.6 |
| "There is no claim of a real-time consolidated (SIP) feed." | `:70` (and `README.md:89`) | **verified** | No SIP claim exists anywhere; the chart badge tooltip says "not a live SIP feed" (`chart-workspace.tsx:246`); the FAQ answers "No" to the liveness question (`faq.ts:16-20`). The single counter-example is the landing stat tile (`page.tsx:53`) | Fix `page.tsx:53` so the claim stays true site-wide |
| "Paper sessions run the exact same engine as a backtest… no real-market liquidity, latency, or partial fills." | `:77-78` | **verified** | `trading/service.py:80-85` calls `engine.run(spec, bars, ExecutionConfig(...), close_at_end=False)`; disclosed via `HypotheticalBanner kind="paper"` (`paper-view.tsx:35`) and in alert emails (`trading/alerts.py:105,113`) | None |
| "Explanations are instructed to use only the numbers actually present in a result, and to refuse rather than invent." | `:86` | **partially supported** | The instruction exists (`ai/prompts.py:52-54`), and "instructed to" is honest phrasing. But "a result" is an arbitrary client-supplied dict (`ai/schemas.py:21-23`; the frontend sends its own copy at `backtest-results.tsx:172-178`), so the numbers are not server-verified, and no refusal mechanism exists | Take a `backtest_id` and rebuild the context from the owner-scoped stored result |
| "**Every** AI response ends with a not-investment-advice note." | `:87` | **unsupported** | The only mechanism is a sentence in a system prompt (`ai/prompts.py:54`). `explain_backtest` returns `resp.text.strip()` with no check or append (`ai/service.py:70`), and `/ai/strategy` returns a JSON spec containing no note at all (`ai/schemas.py:16-18`). Same overstatement at `README.md:91-92` and `ai/router.py:5` | Enforce server-side (append if the model omitted it), or reword all three to "the model is instructed to close with…" |
| "What we deliberately don't claim" list (no SIP feed, no survivorship-free fundamentals, no IS/OOS split, no Deflated Sharpe, no buy-and-hold overlay) | `:92-98` | **verified** | Each is accurate against the code: no SIP path (`streaming.py:1-7`), no fundamentals module, no train/test split in `backtesting/`, no deflated Sharpe in `metrics.py`, no benchmark series anywhere | None — but the OG card violates the last item (§3.2), and the survivorship item should be extended to cover the track-record universe |

### 3.4 Public per-ticker pages — `apps/web/src/app/markets/[ticker]/`

| Claim | Location | Verdict | Evidence | Required fix |
|---|---|---|---|---|
| Meta description: "Delayed {TICKER} … price with a **live** candlestick chart" | `page.tsx:54-57` | **contradictory** | "Delayed" and "live" in one sentence. The public chart explicitly has no live feed: `public-chart.tsx:35` — "has NO live WebSocket append — public data is delayed" | "an **interactive** candlestick chart" |
| `FinancialProduct` JSON-LD description (delayed price, real indicators, hypothetical reference backtest, not investment advice) | `page.tsx:87-98` | **verified** | Non-promissory and matches the visible page | None |
| Footer: "Delayed data. Hypothetical results. Not investment advice." | `market-view.tsx:237` | **verified** | Matches the DELAYED badges (`:106,115`), the `HypotheticalBanner` (`:164`) and the per-run caveat block (`:179-196`) | None |
| "Profit factor" metric tile on public pages | `market-view.tsx:27,35` | **contradictory** | `metrics.py:65` returned `gross_win` — a dollar sum (`:63`) — instead of a ratio whenever there were no losing trades, rendered as `value.toFixed(2)` under the label "Profit factor" on an indexed page. Short reference samples are exactly the regime these pages run in (`reference_backtest.py:196-201` admits runs at ≥35 bars) | *Fixed in working tree (§1.3).* Verify the client renders a `null` as "—" rather than `0.00` |
| Annualized metrics omitted from public surfaces because they mislead over short windows | `market_data/public_router.py:46-51`; `track-record.tsx:20-29`; `market-view.tsx:18-29` | **verified** | `_ANNUALIZED_METRICS` stripped server-side for both the track record (`:71,78`) and the per-ticker summary (`:173`); clients independently omit them | None — preserve |
| FAQ: "Is the {ticker} price on this page live? **No.** …delayed… does not present a real-time consolidated (SIP) feed." | `lib/markets/faq.ts:16-20` | **verified** | `public_router.py:154-161` serves the latest **closed** bar's close; rendered under a DELAYED badge with an "As of" timestamp (`market-view.tsx:106-110`). The same text is emitted as `FAQPage` JSON-LD (`faq-jsonld.tsx:11-27`) and shown on-page (`market-view.tsx:209-214`) | None — the single-source JSON-LD/on-page pattern is exemplary |
| FAQ: the reference backtest "is hypothetical, benefits from hindsight, and is not a trade recommendation or a prediction of future returns" | `faq.ts:23-28` | **verified** | `reference_backtest.py:107-139` is one fixed un-optimized SMA 10/30 spec run through `engine.run` with default frictions (`:210`); the server note says the same (`:223-226`); rendered under `HypotheticalBanner` (`market-view.tsx:164`) | None |
| FAQ: "SMA, EMA, and RSI series are computed causally with the exact same code the backtest engine uses… Warm-up periods are left blank rather than back-filled." | `faq.ts:31-35` | **verified** | `compute_public_indicators` calls the engine's `compute.build_arrays` / `compute_indicators` (`reference_backtest.py:94-96`) and maps NaN warm-up to `None` (`:102`); the page renders "—" for blanks (`market-view.tsx:147`) | None |
| FAQ: "TradePulse is a research and education tool… run them in paper (simulated) trading." | `faq.ts:38-41` | **verified** | No execution path exists (`live_router.py:52-61`); paper is simulated on stored bars (`trading/service.py:80-85`) | None |

### 3.5 Landing track record — `apps/web/src/components/track-record.tsx`

| Claim | Location | Verdict | Evidence | Required fix |
|---|---|---|---|---|
| "A real, reproducible illustration / The same engine, run in the open" | `:58-59` | **verified** | Numbers come from `engine.run` + `compute_metrics` (`reference_backtest.py:210`) with `spec_hash` and `engine_version` surfaced (`:96-101`); the section returns `null` rather than inventing a fallback when the API is down (`:50`) | None — this is the strongest honesty pattern in the codebase |
| Track record renders under a hypothetical notice | `:74` | **verified** | `HypotheticalBanner` sits directly above the metric tiles, plus a per-run / not-annualized / not-achievable note (`:93-96`) and the server's `data_note` (`:149`) | None |
| "Avg win rate" | `:28` | **misleading without context** | `reference_backtest.py:352-356` averaged `win_rate` across all covered symbols, and `metrics.py:21-31` returned `win_rate: 0.0` for a run with no trades (only filled `if trades:` at `:59-62`). A symbol whose SMA never crossed was counted as a 0% winner | *Fixed in working tree (§1.3).* Still show the component count contributing to each averaged metric |
| Universe framing (implicit in the aggregate) | `reference_backtest.py:316`; `seed.py:21-61` | **partially supported** | The module docstring asserts "no cherry-picking (ALL covered symbols count)" — true within the universe. The universe is AAPL, MSFT, SPY, BTC/USD, ETH/USD: five hand-picked 2026 survivors, further filtered to whatever an operator chose to backfill (`reference_backtest.py:196-201`, `README.md:45`). `methodology/page.tsx:94` discloses survivorship only for *fundamentals* | Add one sentence to the track-record caption and the methodology "don't claim" list disclosing hindsight-selected instrument coverage |
| "Not enough history" fallback instead of a zero-return number | `reference_backtest.py:196-201`; `market-view.tsx:198-201` | **verified** | `_unavailable()` returns `available=False` with an explanatory note rather than a misleading 0%; the landing `TrackRecord` returns `null` entirely (`track-record.tsx:50`) | None — exactly the right behaviour |

### 3.6 In-app surfaces

| Claim | Location | Verdict | Evidence | Required fix |
|---|---|---|---|---|
| Signal card: "Entry signal" with entry/stop/target/size | `components/signal-card.tsx:60-67` | **verified** (not public) | `SignalCard` is used **only** by `ChartWorkspace` (`chart-workspace.tsx:262`), which renders under the session-gated `(app)` route group (`(app)/layout.tsx:11-18`); the endpoint requires `CurrentUser` (`market_data/router.py:158-163`). Every price carries a DELAYED badge (`:113,151`) and an explicit "Not an executable order… Live trading is not enabled" note (`:121-129`) | None — but see §5.1: adding signal cards to public pages would change the regulatory posture materially |
| "Prices are DELAYED and modeled on the last closed bar; a real fill would occur at the next bar's open." | `signal-card.tsx:126-129` | **verified** | `market_data/signal.py:102-109` uses the last closed bar's close and nudges by the engine's own `slippage_fraction`/`entry_fill`; stop/target/size come from shared engine helpers (`:108-113`), so the client never does money math | None |
| Backtest footnote: "Returns are net of modeled costs — commission 2 bps/side + slippage 1 bps." | `components/backtest-results.tsx:206-208` | **verified** | Costs are not user-configurable (`backtesting/schemas.py:12-15`; orchestration defaults to `ExecutionConfig()` at `orchestration.py:61`), so the hard-coded footnote cannot drift from the actual run | None |
| Paper screen: "Deployed strategies running against **live data** on a virtual ledger." | `(app)/paper/paper-view.tsx:30,47` | **partially supported** | The virtual-ledger half is accurate (`trading/service.py:80-85`). "Live data" is the same 30s-polled delayed bar store (`service.py:76-78`) | "running against **delayed** market data on a virtual ledger" |
| Dashboard: "Portfolio Value" dollar figure | `(app)/dashboard/dashboard-view.tsx:54-58` | **misleading without context** | Computed from paper-session snapshots (`:36-42`) but labelled as a portfolio with no provenance chip, even though `DataBadge` defines `PAPER` and `SIMULATED` kinds (`data-badge.tsx:3`) and neither is used anywhere in the app | Rename "Paper portfolio value" and attach `<DataBadge kind="PAPER" />` |
| Dashboard: "AI Insights" / "Your market intelligence at a glance." | `dashboard-view.tsx:50,104` | **unsupported** | The card body is static prose and a link (`:107-115`). No AI call happens on this screen; the only AI calls are `strategies-view.tsx:50` and `backtest-results.tsx:172` | Rename the card "AI copilot"; drop "market intelligence" |
| Dashboard: "Ask the assistant to draft a strategy, explain a backtest, or **summarize a market** — grounded in your data" | `dashboard-view.tsx:109-110` | **contradictory** | Exactly two AI endpoints exist — `/ai/strategy` and `/ai/explain` (`ai/router.py:22,31`). There is no market-summary capability and no assistant/chat UI anywhere in `apps/web` | Remove the non-existent capability and the chat framing |
| Calculator: "TradePulse does not place live trades — real-money execution is intentionally gated behind hard risk controls." | `(app)/calculator/calculator-view.tsx:101-103` | **verified** | `live_router.py:52-61` refuses every order; sizing math is server-side (`trading/calc.py`) | None |
| Calculator: "**Portfolio risk**" result row | `calculator-view.tsx:217` | **contradictory** | The value is `pct_of_equity`, defined server-side as **notional / equity** (`trading/calc.py:56`; `trading/schemas.py:72` comments it "notional / equity"). With the screen's own defaults (equity 100000, entry 100, stop 95, risk 1%) it displays "20.00%" while capital at risk is 1% — and the adjacent "Risk amount" row shows the true figure, so the two tiles contradict each other on a tool whose entire purpose is risk communication | Rename to "Notional exposure" / "% of equity deployed" |
| Calculator: "All figures are computed server-side as exact decimals; nothing is calculated in your browser." | `calculator-view.tsx:227-228` | **misleading without context** | True for the displayed results (decimals arrive as strings). But `calculator-view.tsx:62-67` does `Number(riskPct)/100` in JS float before sending, and `dashboard-view.tsx:36-39` sums `Number(final_equity)` across sessions for the headline | Send the percentage as a string and let the server divide; fix or relabel the dashboard aggregate |
| `LivePrice` tooltip: "Polled every 30s and may be delayed." | `components/live-price.tsx:30` | **misleading without context** | True for the VM/worker deployment (`worker.py:112`) but contradicted for the documented no-card deployment, where `docs/DEPLOY_FREE_CLOUD.md:8` states "live data is **~5-min** cadence (not 30s)" via an external cron hitting `/internal/tick` (`ops_router.py:5-6`) | Drop the hard-coded interval, or serve the actual cadence from the API |
| MarketStatus pill: "Crypto 24/7 · Equities open/closed" | `components/market-status.tsx:41` | **partially supported** | The frontend computes the session correctly in `America/New_York` (`:11-24`) and honestly flags that holidays are unmodelled (`:8-9`). But the backend poller compares raw UTC minutes against a fixed 13:30–20:00 window (`streaming.py:27-37`) — EDT only — so under EST the UI says "open" for an hour while ingestion is idle | Convert to exchange time in `streaming.is_market_open`, matching the frontend |
| Nav: "Live Trading — Gated" | `components/app-nav.tsx:38,82-84` | **verified** | Matches `live_router.py:52-61`. Notably honest: "Gated" rather than "Coming soon" | None |

### 3.7 README, docs, metadata

| Claim | Location | Verdict | Evidence | Required fix |
|---|---|---|---|---|
| "AI-powered algorithmic trading intelligence — US equities + crypto." | `README.md:5` | **misleading without context** | The AI is an NL→spec translator plus a narration prompt (`ai/service.py:39-59`, `prompts.py:50-55`). No forecasting, ranking, or autonomous execution; live orders refused unconditionally (`live_router.py:52-61`) | Reposition as "a research workbench for building and honestly backtesting trading strategies" |
| "**Live market data**, interactive charts, a strategy builder…" | `README.md:7` | **contradictory** | Contradicted 82 lines later in the same file: `README.md:89` — "prices are polled (~30s) and labeled `DELAYED`; no real-time SIP claim." "Strategy builder" also overstates a JSON textarea (`strategies-view.tsx:110-116`) | "Delayed (~30s polled) market data… a canonical strategy spec (JSON + AI authoring)…" |
| "a **production-grade**, SaaS-ready platform" | `README.md:8`, `:29` | **partially supported** | SaaS-readiness is limited to `owner_id` row scoping, which ADR 0005 states outright — "no billing/org/RBAC yet" (`docs/adr/0005-owner-id-tenancy.md:6`). "Production-grade" has no objective backing; against it, the public endpoint runs N full backtests per uncached request (`public_router.py:61` → `reference_backtest.py:327-342`) | Drop "production-grade"; keep "SaaS-ready tenancy seam (no billing/orgs/RBAC yet)" |
| Live Demo badge → `https://tradepulse.vercel.app` | `README.md:11-13` | **blocked pending measurement** | No network access in this audit. The *inconsistency* is verifiable though: `brand.ts:11` defaulted `SITE_URL` to `https://tradepulse.app` and `NEXT_PUBLIC_SITE_URL` was set nowhere in the repo, so a deployed site emitted canonical/OG/sitemap URLs for a different domain than the badge | Verify the demo, then set `NEXT_PUBLIC_SITE_URL` to whichever origin is real |
| Screenshot alt text: "TradePulse — AI-powered trading intelligence" | `README.md:23` | **blocked pending measurement** | `docs/assets/screenshot.png` is a 1440×900 PNG that cannot be inspected here — whether it shows DELAYED badges, hypothetical banners, or fabricated P&L is unverified. `docs/assets/screenshot-light.png` is committed but referenced nowhere | Manually confirm the image shows honest provenance labels; reference or delete the unused light variant |
| "Frontend: … **shadcn/ui** (TanStack Query + **Zustand**)" | `README.md:36` | **unsupported** (shadcn) / **contradictory** (Zustand) | No `components.json` in `apps/web`, no `@radix-ui/*` dependency, no `data-slot` attributes — `components/ui/*` are 8 hand-written CVA components. `zustand` is absent from `apps/web/package.json`, and a search of `apps/web/src` returns zero imports. TanStack Query is the only true part (used in 12 files) | "Tailwind + hand-rolled CVA primitives (TanStack Query)" |
| "Market data (free): CCXT + yfinance out of the box" / "AI (free): Google Gemini (free tier) by default, or a local Ollama model — **both no-cost**" | `README.md:35,37` | **partially supported** | Market data really is keyless. AI is not usable out of the box: `GeminiProvider` raises "GEMINI_API_KEY is not configured" when the key is empty (`ai/providers/gemini.py:19-21`) and the default provider is `gemini` (`core/config.py:68`). Ollama needs a local install plus a model pull and is unreachable in every shipped deployment target (`Dockerfile:27`, `render.yaml:27-28`, `infra/.env.prod.example:33-36` all pin gemini; `infra/compose.prod.yaml` has no `ollama` service) | Say the AI copilot requires a free Gemini key (or a local Ollama), and mark the Ollama path dev-only until it is deployable |
| "Backtests are look-ahead-free… Every run is reproducible (spec hash + engine version + data fingerprint)." | `README.md:81-83` | **verified** | `engine.py:196-231,264-278`; `types.py:59-61`; `tests/test_backtest.py:73-85`; `repository.py:1-9` returns only `is_final` bars | None |
| "every backtest/paper result carries a hypothetical-performance notice" | `README.md:87-88` | **verified** | `HypotheticalBanner` on all four result surfaces: `backtest-results.tsx:184`, `paper-view.tsx:35`, `track-record.tsx:74`, `market-view.tsx:164` | None |
| "**Grounded** AI copilot — generates a validated spec, never auto-executes, instructed to use only the numbers present (refuses rather than invents), and **always** closes with a not-investment-advice note." | `README.md:90-92` | **partially supported** | "Validated spec, never auto-executes" is verified (`ai/service.py:42-59`, `ai/router.py:22-28`). "Refuses rather than invents" and "always closes" are prompt-only with no enforcement (`prompts.py:50-55`, `service.py:70`), and the explain context is client-supplied (`ai/schemas.py:21-23`) | Downgrade to "instructed to"; ground the explain context server-side |
| "CI adds informational pip-audit / npm audit + a coverage report alongside the existing mypy / import-linter / migration / OpenAPI-drift gates." | `README.md:100-102` | **verified** | `.github/workflows/ci.yml`: ruff `:42`, mypy `:46`, import-linter `:48`, migrations `:50`, OpenAPI drift guard `:54`, pytest+coverage `:58`, pip-audit `:60`, npm audit `:77`, TS types drift `:80`, gitleaks `:100` | None — whether these gates currently **pass** is a separate question; see `BASELINE_VERIFICATION.md` |
| "Real-money live trading is disabled by default and structurally gated (feature flag + opt-in + **2FA** + **step-up** + kill-switch + enforced risk + **per-order confirmation**). No AI/agent path can mint a live order." | `SECURITY.md:24-26` | **misleading without context** | The final sentence is **verified** — no AI endpoint touches trading; `ai/router.py` has no order path. The control list is not: `live_gate.py:41-61` is a dataclass whose `evaluate()` defaults every control to a constant, and its own docstring (`:1-4`) says 2FA/opt-in/step-up/confirmation are "deferred"; ADR 0004 (`docs/adr/0004-sessions-not-jwt.md:9`) defers TOTP MFA. The *behaviour* is fail-closed and safe; the *claim* describes controls that do not exist | "The gate enumerates the controls required before live trading can be enabled (2FA, opt-in, step-up, kill-switch, confirmation); none are implemented, so live trading is refused unconditionally" |
| PR checklist: "Did not enable real-money live trading or weaken a safety gate" | `.github/pull_request_template.md:12` | **verified** | Matches the code posture (`core/config.py:76`, `live_router.py:61`) | None |
| "AI-powered algorithmic trading platform (US equities + crypto): backtesting, paper trading, AI copilot." | `pyproject.toml:4` | **misleading without context** | The listed capabilities are all real; "algorithmic trading platform" implies execution that `live_router.py:52-61` refuses | "Backtesting and paper-trading research platform (US equities + crypto) with an AI strategy copilot." |
| FastAPI title "Trading Platform API" | `apps/api/app/main.py:62` | **partially supported** | Accurate but brandless and inconsistent with `BRAND_NAME` "TradePulse" (`brand.ts:2`); it is the public `/docs` heading and the OpenAPI `info.title` in `packages/contracts/openapi.json` | Rename to "TradePulse API" and regenerate the contract (the CI drift guard at `ci.yml:54` keeps it in sync) |
| `ai/router.py` module docstring: "Every response carries the non-advice framing in its text." | `apps/api/app/modules/ai/router.py:5` | **unsupported** | Same mechanism gap as `methodology/page.tsx:87`. `/ai/strategy` returns a JSON spec with no note at all (`ai/schemas.py:16-18`) | Enforce server-side, or reword |
| AI DSL guide offers `entry_short` to users generating strategies | `apps/api/app/modules/ai/prompts.py:29` | **unsupported** | `StrategySpec` accepted and validated `entry_short` (`spec.py:167,202-203`) but the engine is long-only (`engine.py:1`) and never read it — a generated long/short strategy backtested as if the short leg did not exist | *Spec side fixed in working tree (§1.3): `entry_short` is now rejected. The prompt at `prompts.py:29` still advertises it, so the copilot now reliably generates specs the validator refuses.* **Remove it from `DSL_GUIDE`.** |
| AI DSL guide offers `time_of_day.timezone: exchange\|utc` | `apps/api/app/modules/ai/prompts.py:35` | **unsupported** (at baseline) | `spec.py:155` declared the field; `engine.py:269` computed `minute = bar.ts.hour * 60 + bar.ts.minute` on a UTC timestamp and never read `timezone`, so an "exchange" window was silently evaluated in UTC | *Fixed in working tree (§1.3).* No copy change needed once verified |
| Free-tier deploy guide instructs publishing the source to a **public** Hugging Face Space | `docs/DEPLOY_FREE_CLOUD.md:9-10,36` | **misleading without context** | The doc states plainly "A public HF Space means its copy of the **code is public**", while `LICENSE:16-20` forbids any third party to "use, copy, reproduce, modify … publish, distribute" the Software and `LICENSE:5-6` calls it "proprietary and confidential". The doc is honest about the consequence; it just never connects it to the license | Note that the public-Space route publishes proprietary source and is owner-only, or recommend a private Space / the VM walkthrough |
| LICENSE is proprietary; is there any "open source" claim? | `LICENSE:1-33` | **verified** (no conflicting claim) | A case-insensitive repo-wide search for `open source` / `open-source` returns **zero** hits. The only tension is the deploy-doc row above | None |
| ADR-0002: "async background work (backtests, ingestion, alert evaluation, **AI calls**) without blocking the request path" | `docs/adr/0002-async-task-queue-arq.md:6` | **unsupported** | AI calls run inline in the request handler (`ai/router.py:26-27`) with per-attempt timeouts of 60s (Gemini) / 120s (Ollama) and up to three attempts. `apps/api/app/worker.py` defines no AI job | Move AI calls to ARQ with a poll endpoint, or amend the ADR and cap total wall-clock well under the proxy timeout |
| ADR-0008: "the AI tool-use target … consume[s] the generated artifact" (JSON Schema from `StrategySpec`) | `docs/adr/0008-one-canonical-strategyspec.md:9` | **unsupported** | The prompt uses a hand-written prose guide (`prompts.py:20-48`) plus a serialized example (`:61`), not the generated JSON Schema, and no provider uses tool-use/function-calling. No CI check guards the guide against `spec.py` drift | Generate the catalog/constraints section of the prompt from `spec.py` with a CI drift test, or amend the ADR |
| `apps/web/README.md` | whole file | **unsupported** (as documentation) | 36 lines of unmodified `create-next-app` boilerplate — "bootstrapped with create-next-app", "Learn More", "Deploy on Vercel". Nothing describes the proxy model, the generated API client, or the env contract | Replace with the real frontend contract, or delete in favour of `apps/web/AGENTS.md` |

---

## 4. Phrase-family analysis

### 4.1 "real time" / "live"

The most systematically overused word in the product. Ingestion is a 30-second REST poll
(`worker.py:112`, `streaming.py:1-7`), every stored bar is closed (`repository.py:1-9`), and the UI
correctly stamps `DELAYED` on every price it renders.

| Where "live" appears | Status |
|---|---|
| `page.tsx:31` "real-time data over WebSockets" | Misleading — real transport, delayed payload |
| `page.tsx:41` "watch it trade live" | Partially supported — delayed bars |
| `page.tsx:53` "Live data" | Contradictory (see §4.2) |
| `README.md:7` "Live market data" | Contradictory with `README.md:89` |
| `markets/[ticker]/page.tsx:55` "a live candlestick chart" | Contradictory with `public-chart.tsx:35` |
| `paper-view.tsx:30,47` "running against live data" | Partially supported |
| `app-nav.tsx:38` "Live Trading — Gated" | Verified — the one correct use |
| `data-badge.tsx:3` `LIVE` provenance kind | Defined and **never used anywhere** in the app. Deliberately so — that is the honest choice, and the comment at `:14-15` should say so explicitly |

**Assessment.** The infrastructure for honesty is already built and consistently applied at the point
of data *display*. Every failure is in prose written *about* the data, never in the data components
themselves. That makes this cheap to fix: six strings, no code.

### 4.2 "sub-second"

One occurrence, and it is the single most quantitatively false claim on the site.

`apps/web/src/app/page.tsx:53` renders the stat tile `["Sub-second", "Live data"]`. The measured
ingestion cadence is 30 seconds on the worker deployment (`worker.py:112`, `cron(poll_quotes,
second={0, 30})`) and ~5 minutes on the documented no-card deployment
(`docs/DEPLOY_FREE_CLOUD.md:8`). The client refetches every 30s (`live-price.tsx:19`). The
methodology page one click away states "~30-second cadence and can be delayed"
(`methodology/page.tsx:69`).

This is not puffery — it is a latency figure off by at least 30×, on a page whose copy 70 lines below
promises "No cherry-picked numbers here" (`page.tsx:125`). **Never publish a latency claim the
ingestion path cannot meet.** Replace with `["~30s polled", "Delayed data"]` or, better, a
non-latency stat that reflects the actual differentiator, e.g. `["Closed-bar", "Decision discipline"]`.

### 4.3 "production grade" / "institutional grade"

| Claim | Location | Verdict |
|---|---|---|
| "a production-grade, SaaS-ready platform" | `README.md:8`, `:29` | partially supported |
| "Institutional-grade analytics" | `page.tsx:102` | unsupported |

Neither phrase carries a testable definition, which is precisely why they read as filler on a product
whose whole thesis is testability. Against "institutional-grade" specifically: no benchmark series,
no factor attribution, no multiple-testing correction (conceded at `methodology/page.tsx:95-96`), and
— at baseline — a wrong annualization constant. Against "production-grade": the public endpoint runs
N full backtests per uncached request (`public_router.py:61` → `reference_backtest.py:327-342`).

**Both should be deleted rather than qualified.** They cost credibility and buy nothing.
"Auditable, cost-aware analytics" is defensible, differentiated, and describes what actually ships.

### 4.4 "look-ahead free"

**The strongest claim in the product, and it holds.** Verified at `page.tsx:21`,
`methodology/page.tsx:32-33`, `opengraph-image.tsx:100`, `README.md:81`, `faq.ts:31-35`.

Mechanism: decisions are taken at bar *i*'s close (`engine.py:264-278`), orders fill at bar *i+1*'s
open (`engine.py:196-231`), indicators are causal (`compute.py`), reads return only `is_final` bars
(`repository.py:1-9`), and NaN warm-up periods are left blank rather than back-filled
(`reference_backtest.py:100-103`). Most importantly it is **proven, not asserted**:
`apps/api/tests/test_backtest.py:73-85` (`test_lookahead_canary`) perturbs future bars and asserts
prior equity is unchanged.

One adjacent honesty gap sat in a different dimension at baseline, and is being closed: fields the
spec accepted and the engine silently ignored (`entry_short`, `universe[1:]`,
`time_of_day.timezone`). Silently dropping half a strategy while still returning a confident equity
curve is a look-ahead-grade failure of a different kind. The working-tree fix — refusing at
validation with an explicit engine-capability message — is the right shape. **Finish it by removing
`entry_short` from the AI DSL guide (`prompts.py:29`)**, which otherwise instructs the copilot to
generate specs the validator now rejects.

**Recommendation: make this the headline.** It is the one claim that is both true and rare.

### 4.5 "AI validated" / "grounded"

Two claims, opposite verdicts.

**Verified — the AI cannot execute anything.** `apps/api/app/modules/ai/__init__.py:6` states "No AI
code path can place an order," and it is structurally true: `ai/service.py` imports only `budget`,
`prompts`, `providers.base`, `strategies.spec` and kernel modules — no trading/backtesting imports,
no `eval`/`exec`/`subprocess`, no persistence. The only external importer of `app.modules.ai` is the
router mount in `main.py:30`, the ARQ worker has no AI job, and the import-linter contract
(`pyproject.toml:112-123`) keeps AI at the top layer. Generated specs are re-validated by Pydantic on
`POST /strategies` (`strategies/router.py:25-30`). **Preserve this design exactly.**

**Verified — the spec really is validated.** `ai/service.py:53-54` parses and validates against
`StrategySpec`, with a bounded validate-and-repair loop (`:46-59`) that re-prompts with the concrete
Pydantic error and fails closed with a 400 rather than returning a half-valid object.

**Unsupported — "grounded."** `/ai/explain` narrates an unconstrained client dict:
`ExplainRequest.context: dict[str, Any]` (`ai/schemas.py:21-23`), forwarded verbatim into the prompt
(`ai/service.py:61-70`, `prompts.py:71-72`), never correlated with a stored backtest row. Any
authenticated user can post fabricated metrics and receive a confident, branded analysis of them.
`dashboard-view.tsx:110` says "grounded in your data" unconditionally, and `page.tsx:26` says
"Grounded explanations of every result". `methodology/page.tsx:86` is the one correctly-hedged
instance ("are instructed to"). Note the blast radius is bounded — the output is ephemeral client
state, never persisted and never shown to another user — so this is a truthfulness defect, not an
authorization vulnerability.

**Unsupported — the disclaimer guarantee.** "Every AI response ends with a not-investment-advice
note" (`methodology/page.tsx:87`, `README.md:91`, `ai/router.py:5`) rests entirely on one sentence in
a system prompt (`prompts.py:54`). `explain_backtest` returns `resp.text.strip()` unmodified
(`service.py:70`), and `/ai/strategy` returns a JSON spec containing no note at all. An LLM that
drops the closer produces a response the product has promised cannot exist. The frontend compounds it
by rendering AI text in a plain box with no AI-generated label (`backtest-results.tsx:236-240`).

**Also unstated — data egress.** The default provider is remote (`core/config.py:68`, pinned in
`Dockerfile:27` and `render.yaml:27-28`), so strategy ideas and backtest metrics are sent to Google.
The methodology page's explicit "Deliberately not claimed" list covers SIP feeds and survivorship
bias but never third-party AI processing. `README.md:37` does name Gemini, so this is not undisclosed
outright — but no *in-product* surface tells a user, at the point of submission, where their input
goes. For a product positioned on transparency, that is the largest remaining credibility gap in this
family.

### 4.6 "guaranteed" / "profitable" / "risk free"

**Clean. Nothing to fix.** This is the family where the product most clearly outperforms its
category, and it deserves to be stated plainly.

A repo-wide case-insensitive search at commit `8b82368` finds **zero** return-promissory claims: no
"guaranteed returns", no "profitable", no "risk free", no "no risk", no "beat the market", no
"outperform", no "proven strategy", no win-rate boast. Every apparent match is engineering-internal:

| Match | Location | Actual meaning |
|---|---|---|
| "Honesty guarantees:" | `market_data/reference_backtest.py:15` | A docstring heading listing methodological constraints |
| "parity … guaranteed by" | `trading/__init__.py:5` | Backtest/paper engine parity — an engineering invariant |
| "hard guarantee against double-firing" | `trading/models.py:44` | A DB uniqueness constraint on alert dispatch |
| "risk-free rate of 0" | `README.md:87`, `methodology/page.tsx:60`, `backtest-results.tsx:208` | The standard Sharpe convention, correctly disclosed |
| "alpha=" | `backtesting/compute.py:42,43,58` | The EWM smoothing parameter |
| "proven" (12 hits) | various | All substring matches inside "provenance" |

The one adjacent risk is **implied**, not stated: "The terminal that respects your edge"
(`page.tsx:103`) and "Trade with an edge you can actually trust" (`page.tsx:181`) presuppose an edge
the product neither measures nor claims to produce. Fix those two strings and this family is entirely
clean.

Separately, one **label** in this family is genuinely dangerous and is tracked in §3.6: the calculator
renders notional exposure under the label "Portfolio risk" (`calculator-view.tsx:217` vs
`trading/calc.py:56`), showing 20.00% where actual risk is 1%. On a position-sizing tool, that is the
highest-consequence single word in the codebase.

### 4.7 "open source" / "free"

**"Open source": zero hits.** No copy anywhere contradicts the proprietary `LICENSE`. Verified clean.

**"Free": mostly accurate, with two qualifications.**

- "Start free" (`page.tsx:107`) — **verified**. No billing, plan, price or payment code exists anywhere; registration is open (`auth/router.py:49-57`).
- "Market data (free): CCXT + yfinance out of the box" (`README.md:35`) — **verified**. Genuinely keyless.
- "AI (free): … both no-cost" (`README.md:37`) — **partially supported**. Gemini requires a Google account and an API key, without which the API returns a 500 naming the missing env var (`ai/providers/gemini.py:19-21`); on the free tier, submitted content may be used by the provider to improve its products — a cost stated nowhere. Ollama requires a local install plus a model pull and is unreachable in every shipped deployment target.

**The real conflict in this family is the deploy guide vs. the LICENSE.**
`docs/DEPLOY_FREE_CLOUD.md:9-10,36` instructs the operator to create a **public** Hugging Face Space
and states outright that its "copy of the **code is public**", while `LICENSE:16-20` forbids any
third party to publish or distribute the Software and `LICENSE:5-6` calls it proprietary and
confidential. The doc is honest about the consequence; it simply never connects it to the license.
Add the note, or switch the recommended path to a private Space.

### 4.8 "autonomous"

**Zero hits for "autonomous", "auto-trade", "hands-free", "set and forget".** The product does not
claim autonomy anywhere, and it actively disclaims it: "never auto-executed" (`page.tsx:26`),
"generates a validated spec, never auto-executes" (`README.md:90`), "It generates a validated
strategy spec from plain English — and never auto-executes it" (`methodology/page.tsx:85`). All three
are **verified** against `ai/service.py:42-59` and `ai/router.py:22-28`.

The residual issue is **implied** autonomy in two places:

1. "AI-powered **algorithmic trading** intelligence" (`README.md:5`, `pyproject.toml:4`) — "algorithmic trading" conventionally means automated execution, which `live_router.py:52-61` refuses unconditionally.
2. The landing headline "Build, analyze & **automate** trading strategies" (`page.tsx:97`) — nothing in the product automates a trade. The closest capability is a paper session re-run by a 30s cron against a virtual ledger.

Both should be reworded. This family is otherwise a credit to the project: implying autonomy is
exactly what this category does, and the interior copy consistently refuses to.

### 4.9 Paper vs. live trading

**The distinction is honestly and consistently maintained — this is a strength.**

| Control | Location | Status |
|---|---|---|
| Live orders refused unconditionally | `trading/live_router.py:52-61` | verified |
| Feature flag defaults off | `core/config.py:76` | verified |
| Nav labels the item "Gated", not "Coming soon" | `app-nav.tsx:38,82-84` | verified |
| No AI path can reach an order | `ai/__init__.py:6`; import-linter `pyproject.toml:112-123` | verified |
| Paper runs the identical engine | `trading/service.py:80-85` (`close_at_end=False`) | verified |
| Paper screen carries `HypotheticalBanner kind="paper"` | `paper-view.tsx:35` | verified |
| Paper alert emails carry the simulation caveat | `trading/alerts.py:105,113` | verified |
| Calculator states the product places no live trades | `calculator-view.tsx:101-103` | verified |
| PR template forbids weakening the gate | `.github/pull_request_template.md:12` | verified |

Two defects remain, and neither is about the gate itself:

1. **`SECURITY.md:24-26` describes controls that do not exist** (2FA, opt-in, step-up, per-order confirmation). `live_gate.py:41-61` is a dataclass with constant defaults whose own docstring calls these "deferred", and ADR 0004 (`:9`) defers TOTP MFA. The effect is fail-closed and safe; the *claim* is not accurate. This is the one place where the product describes a security posture it does not have — a category of error worth correcting on its own terms.
2. **Paper equity is displayed as dollars without a `PAPER` badge.** `dashboard-view.tsx:54-58` labels a paper-derived sum "Portfolio Value", and `paper-view.tsx:30,47` describes the ledger as running "against live data". `DataBadge` already defines `PAPER` and `SIMULATED` provenance kinds (`data-badge.tsx:3`) and **neither is used anywhere in the app** — the components exist, they are simply not wired to the surfaces that show simulated money.

### 4.10 "track record" / "signals"

**Track record.** Mechanically well built and, unusually for the category, real. `GET
/public/track-record` (`public_router.py:54-86`) serves an equal-weight, per-run average of one fixed
SMA(10)/SMA(30) spec (`reference_backtest.py:107-139`) run through the same engine as user backtests
(`:210`), with default frictions, and includes **all** covered symbols with no per-symbol
cherry-picking (`:327-342`). Annualized metrics are stripped server-side (`public_router.py:46-51`)
*and* omitted client-side (`track-record.tsx:25-29`). The block renders under a `HypotheticalBanner`
(`:74`) with an explicit "per-run … NOT annualized … not an achievable return" note (`:93-96`), and
returns `null` rather than inventing a fallback when the API is down (`:50`).

Two qualifications survive:

- **Universe selection is undisclosed.** "No cherry-picking" is true within the universe; the universe is five hand-picked 2026 survivors (`seed.py:21-61`), further filtered to whatever an operator chose to backfill (`reference_backtest.py:196-201`, `README.md:45`). `methodology/page.tsx:94` discloses survivorship only for *fundamentals*. The landing line "No cherry-picked numbers here" (`page.tsx:124-125`) is therefore stronger than the code supports.
- **"The one performance figure on our marketing pages"** (`methodology/page.tsx:62`) is inaccurate: every public ticker page publishes five more (`market-view.tsx:23-29`), and those are the SEO surface.

**Signals.** `SignalCard` (`components/signal-card.tsx:60-67`) renders an "Entry signal" badge with
entry, stop, target and size — the highest-regulatory-risk artifact in the product. It is **correctly
gated**: used only by `ChartWorkspace` (`chart-workspace.tsx:262`), which renders under the
session-gated `(app)` group (`(app)/layout.tsx:11-18`), served by an endpoint requiring `CurrentUser`
(`market_data/router.py:158-163`). Every price carries a DELAYED badge (`:113,151`), the card states
"Not an executable order… Live trading is not enabled" (`:121-129`), and the money math is done
server-side by the engine's own helpers (`signal.py:102-113`) rather than in the browser.

No claim in this family is unsupported. The action item is **preservation**, not correction — §5.1.

---

## 5. Public surfaces

The unauthenticated surface is what a regulator, a journalist or a crawler sees first. It is
enumerated here in full.

| Route | Auth | Publishes | Crawl status |
|---|---|---|---|
| `/` | none | Landing copy + `TrackRecord` aggregate (3 metric tiles + per-symbol component table) | allowed (`robots.ts:18`) |
| `/methodology` | none | Method description + "don't claim" list | allowed |
| `/markets/[ticker]` | none | Delayed price, OHLCV chart, latest SMA/EMA/RSI, **5 reference-backtest metrics**, FAQ, `FinancialProduct` + `FAQPage` JSON-LD | explicitly allowed (`robots.ts:12-13`), sitemapped (`sitemap.ts:17-22`), pre-rendered (`page.tsx:19-27`) |
| `GET /public/markets/{ticker}` | none | Latest closed-bar price, indicator series, reference summary | — |
| `GET /public/markets/{ticker}/bars` | none | OHLCV rows, capped at 1500 | — |
| `GET /public/track-record` | none | Universe-wide aggregate | — |
| `/login`, `/forgot-password`, `/reset-password` | none | No product claims | allowed |

### 5.1 Per-ticker signal cards — not public, and that must stay true

The single most important finding in this section is a negative one, and it is easy to lose:
**TradePulse does not publish per-ticker trading signals.**

`SignalCard` has exactly one call site — `chart-workspace.tsx:262` — inside a component rendered only
within the `(app)` route group, which redirects any request without a session cookie
(`(app)/layout.tsx:11-18`) and is additionally gated in the proxy. The API endpoint it consumes
requires `CurrentUser` (`market_data/router.py:158-163`). Nothing under `apps/web/src/app/markets/`
imports it.

This matters because the card is the one artifact in the product that looks like a recommendation: a
directional "Entry signal" badge with a concrete entry price, stop, target and position size for a
named ticker. Publishing that on a crawlable page — with `FinancialProduct` JSON-LD already attached
to the same route — would change the product's posture materially, from "research tool" to something
a reasonable reader could treat as personalised investment advice.

**Required guardrails (none exist today):**

1. Add a test asserting `GET /market/instruments/{id}/signal` returns 401 unauthenticated. There is currently **no** test covering this boundary.
2. Add a lint or CI grep asserting `SignalCard` is imported only from within `apps/web/src/app/(app)/**` and its components.
3. Record the constraint in `SECURITY.md` alongside the live-trading invariant, so it is a stated invariant rather than an accident of the current import graph.

### 5.2 Landing track record

Assessed in §4.10. Summary of the public-surface posture:

**Correct and worth preserving:** real engine output; no fabricated fallback; annualized metrics
stripped in two independent places; `HypotheticalBanner` above the tiles; per-run / not-annualized /
not-achievable caption; reproducibility triple surfaced; `available=False` handled by hiding the
section rather than showing 0%.

**Two disclosure gaps:** the hindsight-selected instrument universe (§4.10), and the inaccurate "the
one performance figure on our marketing pages" (`methodology/page.tsx:62`) given that the per-ticker
pages publish five metrics each.

**One load-bearing operational risk on the same surface:** `GET /public/track-record` runs a full
backtest per instrument per uncached request (`public_router.py:61` → `reference_backtest.py:327-342`),
and the rate limiter's tighter 30/min bucket applies only to paths *ending in* `/bars`
(`core/ratelimit.py:60-62`) — so both `/public/markets/{ticker}` and `/public/track-record` fall
through to the default 120/min (`:64-65`, `core/config.py:56`). The limiter also trusts the leftmost
`X-Forwarded-For` hop with no trusted-proxy allowlist (`core/ratelimit.py:42-47`), so the per-IP
budget is bypassable by header rotation. No `Cache-Control` header is set anywhere in the API. This
is not a claims defect, but it sits directly beneath the claims surface and is the reason the track
record can be made expensive by an anonymous caller.

### 5.3 Public metadata integrity

`FinancialProduct` and `FAQPage` JSON-LD are generated from the **same** `tickerFaq()` source the
visible page renders (`lib/markets/faq.ts` → `faq-jsonld.tsx` → `market-view.tsx:209-214`), with an
explicitly stated rule that structured data must not drift from visible copy (`faq-jsonld.tsx:6-7`).
This is the correct pattern and should be the template for any future structured-data surface.

At baseline, every canonical, `og:url`, JSON-LD `url`, `robots.host` and sitemap entry resolved
against the placeholder `https://tradepulse.app` (`brand.ts:11`) — a domain the README's own demo
badge (`README.md:11`) contradicts. *(Addressed in the working tree — §1.3. Confirm the deployed
build sets `NEXT_PUBLIC_SITE_URL` as a Docker **build** arg, since `NEXT_PUBLIC_*` is inlined at
build time and runtime container env has no effect.)*

---

## 6. Prioritized correction list

Ordered by consequence, not effort. **P0** items are factually false statements on crawlable or
shareable surfaces; **P1** items are misleading positioning; **P2** items are accuracy and hygiene.

### P0 — false on a public or cached surface

| # | Action | Location | Why first |
|---|---|---|---|
| 1 | Delete "measured against buy & hold" from the OG card | `opengraph-image.tsx:128-129` | Social platforms cache OG cards; the product's own methodology page lists this under "What we deliberately don't claim" (`methodology/page.tsx:97`). Fix before any further sharing |
| 2 | Replace the "Sub-second / Live data" stat tile | `page.tsx:53` | A latency claim off by ≥30×, sitting 70 lines above "No cherry-picked numbers here" |
| 3 | Rename the calculator's "Portfolio risk" row to "Notional exposure" | `calculator-view.tsx:217` | Displays 20.00% where capital at risk is 1%, on a risk tool, contradicting the adjacent "Risk amount" row |
| 4 | Delete "and spread" | `page.tsx:21` | Zero implementation; `ExecutionConfig` has two friction fields (`types.py:14-15`) |
| 5 | Delete "and a visual builder" | `page.tsx:36` | Zero implementation; the UI is a JSON textarea (`strategies-view.tsx:110-116`) |
| 6 | Change "a live candlestick chart" → "an interactive candlestick chart" | `markets/[ticker]/page.tsx:55` | Self-contradicting meta description on the primary SEO surface |
| 7 | Add a test + import guard asserting signal cards stay auth-only | `market_data/router.py:158-163`; `chart-workspace.tsx:262` | The one artifact whose accidental exposure changes the regulatory posture; today it is protected only by the import graph, with no test |

### P1 — positioning

| # | Action | Location | Why |
|---|---|---|---|
| 8 | Source the OG footer tagline from `BRAND_TAGLINE` instead of hardcoding it | `opengraph-image.tsx:146` | The working-tree tagline fix does **not** propagate here; the retired "AI-Powered Trading Intelligence" still ships on the most-shared asset |
| 9 | Reposition README + `pyproject` away from "algorithmic trading intelligence/platform" | `README.md:5`; `pyproject.toml:4` | Implies execution the product refuses unconditionally (`live_router.py:52-61`) |
| 10 | Delete "Institutional-grade" and "The terminal that respects your edge" | `page.tsx:102-103` | Unsupported, and edge-presupposing; replace with the honest-engine claim, which is verified |
| 11 | Change "Trade with an edge you can actually trust" → "Test with numbers you can actually trust" | `page.tsx:181` | The product cannot trade and estimates no edge; the adjacent subhead (`:184`) is already correct |
| 12 | Change "Live market data" → "Delayed (~30s polled) market data"; drop "production-grade" | `README.md:7-8`, `:29` | Contradicted by `README.md:89` in the same file |
| 13 | Reword the "Every AI response ends with…" guarantee in all three places, **or** enforce it server-side | `methodology/page.tsx:87`; `README.md:91-92`; `ai/router.py:5` | A guarantee backed only by a prompt sentence (`prompts.py:54`) with no check or append (`service.py:70`) |
| 14 | Ground `/ai/explain` on a `backtest_id` loaded under owner scoping | `ai/schemas.py:21-23`; `ai/service.py:61-70` | Makes "grounded in your data" (`dashboard-view.tsx:110`, `page.tsx:26`) true rather than aspirational |
| 15 | Reword the `SECURITY.md` live-trading control list | `SECURITY.md:24-26` | Describes 2FA/opt-in/step-up/confirmation that `live_gate.py:1-4` itself calls "deferred". Keep the verified sentence about AI paths |
| 16 | Reword "the one performance figure on our marketing pages" | `methodology/page.tsx:62` | Every public ticker page publishes five more (`market-view.tsx:23-29`) |
| 17 | Disclose the hindsight-selected track-record universe | `page.tsx:124-125`; `methodology/page.tsx:94`; `track-record.tsx` caption | "No cherry-picking" is true within the universe, not of it (`seed.py:21-61`) |
| 18 | Soften "real-time data over WebSockets" and the "live data" framing on paper surfaces | `page.tsx:31,41`; `paper-view.tsx:30,47` | Real transport, delayed payload; delayed bar store |

### P2 — accuracy, consistency, hygiene

| # | Action | Location |
|---|---|---|
| 19 | Remove `entry_short` from the AI DSL guide — the validator now rejects it, so the copilot reliably generates invalid specs | `ai/prompts.py:29` |
| 20 | Wire `<DataBadge kind="PAPER" />` into the dashboard and paper surfaces; rename "Portfolio Value" → "Paper portfolio value" | `dashboard-view.tsx:54-58`; `data-badge.tsx:3` |
| 21 | Rename the "AI Insights" card to "AI copilot"; drop "summarize a market" and "market intelligence" | `dashboard-view.tsx:50,104,109-110` |
| 22 | Fix the README frontend stack line (no Zustand, not shadcn/ui) | `README.md:36` |
| 23 | Qualify "AI (free) … both no-cost": a Gemini key is required; Ollama is dev-only until deployable | `README.md:37` |
| 24 | Note that the public HF Space route publishes proprietary source, or recommend a private Space | `docs/DEPLOY_FREE_CLOUD.md:9-10,36` |
| 25 | Rename the FastAPI title to "TradePulse API" and regenerate the contract | `apps/api/app/main.py:62` |
| 26 | Drop the hard-coded "Polled every 30s" from the `LivePrice` tooltip, or serve the real cadence | `live-price.tsx:30` |
| 27 | Convert `streaming.is_market_open` to exchange time (`market-status.tsx:11-24` already shows the correct approach) | `streaming.py:27-37` |
| 28 | Disclose third-party AI processing in-product at the point of submission, and add it to the methodology limits list | `methodology/page.tsx:81-98`; the AI affordances |
| 29 | Replace `apps/web/README.md` (create-next-app boilerplate) with the real frontend contract, or delete it | `apps/web/README.md` |
| 30 | Add a shared copy constant or CI grep so marketing copy cannot drift from methodology copy again | `page.tsx` / `methodology/page.tsx` |
| 31 | Resolve or record the two blocked items: demo liveness (`README.md:11`) and screenshot content (`README.md:23`) | — |

### 6.1 Do not regress

These are the product's actual differentiator and should survive every change above:

- The look-ahead-free engine and its canary test — `engine.py:196-231,264-278`; `tests/test_backtest.py:73-85`
- Non-overridable costs — `backtesting/schemas.py:12-15`; `orchestration.py:61`
- Server-side stripping of annualized metrics on public surfaces — `public_router.py:46-51`
- `HypotheticalBanner` on all four result surfaces — `track-record.tsx:74`, `market-view.tsx:164`, `backtest-results.tsx:184`, `paper-view.tsx:35`
- The single-source FAQ → JSON-LD → on-page pattern — `lib/markets/faq.ts`, `faq-jsonld.tsx:6-7`
- Signal cards remaining auth-only — `chart-workspace.tsx:262`, `(app)/layout.tsx:11-18`, `market_data/router.py:158-163`
- `track-record.tsx:50` returning `null` rather than inventing a number
- The "What we deliberately don't claim" section — `methodology/page.tsx:92-98`
- The nav labelling Live Trading "Gated" rather than "Coming soon" — `app-nav.tsx:38`
- The complete absence of promissory return language anywhere in the repository (§4.6)

---

## Baseline Verification (see BASELINE_VERIFICATION.md)

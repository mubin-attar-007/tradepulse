# TradePulse — Current-State Audit (pre-v2)

**Date:** 2026-08-21
**Baseline commit:** `8b82368` (`main`, clean tree) — the same commit measured in
[`BASELINE_VERIFICATION.md`](./BASELINE_VERIFICATION.md).
**Scope:** the whole repository — `apps/api`, `apps/web`, `packages/contracts`, `infra/`,
`.github/`, `docs/`, root tooling.

## How to read this document

- Every `path:line` reference is against **commit `8b82368`** unless explicitly marked
  otherwise. A working tree with uncommitted remediation exists; it is described in
  §2.12 and is never used as the baseline.
- Findings carry stable ids (`ARCH-01`, `MD-04`, `BT-02`, …). The complete register is
  §10; narrative sections cite ids rather than repeating evidence.
- Every finding below survived an independent verification pass. Claims that verification
  **refuted** have been removed entirely; claims that verification **corrected** appear
  here in their corrected form, with the correction noted where it is material.
- Severity is `critical` / `high` / `medium` / `low` / `info`, judged on blast radius at
  the point of deployment, not on how hard the code is to fix.
- Two deep dives live in separate documents and are summarised, not duplicated, here:
  [`QUANT_CORRECTNESS_AUDIT.md`](./QUANT_CORRECTNESS_AUDIT.md) (engine, indicators,
  metrics, reproducibility) and [`AI_SYSTEM_AUDIT.md`](./AI_SYSTEM_AUDIT.md) (providers,
  prompts, budget, evaluation).

---

## 1. Executive summary

### 1.1 What exists

TradePulse is a modular-monolith FastAPI backend (7,008 LOC across 101 modules at HEAD)
plus a Next.js 16 App Router frontend (92 files), sharing a generated OpenAPI contract.
Seven bounded modules (`auth`, `audit`, `market_data`, `strategies`, `backtesting`,
`trading`, `ai`) sit on a kernel (`app/core/`) with a composition root at `app/main.py`.
Nine tables across six linear Alembic revisions. An ARQ worker runs two crons. 45 HTTP
routes (43 from domain routers plus `/health` and `/ready`) and one WebSocket. Four deploy targets: Render, Hugging Face Spaces, Vercel (web),
and a self-hosted Docker Compose VPS.

Functionally: delayed market-data ingestion from three providers; a JSON strategy DSL
(`StrategySpec`); an event-driven backtest engine; paper trading that re-runs that same
engine on a schedule; an AI copilot that translates natural language into a spec and
narrates results; a position-size calculator; an email alert feed; a public crawlable
SEO surface; and a live-trading seam that refuses every order.

### 1.2 What is genuinely strong — preserve these

These are not faint praise. Several are better than what most projects of this size ship.

| Strength | Evidence |
|---|---|
| **Tenancy is enforced by construction, not convention** | `OwnedRepository.add()` stamps `owner_id` from the repository rather than trusting the caller (`apps/api/app/core/repository.py:38`); `_owned()` filters every read (`:27`); `apps/api/tests/test_tenancy.py:41-55` proves a spoofed `owner_id` is overridden. |
| **The engine's core timing discipline holds** | Decisions on closed bar `i`, fills at bar `i+1`'s open (`apps/api/app/modules/backtesting/engine.py:265-279`, `:196-231`); indicators are causal with `min_periods` warm-up masking, and NaN comparisons return `False` so no trade fires unwarmed (`compute.py:132-133`); a look-ahead canary exists (`apps/api/tests/test_backtest.py:73-85`). |
| **Costs are not user-tunable** | `CreateBacktestRequest` exposes no friction fields (`backtesting/schemas.py:12-15`); commission is charged on both legs and included in `entry_gross` (`engine.py:116`, `:218-226`, `:155-159`). A `frictionless` mode exists but no API path can reach it. |
| **Migration chain is linear and drift-free** | Six revisions, single head, verified column-by-column against every model with zero drift; portable `date_bin`/`array_agg` reads instead of Timescale-only `time_bucket`/`first`/`last` (`market_data/repository.py:176-190`); the hypertable conversion is guarded by a `pg_extension` probe so the same migration runs on plain Postgres. |
| **Contract drift guards actually work** | `packages/contracts/openapi.json` regenerates byte-identically; `.gitattributes` pins both generated artifacts to LF so the guard is deterministic on Windows; CI diffs both sides (`.github/workflows/ci.yml:54-57`, `:80-83`). |
| **Alert idempotency is correctly ordered** | Stable `dedup_key`, an in-batch `seen` guard, a DB unique constraint as the hard backstop, and a documented commit-before-email rationale (`trading/alerts.py:136-143`, `:156`; `trading/models.py:49`). Rare to see reasoned through this carefully. |
| **The live-trading gate is unreachable by construction** | `LiveTradingGate.evaluate` defaults every control to `False` (`trading/live_gate.py:42-52`); `/live/orders` raises an unconditional `PermissionDeniedError` even past the gate (`live_router.py:59-61`); `AlpacaBrokerAdapter.submit_order` has zero callers repo-wide. |
| **Public surfaces strip annualized metrics server-side** | `_ANNUALIZED_METRICS` is removed from every crawlable payload (`market_data/public_router.py:46-51`), with the frontend independently omitting them (`track-record.tsx:20-24`, `market-view.tsx:18-22`). Belt-and-braces, and the right call. |
| **The honesty layer is real** | `HypotheticalBanner` on all four result surfaces; `DataBadge` on every price; `/methodology`'s "what we deliberately don't claim" list is accurate against the code; `TrackRecord` returns `null` rather than inventing a number when the API is down (`track-record.tsx:50`); FAQ text is single-sourced between JSON-LD and visible copy (`apps/web/src/lib/markets/faq.ts`). |
| **Type and secret hygiene** | `mypy` clean across 101 files under a strict-ish config; `ruff check` clean; gitleaks in pre-commit *and* as a full-history CI scan; only `.env.example` files tracked. |

### 1.3 What is weak

Five structural themes account for most of the register.

1. **Safety controls are individually well-designed and collectively mis-wired.** CSRF
   exists and guards 3 of 21 unsafe endpoints. Rate limiting exists and is bypassable with
   one header. Logout exists and does not clear the production cookie. The recurring
   pattern is a correct mechanism attached to too few call sites.
2. **Two CI gates are red on `main`, and have been for five commits.** `lint-imports` and
   `ruff format --check` both fail at HEAD. Whatever branch protection exists is not
   enforcing them.
3. **The marketing layer contradicts the product's own methodology page.** Several
   landing/OG claims are refuted by code in this repository — three of them by a page one
   click away. For a product whose entire differentiator is provenance honesty, this is
   the most self-inflicted category of damage in the audit.
4. **Numeric defects reach rendered pages.** Calendar-blind annualization and a
   `profit_factor` that returns dollars instead of a ratio both surface in the UI, the
   latter on crawlable per-ticker pages.
5. **Declared-but-ignored surface area.** `entry_short`, `max_open_positions`,
   `time_of_day.timezone`, multi-symbol `universe`, `APP_SECRET_KEY`, `orjson`,
   `python-multipart`, `hypothesis`, `bars_as_of`, `AlpacaBrokerAdapter`. Each is
   accepted, advertised, or documented, and then does nothing.

### 1.4 Top 15 issues, ranked

Ranked by deployment blast radius. Ids resolve in §10.

| # | Id | Sev | Issue |
|---|---|---|---|
| 1 | `ARCH-01` | critical | Import-linter layered contract is **broken at HEAD**; the architecture CI gate fails. Six unsanctioned upward edges from `market_data` into `backtesting`/`strategies`. |
| 2 | `FE-01` | critical | `NEXT_PUBLIC_*` never reach the production web bundle — `infra/Dockerfile.web:12` builds with no build args — so every deployed browser attempts `ws://localhost:8080/market/ws`. The live chart cannot connect anywhere. |
| 3 | `FE-02` | critical | The position-size calculator labels **notional exposure** as "Portfolio risk" (`calculator-view.tsx:217`), reading 20.00% where capital at risk is 1%. A risk tool that misstates risk. |
| 4 | `SEC-01` | high | A **real 32-byte `BROKER_CRED_KEY`** is published in a committed deploy guide (`docs/DEPLOY_FREE_CLOUD.md:41`) and recommended for a *public* Space. Aggravated: `POST /brokers/connections` accepts `env="live"` with no gate. |
| 5 | `MD-05` / `TRD-002` | high | Rate limiting trusts the leftmost `X-Forwarded-For` hop unconditionally (`core/ratelimit.py:42-47`) with no trusted-proxy allowlist. Every middleware-enforced budget is bypassable per request. |
| 6 | `TRD-003` | high | Login (10/min) and password-reset (5/5min) limiters key on `request.client.host` (`auth/router.py:38-39`) while `forwarded_allow_ips` is unset — behind any proxy that is **one bucket for the whole platform**. One visitor can lock out every login. |
| 7 | `SEC-02` / `TRD-012` | high | `FRONTEND_URL` and SMTP are set in **no** deploy target, so password reset is 100% broken in production *and* the live 30-minute token is written to stdout in full (`core/email.py:23`), shipped to Loki. |
| 8 | `TRD-005` | high | Password change and password reset revoke **no** sessions; there is no per-user session index, so "revoke all sessions" is not expressible. A stolen cookie survives a reset for up to 14 days. |
| 9 | `BT-02` | high | ATR position sizing reads the **fill bar's own** high/low (`engine.py:206`) — intrabar look-ahead the existing canary structurally cannot detect. Perturbing only bar `i`'s H/L moved position size ~7x. |
| 10 | `BT-01` | high | Trailing-stop exits book the **bar's open** instead of the trail level (`engine.py:236-240`) because the gap-through test runs after the ratchet. Uniformly pessimistic; silently mis-ranks strategies. Zero test coverage for `trailing_stop_pct`. |
| 11 | `BT-04` + `BT-05` | high | Sharpe/Sortino/CAGR annualized at 365d / 8760h regardless of calendar (`metrics.py:37`), with no minimum-sample floor — a 6-bar run produced `sortino: -54045`. Both render in the authed UI. |
| 12 | `MD-06` + `MD-07` | high | Zero data-quality validation at any layer (no NaN / negative / `high<low` check, no CHECK constraint) and no corporate-action handling — combined with immutable final bars, corruption is **unrepairable by re-ingestion**. |
| 13 | `MD-01` | high | `get_bars` returns a still-forming trailing bucket at every timeframe above 1m (`repository.py:176-190`), so the signal card's "Latest closed bar" contract is false at 1h/1d and repaints minute-to-minute. |
| 14 | `CI-01` | high | `ruff format --check` fails at HEAD; **five** commits (from `55fe20d`) landed on `main` against a red required gate. The formatting is a symptom; the process gap is the finding. |
| 15 | `PC-01`–`PC-06`, `FE-03`, `FE-04` | high | Landing/OG copy claims "Sub-second live data", "measured against buy & hold", "models … spread", and "a visual builder" — all four contradicted by this repository, three of them by `/methodology` itself. |

Immediately behind: `TRD-001` (logout is a redirect trap in production), `TRD-004` (CSRF on
3 of 21 unsafe endpoints), `MD-04` (unauthenticated full-year engine runs per request),
`FE-05` (every API error renders as a benign "no data yet" empty state), `AI-12` (no LLM
evaluation harness of any kind).

---

## 2. Repository & architecture

### 2.1 Structure

208 tracked files: `apps/api` (128), `apps/web` (92), `docs` (14), `infra` (12),
`.github` (4), plus root tooling. The modular-monolith shape the ADRs describe is
genuinely present, not aspirational: a kernel at `app/core/`, seven bounded modules under
`app/modules/`, a composition root (`app/main.py`, `app/worker.py`, `app/ops_router.py`,
`app/models.py`), and a three-command CLI (`app/cli/`).

`app/core/` contains: `config`, `context`, `crypto`, `db`, `deps`, `email`, `errors`,
`logging`, `middleware`, `observability`, `ratelimit`, `redis`, `repository`, `security`,
`types`. There is **no `events` module**, contrary to `README.md:56` (`DOC-01`).

### 2.2 Modules and ownership

Ownership is clean and non-overlapping — no table is written by two modules.

| Module | Owns |
|---|---|
| `auth` | `users`, `user_credentials`, `broker_connections`; Redis sessions (`session:`) and reset tokens (`pwreset:`); `CurrentUser`, `csrf_protect`, `get_owned` |
| `audit` | `audit_log` — append-only, insert-only service (`audit/service.py:13`) |
| `market_data` | `instruments`, `instrument_sources`, `ohlcv`; ccxt/yfinance/alpaca adapters; ingestion, polling/publish, Redis pub-sub + WS tickets, public SEO surface |
| `strategies` | `strategies`, `strategy_versions`; the canonical `StrategySpec` DSL (`spec.py:24` onward) |
| `backtesting` | `backtests`; engine / compute / metrics / snapshot plus persistence orchestration |
| `trading` | `paper_sessions`, `alerts`; position sizing, alert dispatch, broker-connection service, `LiveTradingGate` |
| `ai` | Gemini/Ollama providers, prompts, per-user + global Redis token budget |

`backtesting/service.py` (pure compute over bars) versus `backtesting/orchestration.py`
(persist + failure capture) initially reads as duplication but is a legitimate split:
`service.py` is engine-facing, `orchestration.py` is request-facing. Worth keeping.

### 2.3 Routes

43 router-declared HTTP paths (22 `GET`, 21 `POST` — no `PUT`/`PATCH`/`DELETE` exists
anywhere in the API) plus 1 WebSocket, every router mounted at `app/main.py:117-129`.
`/health` and `/ready` are declared directly on the app (`main.py:90`, `:94`), and `/metrics`
is exposed conditionally by the instrumentator (`main.py:88`).

| Prefix | Method + path | Auth | Notes |
|---|---|---|---|
| `/auth` | `GET /csrf` | none | issues cookie + token |
| | `POST /register` | none | **no rate limit** (`TRD-016`); 409 on duplicate = enumeration oracle |
| | `POST /login` | none | per-IP limiter, but see `TRD-003` |
| | `POST /logout` | session | **has `csrf_protect`** |
| | `GET /me` | session | |
| | `POST /change-password` | session | **has `csrf_protect`**; revokes nothing (`TRD-005`) |
| | `POST /delete` | session | **has `csrf_protect`**; soft delete only |
| | `POST /password-reset` | none | generic response; token logged (`SEC-02`) |
| | `POST /password-reset-confirm` | none | unthrottled; revokes nothing |
| `/market` | `GET /instruments` | session | `asset_class` filter never used by the client |
| | `GET /instruments/{id}/bars` | session | **no span or row cap** (`API-01`, `MD-12`) |
| | `GET /instruments/{id}/indicators` | session | caps rows *after* the query |
| | `GET /instruments/{id}/latest` | session | `QuoteOut` carries no timestamp (`MD-13`) |
| | `GET /instruments/{id}/signal` | session | "latest closed bar" is false >1m (`MD-01`) |
| | `POST /ws-ticket` | session | 30 s one-time Redis ticket — good design |
| | `WS /ws` | ticket | Origin allowlist + single-use ticket |
| `/public/markets` | `GET ""`, `GET /{ticker}`, `GET /{ticker}/bars` | **none** | crawlable; `/{ticker}` runs a full engine pass (`MD-04`) |
| `/public` | `GET /track-record` | **none** | loops the engine over every instrument (`MD-04`, `PERF-01`) |
| `/strategies` | `POST ""`, `GET ""`, `GET /{id}`, `POST /{id}/versions`, `GET /{id}/versions`, `GET /{id}/versions/{v}` | session | `list_strategies` hand-rolls the owner filter (`strategies/repository.py:46-50`) |
| `/backtests` | `POST ""`, `GET ""`, `GET /{id}` | session | |
| `/ai` | `POST /strategy`, `POST /explain` | session | inline LLM call, up to 180 s/360 s (`AI-16`) |
| `/paper` | `POST /deploy`, `GET /sessions`, `GET /sessions/{id}`, `POST /sessions/{id}/run`, `POST /sessions/{id}/stop` | session | run/stop unwired in the UI (`FE-10`) |
| `/calc` | `POST /position-size` | session | |
| `/alerts` | `GET ""` | session | read-only feed |
| (root) | `POST /brokers/connections`, `GET /brokers/connections` | session | accepts `env="live"`, **no gate, no delete, no audit** (`TRD-007`) |
| | `GET /live/preflight`, `POST /live/orders` | session | orders unconditionally 403 |
| (internal) | `POST /internal/tick`, `POST /internal/backfill` | shared secret | `include_in_schema=False`; backfill 422s unauthenticated (`OPS-01`) |
| (infra) | `GET /health`, `GET /ready`, `GET /metrics`, `/docs`, `/openapi.json` | mixed | `/metrics` token-guarded; `/docs` unconditionally public (`API-02`) |

**Owner scoping.** `/backtests`, `/strategies`, `/paper/*`, `/alerts`, `/brokers/connections`
all route through `OwnedRepository` (`core/repository.py:19-44`). The single exception is
`strategies/repository.py:46-50`, which hand-rolls `select(Strategy).where(owner_id == …)`
— correct today, but the one place the tenancy seam is bypassed.

**CSRF.** `csrf_protect` is applied to **3 of 21** unsafe routes (`TRD-004`, `SEC-04`). See
§7.3 for why the practical exploitability is narrower than the raw count suggests.

### 2.4 Models and tables

Nine tables, all registered on `Base.metadata` via `app/models.py`.

| Table | Module | Notes |
|---|---|---|
| `users` | auth | unique index on `email`; `totp_secret` column exists and is unused |
| `user_credentials` | auth | argon2id hash; `check_needs_rehash` upgrade on login |
| `broker_connections` | auth | `secret_ciphertext` (libsodium); `is_active` never toggled |
| `audit_log` | audit | insert-only; **written only by `auth`** (`TRD` §6.7) |
| `instruments` | market_data | unique `(symbol, asset_class)`; `calendar` ∈ `XNYS`/`24x7` |
| `instrument_sources` | market_data | per-symbol provider mapping + `is_primary` |
| `ohlcv` | market_data | Timescale hypertable when available; `source` written, never read (`MD-21`) |
| `strategies` / `strategy_versions` | strategies | `spec_hash` per version |
| `backtests` | backtesting | JSONB result snapshot, tail-truncated (`BT-24`) |
| `paper_sessions` | trading | JSONB snapshot; `session_start`/`last_run_at` are `timestamptz` |
| `alerts` | trading | `uq_alerts_session_id_dedup_key` — load-bearing for idempotency; `created_at` is **naive** (`TRD-023`) |

### 2.5 Migrations

Six revisions, single head, strictly linear:

```
0addaba53686  baseline: extensions, audit_log, users, broker_connections, user_credentials
  → ee76d2a81338  instruments / instrument_sources / ohlcv (+ conditional hypertable)
  → b13d9815e40d  strategies / strategy_versions
  → 91d0566854c9  paper_sessions
  → 8d734251ff4e  backtests
  → a3f7c2e91b44  alerts
```

Diffed model-by-model, column-by-column: **no drift**. `alerts` is fully migrated including
the unique constraint the idempotency design depends on (`trading/models.py:48-50` ↔
`a3f7c2e91b44:49`). Naming conventions in `core/db.py:26-32` produce stable constraint
names; `alembic/env.py:38-44` correctly excludes Timescale-managed objects from
autogenerate. This is the strongest single area of the backend.

Two problems sit on top of it:

- The baseline runs `CREATE EXTENSION IF NOT EXISTS vector` **unconditionally** at
  `0addaba53686:40`, twelve lines after a comment promising the migrations run on plain
  managed Postgres. `pgvector` is third-party and referenced by no model, query, or import
  anywhere. `citext` and `pgcrypto` are likewise created and unused (`DB-01`).
- Nothing guards *future* drift. `tests/conftest.py:59` builds the test schema with
  `Base.metadata.create_all`, not Alembic, and CI only proves `upgrade head` succeeds —
  there is no `alembic check` (`TEST-01`). The chain is correct by author discipline, not
  by a gate.

### 2.6 Worker and crons

`app/worker.py` registers `heartbeat` and `ingest_backfill` as callable jobs and two crons
(`worker.py:111-114`):

| Job | Schedule | Effect |
|---|---|---|
| `poll_quotes` | `second={0, 30}` | REST-poll each active instrument, upsert final bars, publish to Redis |
| `run_paper_sessions` | `second={15, 45}` | Advance every running paper session, dispatch alerts |

`ops_router.tick` (`ops_router.py:36-64`) is a faithful re-implementation of both crons for
hosts with no background process, including the same per-session try/rollback isolation.
The ~12 lines of duplication between `worker.py:75-93` and `ops_router.py:50-61` are
deliberate and documented; extracting one `advance_running_sessions(session)` helper would
remove the drift risk cheaply.

`ingest_backfill` is registered and **never enqueued** anywhere (`MD-20`). Neither
scheduler takes a lock, so overlapping ticks race (`TRD-015`), and blocking per-message
SMTP runs inside the sequential cross-owner loop (`TRD-014`).

### 2.7 Redis usage

Six distinct concerns, all with sane prefixes and TTLs:

| Concern | Key | TTL | Source |
|---|---|---|---|
| Sessions | `session:<token>` | 14 days, absolute | `auth/sessions.py:18` |
| Password reset | `pwreset:<token>` | 30 min, single-use | `auth/reset.py:10-29` |
| Rate limits | `rl:<identifier>` | per window | `core/ratelimit.py:29` |
| WS tickets | `wsticket:<t>` | 30 s, one-time | `market_data/realtime.py:28-48` |
| Bar pub-sub + last price | `bars:<id>` / `price:<id>` | — | `market_data/realtime.py:51-80` |
| AI budget | `aibudget:user\|global:<yyyymmdd>` | 48 h | `ai/budget.py:22-42` |

`RealtimeHub` (`realtime.py:83-134`) ref-counts one pub-sub subscription per channel and
drops for slow consumers rather than blocking — a good design. There is no per-user session
index, which is why `TRD-005` has no cheap fix.

### 2.8 Import contracts

`pyproject.toml` declares two contracts. The `forbidden` one (kernel must not import
domains) is **kept**. The `layers` contract is **broken at HEAD** and CI runs
`lint-imports` as a hard gate (`ci.yml:48-49`).

```
$ .venv/Scripts/lint-imports.exe   →   exit 1   ("Contracts: 1 kept, 1 broken")

app.modules.market_data is not allowed to import app.modules.backtesting:
  market_data/signal.py:33 -> backtesting.compute, backtesting.engine
  market_data/signal.py:34 -> backtesting.types
  market_data/router.py:20 -> backtesting.compute
app.modules.market_data is not allowed to import app.modules.strategies:
  market_data/signal.py:37 -> strategies.spec
  market_data/router.py:31 -> strategies.spec
```

Correct config locations (the raw finding's "`pyproject.toml:104`" was a misattribution —
line 104 is blank):

- `pyproject.toml:119` — the layer `"app.modules.strategies | app.modules.market_data"`.
  `|` is import-linter's *independent* delimiter, so the two siblings may not import each
  other either; that is why the `strategies.spec` edges count as violations.
- `pyproject.toml:124-128` — a now-false comment claiming `reference_backtest` /
  `public_router` are "the one allowed upward edge" and that "Everything else in
  market_data stays below backtesting."
- `pyproject.toml:129-135` — `ignore_imports`, waiving only the five
  `reference_backtest -> …` edges.

Both violating imports landed in `6428f60` ("F2: signal cards + on-chart indicator panel");
`ignore_imports` was last edited in the earlier `964567c` and never extended.

The architectural question underneath: the layering says market data sits *below*
backtesting, but three market-data modules now need the engine and the spec DSL. Either the
sanctioned list grows to six modules (making the comment permanently false), or the shared
math moves *down* into a layer both can see. The second is the honest fix — and is what the
uncommitted tree does (§2.12).

### 2.9 Generated contracts

`packages/contracts/openapi.json` is exported by `app/cli/export_openapi.py`, which forces
LF (`:20-24`); `.gitattributes` pins both generated artifacts to `eol=lf` so
`git diff --exit-code` is deterministic across Windows and Linux. CI regenerates and diffs
on both sides. This seam is well built and should be preserved as-is.

`packages/contracts/` contains **only** `openapi.json` — no package, no generated client,
no zod. The typed surface is `apps/web/src/lib/api/schema.ts` (2,910 lines, types only, via
`openapi-typescript`); the client at `apps/web/src/lib/api/client.ts` is hand-written.
`README.md:69` describes this as "OpenAPI spec -> generated TS client + zod", which is
wrong on both counts (`DOC-01`).

### 2.10 Infrastructure

`compose.yaml` (dev) and `infra/compose.prod.yaml` (prod) are clean, healthcheck-gated and
volume-backed. Caddy strips `/api` and proxies to `api:8000`, matching `Dockerfile.api:20`.
Both Dockerfiles are multi-stage and non-root with healthchecks. `deploy.sh` / `backup.sh` /
`restore.sh` are short and `set -euo pipefail`; `restore.sh` is a genuine
restore-*verification* (throwaway DB + table count), which most projects never write —
though the count-only smoke check would pass on an empty `ohlcv` restore, and the
TimescaleDB pre/post-restore calls are missing (`BACKUP-01`).

The observability profile does not work as shipped:

- `MetricsGuardMiddleware` (`core/security.py:110-117`) 404s `/metrics` unless
  `METRICS_TOKEN` matches. `infra/prometheus.yml:5-8` sends no credential and
  `METRICS_TOKEN` is set nowhere under `infra/`. Every scrape 404s (`OBS-01`). The gap is
  two-sided: supplying the token alone still fails, because the scrape config cannot present
  it. Impact is a silent monitoring blackout, not an exposure — the gate fails closed.
- `infra/grafana/provisioning/` contains only `datasources/datasources.yaml`. No dashboard
  JSON exists. `docs/DEPLOY.md:77-78` is honest about this, so it is a gap, not a false claim.
- The `grafana` service publishes no ports and Caddy has no route to it, so it is reachable
  only via `docker exec`/tunnel — which `DEPLOY.md:78` does state.

Container-image licensing is undocumented: TimescaleDB ships under the non-OSI Timescale
License, `redis:7-alpine` is a floating tag now resolving to RSALv2/SSPLv1, and the three
`grafana/*` images are AGPL-3.0 (`DEP-10`). Practical exposure is low — those restrictions
target offering the software *as a service* — but it should be a recorded decision.

### 2.11 CI and deploy targets

`ci.yml` runs three jobs. Gate status at HEAD:

| Gate | Command | Status |
|---|---|---|
| Lint (ruff check) | `ruff check apps/api` | pass |
| Lint (ruff format) | `ruff format --check apps/api` | **FAIL** (`CI-01`) |
| Types | `mypy apps/api/app` | pass (101 files) |
| Architecture | `lint-imports` | **FAIL** (`ARCH-01`) |
| Migrations | `alembic upgrade head` | pass; no `alembic check` (`TEST-01`) |
| OpenAPI drift | regenerate + `git diff --exit-code` | pass |
| Tests | `pytest --cov` | pass (78 tests); **no `--cov-fail-under`** |
| `pip-audit` | informational | `continue-on-error` (`DEP-12`) |
| `npm audit` | informational | `continue-on-error` (`DEP-12`) |
| TS types drift | `gen:api` + diff | pass |
| Frontend | lint / typecheck / build | pass; **no tests exist** (`FE-09`) |
| Secrets | gitleaks full history | pass; binary fetched with **no checksum** (`DEP-11`) |

Deploy targets, and what each omits:

| Target | Mechanism | Gaps |
|---|---|---|
| Render | `render.yaml`, Docker + `alembic upgrade head` in `dockerCommand` | no `FRONTEND_URL`, no SMTP, no `METRICS_TOKEN`; pins `AI_DEFAULT_PROVIDER=gemini` |
| Hugging Face Spaces | root `Dockerfile`, port 7860, migrate + seed on boot | same three gaps; guide publishes source to a **public** Space (`SEC-01`, `PC-19`) |
| Vercel (web) | dashboard-configured, no `vercel.json` | `NEXT_PUBLIC_SITE_URL` set nowhere (`FE-14`, `WEB-02`) |
| Self-hosted VPS | `infra/compose.prod.yaml` + Caddy | `NEXT_PUBLIC_*` passed at runtime, not build time (`FE-01`, `WEB-01`) |

### 2.12 Uncommitted working tree (not part of the baseline)

At the time of writing, the working tree contains a substantial in-flight refactor that is
**not** on `main` and is not counted anywhere above. Recorded here so the next reader is not
confused by a mismatch:

- Adds `app.modules.indicators` **below** `market_data` and moves `signal.py`,
  `reference_backtest.py`, `public_router.py` **up** into a new `app.modules.research` above
  `backtesting`. `ignore_imports` is deleted outright; `lint-imports` reports
  "Contracts: 2 kept, 0 broken". This is the structural fix `ARCH-01` recommends.
- `ruff format --check apps/api` returns exit 0 on that tree, resolving `CI-01`'s formatting
  half (but not its process half).
- `metrics.py` gains calendar-aware `periods_per_year()` and explicit sample-size floors,
  addressing `BT-04`/`BT-05`.
- `engine.py:206` reads `atr_arr[i - 1]`, addressing `BT-02`.
- `docs/DEPLOY_FREE_CLOUD.md` replaces the published key with per-secret generation commands
  and a shared-key warning, addressing `SEC-01`'s disclosure half (the ungated
  `/brokers/connections` endpoint is unchanged).

The action items for these findings are therefore **landing that work on `main`**, not
designing it.

---

## 3. Market data

### 3.1 What is right

- **Boundary normalization is clean.** `CanonicalBar` (`providers/base.py:16-26`) forces
  Decimal prices, tz-aware UTC bar-open timestamps, an explicit `is_final`, and provenance
  at the adapter edge. All three adapters honour it identically; no pandas/float types leak
  inward.
- **Portable aggregation.** `repository.py:176-190` uses `date_bin` + ordered `array_agg`
  rather than Timescale-only functions, so reads work on plain Postgres. The interval comes
  from a frozen whitelist (`repository.py:30-36`), so the f-string interpolation genuinely
  is injection-safe.
- **The conditional upsert.** `repository.py:85-97`
  (`ON CONFLICT DO UPDATE … WHERE is_final = false`) is a correct one-line expression of bar
  immutability, and `tests/test_market_data.py:60-77` proves it.
- **Indicator warm-up honesty.** NaN → `null` rather than back-fill (`router.py:86-93`).
- **Seed reconciliation.** `seed.py:65-97` drops de-listed sources and re-points primaries,
  so a provider switch is self-healing.
- **WS auth.** A one-time 30 s Redis ticket plus an Origin check is a sound answer to
  cookie-less cross-origin WebSocket auth.

### 3.2 Correctness defects

**`MD-01` — the trailing bucket is still forming (high).** `get_bars` filters `is_final` on
the raw 1-minute rows but never excludes the incomplete final bucket
(`repository.py:176-190`); every caller passes `end = datetime.now(UTC)`. At any timeframe
above 1m the last returned bar is the partial current bucket. Verification reframed this
from the original "look-ahead" claim to an **incomplete-bar / repainting** defect, and
narrowed the blast radius:

- *Primary impact — the signal card's contract is false.* `signal.py:99-104` evaluates the
  entry condition at `len(bars)-1` and returns that bucket's close as `reference_price` and
  its bucket-**start** timestamp as `as_of` (`:123`), while the module docstring
  (`signal.py:12-13`, "the engine reads at a closed bar, so it can never look ahead"), the
  response-schema docstring (`signal.py:52`, "closed bar") and the UI
  (`signal-card.tsx:113`, "Latest closed bar") all promise a closed bar. On
  a 1h spec the answer repaints minute-to-minute and `as_of` names a bar that will not close
  for up to 59 more minutes.
- *Reference backtest.* Runs the engine over a partial final bucket and, with
  `close_at_end=True`, flattens at that partial close. The accreting bucket also changes
  `data_fingerprint` on every poll, defeating the memo cache (see `MD-04`).
- *Paper trading — narrower than originally claimed.* Entry/exit **decisions** are already
  safe (`engine.py:264-265` skips the last bar) and bracket triggers on the partial bucket
  are monotone-stable, so no fill is invented or retracted. The residual defect is that
  stop-vs-target classification and exit price can change across the 30 s re-runs, leaving an
  already-emailed alert inconsistent with the stored snapshot. (The stronger "unretractable
  phantom fill alert" claim was **refuted** and is dropped.)
- *Charts.* A forming last candle is conventional charting behaviour and is the one caller
  that may legitimately want it.

**`MD-06` — no data-quality validation anywhere (high).** No check for non-finite values,
non-positive prices, `high < low`, or negative volume exists in the providers, in
`normalize_bars`, in `upsert_bars`, or as a CHECK constraint in the migration — zero
`CheckConstraint` hits across `apps/api`, zero `check` hits across `alembic/versions`.
Consequences, as verified:

- `Money` serializes a stored NaN to the literal JSON string `"NaN"`, which reaches the
  public chart, reference backtest, signals, backtests and paper trading.
- In the rollup, NaN propagates through `max(high)` and `sum(volume)`. It does **not**
  propagate through `min(low)` — Postgres `numeric` sorts NaN above all finite values, so
  `min` returns the smallest non-NaN low. (Correction to the raw finding, which claimed all
  three propagate.)
- The abort-on-NaN-volume behaviour is **yfinance-specific**: `yfinance_provider.py:34`
  wraps volume in `int()`, and `int(float('nan'))` raises `ValueError`, failing the whole
  backfill. `ccxt` and `alpaca` ingest a NaN volume silently instead.
- Repair is impossible through the app: `repository.py:96` blocks updates to final bars and
  no delete path exists. Worse, `upsert_bars` returns `len(rows)` regardless of how many the
  where-clause suppressed, so a corrective re-ingest **reports success while writing nothing**.

**`MD-07` — no corporate-action handling (high).** The only corporate-action token in the
repo is `auto_adjust=False` at `yfinance_provider.py:48`. No splits/dividends table, no
adjustment factor, no `Adj Close` read, no re-adjustment job. Verification widened and
sharpened this:

- It affects **both** equity providers — `alpaca_provider.py:52-59` omits the `adjustment`
  field, so Alpaca's API default `raw` applies.
- The precise mechanism is the reason it is permanent: Yahoo retroactively split-adjusts
  history at fetch time, so bars persisted before a split keep the pre-split scale while bars
  fetched after arrive post-split — and `repository.py:96` refuses the corrective overwrite.
  The vendor would fix it; the upsert won't accept the fix.
- Concretely: `engine.py:239-241` stops out every long position at the post-split open,
  recording a fabricated catastrophic loss in drawdown, Sharpe and the equity curve.
- One sub-claim is **corrected**: an ex-dividend gap is a real price move, not an artifact.
  For dividends the (lesser) defect is total-return accounting — a position held through the
  ex-date is never credited the distribution.
- Disclosure gap confirmed: corporate actions appear nowhere in `/methodology`'s
  `NOT_CLAIMED` list or `README.md:94`.

**`MD-02` — `time_of_day.timezone` is accepted then ignored (medium).** `spec.py:155`
declares `Literal["exchange","utc"] = "exchange"` under `extra="forbid"`, and it is read by
nothing. The engine compares UTC wall-clock minutes (`engine.py:269`) and never receives the
`Instrument`, so there is no exchange-timezone plumbing to honour it. Verification trimmed
two sub-claims: the "almost entirely pre-market" framing does not hold on the default data
path (yfinance defaults `prepost=False`, so a 09:30–16:00 "exchange" window silently
truncates to the morning third of the session, 09:30–12:00 ET), and the UTC daily-loss reset
is **latent**, not live, because neither supported calendar is cut mid-session by UTC
midnight. The field is actively offered to users by the AI prompt (`ai/prompts.py:35`), so
specs carrying it are routinely produced.

**`MD-03` — XNYS session window hardcoded to EDT (high).** `streaming.py:27-28` fixes the
session at 13:30–20:00 UTC with no `America/New_York` conversion (zero zoneinfo usage
anywhere in `apps/`). Under EST the real session is 14:30–21:00 UTC, so the closing hour
15:00–16:00 ET is **never polled** on any winter trading day, and 08:30–09:30 ET pre-market
is polled instead. This is not a stub: `poll_and_publish` is the only scheduled writer of
OHLCV bars, and nothing backfills the gap, so the winter closing hour is missing from the
persisted store and from paper-session evaluation — not merely from the WS feed. The two
existing tests (15:00 and 12:00 UTC) both land on the same side of the boundary under either
regime. Adjacent defect: the window is applied to any calendar that is not literally
`"24x7"`, so a future non-US calendar silently inherits NYSE hours.

**`MD-11` — UTC-origin bucketing ignores exchange sessions (medium).** `date_bin` bins from
the 1970 UTC epoch, so 4h buckets fall at 00/04/08/12/16/20 UTC and chop the US session into
a 2.5h bucket, a full bucket, and (in winter) a one-hour bucket. No 4h bar corresponds to any
session-anchored convention. 1d is correct for crypto and *incidentally* correct for RTH-only
equities, and breaks the moment extended-hours data or a non-US venue is added.

**`MD-09` — weak data fingerprint (medium).** Hashes only
`instrument|timeframe|count|first_ts|last_ts|first_close|last_close`. Back-filling interior
minutes inside already-populated hourly buckets changes those buckets' high/low/volume but
changes neither the count nor the endpoints, so the fingerprint is unchanged and a stale
summary is served. The methodology page advertises this fingerprint as a reproducibility
guarantee.

### 3.3 Availability and abuse

**`MD-04` — unauthenticated engine runs per request (high).** `GET /public/markets/{ticker}`
pulls 365 days of aggregated bars and runs a full engine pass;
`GET /public/track-record` does that **for every instrument**. Verification made three
corrections, two weakening and one strengthening:

- *Weaker:* churn is ~1,440 distinct fingerprints/day/symbol, not ~2,880 — a new final 1m bar
  lands at most once per minute, not per 30 s poll.
- *Weaker:* the cache leak is not attacker-amplifiable. Entry count is bounded by the
  data-change rate regardless of request volume, so it is a slow leak of small frozen
  dataclasses, not a request-driven memory DoS.
- **Stronger (the raw finding understated it):** the expensive read happens *before* the
  cache is consulted. `reference_backtest.py:194-196` runs the unlimited 365-day aggregation,
  and only then checks `_CACHE`. Even a 100% hit rate still costs one full-year query per
  instrument per request — five per `/public/track-record` call. The cache never shields the
  database at all.

Net: one anonymous IP gets 120 req/min (the tighter 30/min bucket matches only paths ending
in `/bars`), and each track-record request costs five unlimited year-long scans plus,
on the ~1/min fingerprint rollover, five full Decimal engine runs over up to ~8,760 bars each.
No `Cache-Control` anywhere in the API, in Caddy, or in `next.config.ts`; the ticker page
uses `cache: "no-store"`.

**`MD-05` — rate limits bypassable (high).** `_client_ip` returns the leftmost
`X-Forwarded-For` hop unconditionally; the docstring states the intent outright. No mitigation
exists at any layer: uvicorn is started with no `--forwarded-allow-ips` in any of the three
Dockerfiles/`render.yaml`, and Caddy's bare `reverse_proxy` *appends* to the header, leaving
the attacker's value leftmost. Scope correction: the login and password-reset limiters use a
**separate** `_client_ip` that ignores the header, so those two buckets are not
header-spoofable — they instead carry the inverse defect (`TRD-003`).

**`MD-12` / `API-01` — authed bars endpoint has no cap.** The public twin enforces
`_MAX_SPAN` per timeframe and a row limit; the authed endpoint — the one the charting
workspace actually uses — validates only `start < end`. A signed-in user can request five
years of 1m bars and force an unbounded scan, materialized fully in Python before the
`bars[-1500:]` slice.

**`MD-14` — the limit bounds the payload, not the scan.** For aggregated timeframes the
`GROUP BY bucket` scans every raw 1m row in the window before `LIMIT` applies. Separately,
every `_MAX_SPAN` entry exceeds `_MAX_PUBLIC_BARS` at its own timeframe, so a max-span request
*always* truncates to the most recent 1,500 bars with no `has_more` flag (`MD-22`).

### 3.4 Operational gaps

`MD-15` (provider construction outside the `try`, so one bad instrument kills the whole poll
cycle — latent while Alpaca stays non-primary, but total when it fires), `MD-16` (yfinance 1m
requests not chunked against Yahoo's ~7-day limit; CCXT pagination uncapped), `MD-17` (the
forming→final lifecycle is dead code — nothing ever writes `is_final=False`, so the documented
lifecycle does not exist in the running system), `MD-26` (no gap detection or fill; the
`resume_start` watermark is unreachable in production), `MD-18` (no retention or compression
policy on a hypertable that accrues ~2.6M rows/year at five instruments, on free-tier Postgres).

### 3.5 Data licensing

**`MD-08` (high, judgment call).** Yahoo is the **primary** equity source (`seed.py:28,36,44`,
`is_primary=True`), and those bars are served with no auth on pages deliberately made
indexable (`robots.ts:12-13` comments that `/markets` is "intentionally allowed";
`sitemap.ts:17-22` emits one entry per ticker). A repo-wide grep for
`yahoo|redistribut|attribution|non-commercial|data licen` returns two hits, neither about
market data. Evidence the raw finding missed: `/methodology` contains a section titled
literally **"Market data & provenance"** whose two bullets cover polling cadence and the
absence of a SIP claim — a section named "provenance" that names zero data sources. The
public ticker footer likewise carries no attribution.

Two scope corrections: Alpaca/IEX is presented as an active exposure but is seeded
`is_primary=False` and key-gated, so it is latent; and this is a legal/documentation posture
gap, not a runtime code defect. `high` is defensible pre-deploy given the pages are
intentionally crawlable, but it is a judgment call rather than a demonstrable failure.

Compounding it, `DEP-01` records that yfinance's HTTP layer forges a Chrome TLS fingerprint
(`curl_cffi` `impersonate="chrome"`) specifically to defeat Yahoo's anti-automation controls —
so the acquisition path, not only the redistribution, is adversarial.

---

## 4. Backtesting — summary

> **Deep dive:** [`QUANT_CORRECTNESS_AUDIT.md`](./QUANT_CORRECTNESS_AUDIT.md). This section
> is a summary only; evidence, reproductions and per-defect remediation live there.

**Verdict.** The engine's *architecture* is genuinely good and should be preserved: one
implementation shared by backtests, paper trading, live signals and the public reference;
Decimal money end-to-end; closed-bar decisions with next-open fills; risk limits that are
enforced rather than decorative; no leverage and no negative cash (a 20k-iteration Decimal
fuzz found a worst-case overspend of 5e-22, pure 28-digit rounding).

The defects cluster in three places.

**1. Intrabar path handling.**
`BT-02` (high) — ATR sizing reads the fill bar's own high/low, confirmed by perturbing only
bar 3's H/L with open and close held fixed: qty 142.857 → 21.739, equity 99995.29 → 99999.28.
It contradicts `/methodology`'s "No same-bar hindsight" and diverges from `signal.py:110`,
which sizes off the last *closed* bar — so the same spec sizes differently live versus
backtested. The existing canary cannot detect this class, because it only perturbs bars after
the cut and its spec uses `percent_equity` sizing.
`BT-01` (high) — the trailing stop ratchets from *this* bar's high and then applies the
gap-through test against the post-ratchet level, so a normal trailing exit is misclassified as
a gap and books the open. Verified trigger condition is an intrabar rally of `pct/(1-pct)`
from the open (11.11% for a 10% trail), not "more than the trailing distance". The bias is
uniformly **pessimistic**, so it mis-ranks strategies rather than flattering them; and
`grep -rn "trailing" apps/api/tests` returns zero hits.
`BT-13` (low) — a take-profit (a limit order) is charged adverse slippage.

**2. Silently ignored spec fields.** `BT-03` (high) `entry_short` is declared, fully
reference-walked by the validator, advertised to the LLM verbatim, exposed in the generated
client schema — and consumed by no execution path. A long/short spec is truncated in
backtests, paper runs **and** live signals, with no warning: `BacktestResult` has no warnings
field and `RiskEvent.kind` enumerates only three risk kinds. It is reachable by pasted JSON
through the UI, not only via the AI. Also `BT-06` (`max_open_positions`), `BT-07`
(`time_of_day.timezone`), `BT-15` (multi-symbol `universe` silently uses `universe[0]`).

**3. Metrics.** `BT-04` (high) — `ppy = (365*24*60)/_TF_MINUTES[tf]` from the timeframe string
alone; bars are not gap-filled, so an equity's bar count reflects only sessions while `ppy`
assumes calendar time. At 1d the CAGR exponent is 1.45x too large and Sharpe 1.20x; at 1h,
4.97x and 2.23x. Correction: the public track-record path is **already mitigated** (all three
annualized metrics are stripped before any public surface), so the live blast radius is the
**authed** backtest path, where users can select any of six timeframes for an XNYS equity.
`BT-05` (high) — no minimum-sample guard; an independently reproduced 5-point curve yields
Sharpe 39,367,736 at `1d` and 1,493,900,568 at `1m`. The counterargument that retaining these
is deliberate ("real users see the caveats") does not hold: the caveat that actually renders
discloses only the risk-free rate, never sample size. Also `BT-11` (Sortino uses dispersion of
losses about their own mean, not downside deviation), `BT-12` (`profit_factor` returns gross
dollars when there are no losses — and reaches a crawlable page).

**Indicator fidelity.** `BT-18` RSI returns NaN rather than 100 when there are no losses, so
`RSI > 70` momentum entries silently never fire in the strongest uptrends — a
direction-dependent, invisible bias. `BT-19` non-Wilder seeding puts RSI(14) 7.9 points off
TA-Lib at index 14. `BT-20` VWAP is cumulative from the first loaded bar, so results depend on
the query start date.

**Testing.** `BT-22` — `tests/test_backtest.py` is 125 lines and is the entire quant-correctness
suite. No test anywhere asserts an exact fill price, commission amount, or metric value.
Untested: targets, trailing stops, time-exit timing, same-bar entry→exit, both halts, both
clamps, the time-of-day filter, and every function in `metrics.py`. `hypothesis` is a declared
dev dependency with zero uses.

---

## 5. AI — summary

> **Deep dive:** [`AI_SYSTEM_AUDIT.md`](./AI_SYSTEM_AUDIT.md).

**The core safety invariant holds and is verifiable — preserve it.** `ai/service.py` imports
only `budget`, `prompts`, `providers.base`, `strategies.spec` and kernel modules. No trading,
live or backtesting import; no `eval`/`exec`/subprocess; no persistence. The only external
importer of `app.modules.ai` is the router mount in `main.py`. The ARQ worker has no AI job.
The claim "No AI code path can place an order" is **true**, and the import-linter layer
contract structurally keeps it true. The validate-and-repair loop is also the right shape:
bounded at three calls, re-prompted with the concrete Pydantic error, failing closed with a
400 rather than returning a half-valid object.

**`AI-01` (medium) — `/ai/explain` narrates arbitrary client-supplied numbers.**
`context: dict[str, Any]` is unconstrained and passed verbatim into the prompt; `AIService`
has no DB session at all, so "grounded" is a prompt instruction that is unverifiable
server-side. Verification downgraded this from high and corrected the framing: it is **not**
an authz vulnerability — the endpoint is auth-gated and the explanation is ephemeral client
state, so a fabrication harms only the caller's own view. Note `/methodology` is correctly
hedged ("are instructed to") and is not itself false; the dashboard and landing copy are not.
The more concrete defect on the same line is availability (see `AI-03`) plus an unfiltered
prompt-injection channel. *(The separate finding proposing prompt delimiting as its own issue
was refuted and is dropped.)*

**`AI-03` (high) — the token budget is advisory.** `check` reads before the call, `record`
increments after; no reservation, no per-request ceiling, up to three provider calls per
single check, and no dedicated `/ai/*` rate limit despite `enforce_rate_limit` being used for
login. Two details make it worse than stated: the 2 MB body cap is only enforced when
`Content-Length` is present (a chunked request bypasses it entirely), and `maxOutputTokens` is
never set, so output tokens are uncapped too. `AI-04` compounds it — `record()` returns early
on `tokens <= 0`, so a response lacking usage metadata is free and uncounted forever.

**`AI-11` (high) — no per-run record of any kind.** One log line exists in the whole module
(`service.py:58`, the repair counter). No success log, no latency, cost, model, provider,
token count or prompt version; no `ai_runs` table; no Prometheus collector; the audit module
is never imported. Correction: that one line *does* carry `request_id`/`user_id` via the
structlog processor, so user attribution is not the gap. The finding **understates** one thing:
AI failures are logged nowhere at all — every provider error is an `AppError`, and the
`_app_error` handler returns a problem response without logging. A total provider outage would
be visible only as HTTP status codes.

**`AI-12` (high) — no evaluation harness.** Zero coverage for `gemini.py`, `ollama.py`,
`factory.py`, the `/ai/explain` endpoint, and the global budget cap; no eval corpus, golden
files or CI scoring. Correction: the claim that both prompt builders are uncovered is **false**
— both have full line coverage; what is missing is any *assertion* on their output.
Supporting evidence the raw finding missed: the happy-path test is circular (the fake echoes
the fixture and the test asserts the fixture's own name), and disclaimer compliance is asserted
against a string the fake was hardcoded to return.

**`AI-08` (medium) — third-party egress disclosure.** Gemini is the default in `config.py:69`,
`Dockerfile:27` and `render.yaml`, and user strategy text plus full backtest JSON are POSTed to
Google. Verification **corrected the headline**: the raw claim "undisclosed anywhere" is wrong —
`README.md:37` names Google Gemini, `.env.example:62-68` documents both providers, and three
deploy docs instruct obtaining a Google key. What is genuinely missing is (a) any in-product
notice at the point of submission, (b) any privacy policy or terms page anywhere under
`apps/web/src`, (c) the free-tier data-usage caveat, and (d) a startup log naming the active
provider. Downgraded to medium for a self-described personal-first project; it becomes high the
moment third-party users are onboarded.

Also: `AI-05` (no capabilities/health/retry/fallback/circuit-breaker — and a new
`httpx.AsyncClient` per call, multiplied 3x by the repair loop), `AI-06`/`AI-07` (the local
Ollama path is nominal — model hardcoded, never passed by the factory, unreachable in every
shipped container), `AI-09` (the "every response ends with a disclaimer" guarantee is
unenforced and false for `/ai/strategy`, which returns JSON), `AI-10` (no prompt versioning;
`DSL_GUIDE` hand-duplicates `spec.py` with no drift guard and omits every numeric constraint
the validator enforces), `AI-16` (a 180 s/360 s worst case inline on the request path,
contradicting ADR-0002, with no client `AbortController`).

---

## 6. Paper trading and the live seam

### 6.1 There is no order model

`PaperService.run_session` fetches bars for `[session_start, now]`, calls
`engine.run(..., close_at_end=False)`, and serializes the whole result into
`paper_sessions.snapshot` (JSONB). There is no orders table, no positions table, no fill/ack
lifecycle, no cash ledger outside the engine's in-process run, and no reconciliation. This is
defensible as an MVP, but it means the **only** idempotency in the system is the alert dedup
key — there is no order idempotency because there are no orders, even though
`brokers/base.py:13` advertises `client_order_id  # idempotency key` for a type nothing
constructs.

`README.md:62` describes `trading/` as "paper engine, **portfolio**, brokers + gated live
seam". No portfolio component exists (`DOC-01`).

### 6.2 Engine parity, warm-up and silent no-ops

Parity with backtesting is real — the same `engine.run` is called — but only for an identical
bar window. `MD-01` (§3.2) is the timing caveat. Beyond it, `TRD-022` (medium): `session_start`
is pinned at deploy and used as the window start, so the engine sees **zero warm-up history** —
an SMA(30) on 1h produces nothing for the first 30 hours. Meanwhile `if len(bars) >= 2` skips
the run but still stamps `last_run_at`, so the UI shows a session that "ran" seconds ago with
`snapshot: null`. (`BASELINE_VERIFICATION.md` independently observed a paper session producing
no snapshot.) Separately, `run_session` returns silently when no instrument matches
`paper.symbol` — no log, no status change — making a session pointed at a removed symbol
indistinguishable from a healthy one.

### 6.3 Scheduling and concurrency

Two schedulers advance sessions and **neither takes a lock** (`TRD-015`): the 30 s cron and
`POST /internal/tick`, which is always armed on Render. There is no advisory lock, `SETNX`, or
`with_for_update` anywhere in `apps/api/app`. Overlapping ticks — or a cron tick racing a user's
`POST /paper/sessions/{id}/run` — both pass the dedup pre-check and both insert. The unique
constraint catches it, which is the correct backstop, but the `IntegrityError` is unhandled on
the request path and surfaces as a 500.

`TRD-014` (medium): `dispatch_snapshot_alerts` awaits SMTP per alert, and `_send_sync` opens a
fresh connection with `starttls()` + `login()` and a 15 s timeout per message. Twenty alerts is
up to 300 s of blocking inside the sequential cross-owner loop, stalling every other owner's
session — and the same code runs inside the `POST /paper/deploy` and `/run` handlers, so a
deploy can hang a request for minutes. There is no cap on paper sessions per user to bound it.

`TRD-027` (low): the alert dispatcher commits the caller's **request-scoped** session mid-request.
The commit-before-email ordering is correct and well-reasoned; the problem is that it borrows the
caller's unit of work, so `/paper/deploy` promotes partially-built state to durable before the
handler completes.

### 6.4 Deleted accounts keep trading

`TRD-013` (medium): `deactivate` is a soft delete; `all_running_sessions` selects purely on
`status == "running"` with no join to `users`, and the alert recipient is resolved with no
`is_active` check. A user who deletes their account keeps receiving paper-trading alert emails
indefinitely, and their sessions keep consuming cron time.

### 6.5 Audit trail

`audit.record` has exactly five call sites, all in `auth/router.py`. Nothing in the trading
module records anything — storing a broker credential, attempting a live order, deploying or
stopping a session all produce no `audit_log` row. For an app whose `SECURITY.md` describes
itself as storing broker API keys, credential creation with no audit entry is the notable gap.

### 6.6 The live seam is sound

I looked for a path to real-money execution and there is none:

- `LiveTradingGate.evaluate` defaults `user_opted_in`, `twofa_enabled`, `recent_step_up` and
  `confirmation_valid` to `False` (`live_gate.py:42-52`).
- `live_router.py:56-58` passes **only** `confirmation_valid`; every other flag stays `False`,
  so even with `LIVE_TRADING_ENABLED=true` the gate returns three blocking reasons and raises 403.
- `live_router.py:59-61` then raises an **unconditional** `PermissionDeniedError` after the gate,
  so the endpoint cannot fall through even if the gate were satisfied.
- `AlpacaBrokerAdapter.submit_order` has zero callers repo-wide (`DEAD-01`, `TRD-021`).

The one missing test is the important one: assert the gate still refuses with
`live_trading_enabled=True` (`TRD-025`).

**Precision note for the docs.** `SECURITY.md:24-26` describes a control stack of "step-up 2FA,
opt-in, kill-switch, enforced risk + per-order confirmation". None of those are implemented —
`User.totp_secret` is an unused column, and the gate's own docstring says the controls are
deferred. The *outcome* (refusal) is correct and safe; the *described controls* do not exist
(`TRD-014` doc half, `PC-14`).

### 6.7 Live credentials are accepted anyway

`TRD-007` (medium) / `SEC-01` aggravating factor: `BrokerConnectionCreate.env` is
`Literal["paper","live"]` and `POST /brokers/connections` passes it straight to encryption and
persistence with no gate check, no audit record, and no reference to `LIVE_TRADING_ENABLED`.
The endpoint is guarded only by `CurrentUser` — any self-registered user. There is no
delete/revoke endpoint (`is_active` is set `True` at creation and never toggled), and no
frontend consumer exists at all. So the app that "structurally cannot" trade live will take
custody of live-account API keys, encrypted — on the documented public deploy — with a key
published in the repository.

`TRD-008` (medium): ciphertext carries no key id or version prefix, so rotating
`BROKER_CRED_KEY` silently bricks every stored credential with no way to tell which key
encrypted which row.

---

## 7. Security

### 7.1 What is strong

Password handling (argon2id with transparent `check_needs_rehash` upgrade and a pre-computed
dummy verify to equalize timing on the no-user path), opaque random session tokens with all
state in Redis under TTL, correct `__Host-` prefix conditioning with `domain=None`, WS ticket
auth, the tenancy seam, `get_owned` returning 404 rather than 403 so non-ownership does not
leak existence, RFC 9457 problem+json errors, and secrets hygiene (only `.env.example` files
tracked; gitleaks in pre-commit *and* full-history CI).

### 7.2 Credential and token exposure

**`SEC-01` (high).** `docs/DEPLOY_FREE_CLOUD.md:41` instructs the deployer to set
`BROKER_CRED_KEY = 879Ab…VWmk=` (redacted here; the full 44-character value is in git history), labelled "(test key)". It
base64-decodes to exactly 32 bytes — a structurally valid `SecretBox` key, not a placeholder —
and it is the **only** non-blank `BROKER_CRED_KEY` value in the repo; every other reference is
blank or a generate-command. The "(test key)" label does not restrict its use: it sits in the
production secret list beside the real Neon `DATABASE_URL` and a freshly-rotated
`GEMINI_API_KEY`. Public exposure is confirmed by the same document, which mandates a Public
Space and then force-pushes the entire tree including `docs/` to it. It contradicts
`SECURITY.md` on three counts (broker credentials encrypted at rest; "real secrets never live
in the repo"; gitleaks "fails the build" on a committed secret — CI is green, corroborating
that gitleaks does not flag a bare base64 value).

The aggravating factor the raw finding missed: `crypto.py:5`'s "Dormant until Phase 8" docstring
is inaccurate, because `POST /brokers/connections` is mounted unconditionally and gated only by
`CurrentUser`. On the exact public deploy this guide produces, any self-registered user's real
broker API key/secret is encrypted at rest with a key published in the repository — anyone
holding the DB contents can decrypt them offline.

*Correction to location:* line **41**, not 39 (line 39 is `DATABASE_URL`).

**`SEC-02` / `TRD-012` (high).** `auth/router.py:168` builds the reset URL from
`frontend_url`, defaulting to `http://localhost:3000`, and `core/email.py:23` logs the **full
body** — including the live reset URL and token — at INFO whenever SMTP is unconfigured.
Verified empirically with the repo's own structlog: positional args are interpolated, producing
`{"event": "email_not_configured to=… body=…token=SECRET…", "level": "info"}`, and
`core/logging.py` applies no redaction processor.

Deploy coverage is **worse** than the raw finding claimed: a repo-wide grep for
`FRONTEND_URL|SMTP` hits only `.env.example`, `config.py` and `router.py` — zero mentions in
`render.yaml`, the root `Dockerfile`, `infra/.env.prod.example`, `infra/compose.prod.yaml`, or
any of the three deploy guides. The compounding effect: because SMTP is unset everywhere, **no
reset email is ever sent in production**, yet the endpoint still returns `{"status": "ok"}`.
The result is a 100%-broken reset flow where the only copy of the live 30-minute single-use
token lands in stdout — and `infra/compose.prod.yaml` ships stdout to Loki. The flow is
reachable, not dead code (both `/forgot-password` and `/reset-password` pages exist), and no
startup guard fails closed. The same log path also leaks paper-trading alert bodies
(`alerts.py:177`).

### 7.3 Session and CSRF

**`TRD-001` (high) — logout does not clear the cookie in production.**
`clear_session_cookie` calls `delete_cookie(key=…, path="/")` without `secure=`. Starlette
defaults `secure=False`, so in production the emitted header is
`Set-Cookie: __Host-session=""; …; Path=/; SameSite=lax` with **no `Secure`** — verified by
running the vendored library. Browsers reject a `__Host-`-prefixed cookie lacking `Secure`, so
the deletion is discarded.

This is **not** an authentication bypass — the Redis session is revoked first, so the stale
cookie grants nothing. It is a **redirect trap**: `proxy.ts:41` gates on cookie *presence* and
lists `/login` in `AUTHED_REDIRECT_PATHS`, so the post-logout `router.replace("/login")` bounces
to `/dashboard`, whose data fetches 401. After logging out in production a user cannot reach
`/login` again without manually clearing cookies. Invisible locally (`cookie_secure=False`
yields the plain name) and in CI (httpx does not enforce `__Host-` rules). The `csrf_token`
cookie is never cleared at all.

**`TRD-005` (high) — password change and reset revoke nothing.** Neither handler calls
`revoke_session`, rotates the current token, or invalidates other sessions; `password-reset-confirm`
additionally has no rate limit and no audit record. Sessions are keyed `session:<token>` with the
user id only inside the value, so "revoke every session for user X" is not expressible without a
full `SCAN`. The 14-day TTL is absolute and never refreshed on read, so a cookie stolen before a
reset stays valid for the remainder of those 14 days. Nuance: a de-facto global kill switch
exists (`deactivate` flipping `is_active`, which `get_current_user` rejects) but is wired only
into account deletion — the reversible per-user revocation is genuinely absent. Login itself
correctly mints a fresh token, so session *fixation* is handled.

**`TRD-004` / `SEC-04` (medium) — CSRF on 3 of 21 unsafe routes.** Enumerating every route
decorator: 21 unsafe routes exist, all POST (no PUT/PATCH/DELETE anywhere). 18 lack
`csrf_protect`; two are shared-secret guarded and four are pre-auth, leaving **13
cookie-authenticated state-changing endpoints** unprotected. Verification narrowed
exploitability materially: 10 of the 13 require a Pydantic JSON body, and FastAPI rejects
`text/plain` and form encodings with 422 — so a cross-site HTML form, the only cross-origin POST
that skips preflight, cannot reach them. The genuinely form-postable ones are the three no-body
routes (`/paper/sessions/{id}/run`, `/stop`, `/market/ws-ticket`). Combined with `SameSite=lax`
there is no working exploit against a current browser. It is a defense-in-depth gap that becomes
real under a same-site attacker (sibling-subdomain XSS, which bypasses Lax entirely). The client
already sends the header on every unsafe method, so enabling it is nearly free.

### 7.4 Rate limiting and client-IP resolution

Two `_client_ip` helpers with opposite trust models, both wrong in opposite directions, is the
crisp statement of this cluster.

- `core/ratelimit.py:42-47` trusts the leftmost `X-Forwarded-For` hop unconditionally →
  every middleware-enforced budget is bypassable (`MD-05`, `TRD-002`, `SEC-03`).
- `auth/router.py:38-39` uses `request.client.host` only → behind any proxy the login and
  password-reset limiters collapse to **one platform-wide bucket** (`TRD-003`). Because
  `enforce_rate_limit` runs *before* credential verification, ~11 requests/minute from any
  unauthenticated visitor denies login to everyone. Every `audit_log` row also stores the proxy
  IP, so the audit log has no real client IP for any event.

*Mechanism correction:* the raw finding blamed a missing `--proxy-headers`. In the pinned
uvicorn 0.48.0 `proxy_headers` already defaults to `True`; the actual cause is
`forwarded_allow_ips`, which defaults to `127.0.0.1`, and a repo-wide grep finds it set nowhere.
The conclusion is unchanged; enabling `--proxy-headers` alone would be a no-op.

Availability note: `RateLimitMiddleware.dispatch` catches only `RateLimitedError`, so an
unreachable Redis makes the API return 500 for **every** request. Fail-closed, but total.

### 7.5 Other application-security findings

`TRD-009` (medium) — `AppError` renders `exc.detail` verbatim at `exc.status_code` with **no
logging**, and `AppError`'s base status is 500. So `AppError("BROKER_CRED_KEY is not
configured.")` returns a 500 whose body contains the internal message, and it never appears in
the logs. Both halves are backwards relative to the module's own docstring.

`TRD-010` (medium) — `hmac.compare_digest` raises `TypeError` on non-ASCII `str`. Three call
sites take attacker-controlled strings: `/internal/tick` (a 500-vs-404 difference reveals
whether the endpoint is armed, defeating its stated design), `/metrics`, and the CSRF header
(500 instead of 403).

`TRD-011` (medium) — `BodySizeLimitMiddleware` only inspects the declared `Content-Length`, so a
chunked request skips the check entirely and streams into memory.

`TRD-016` (medium) — `/auth/register` has no rate limit at all and returns a 409 that positively
confirms account existence, defeating the enumeration defence that the reset flow implements
carefully. It also has a TOCTOU (select-then-insert) yielding an unhandled `IntegrityError`.

`MW-01` / `TRD-024` (low) — `add_middleware` prepends, so `SecurityHeadersMiddleware` is
**innermost**. Responses short-circuited by outer middleware (429, 413, the `/metrics` 404) ship
without `nosniff`, `X-Frame-Options` or HSTS.

`API-02` (low) — `/docs` and `/openapi.json` are unconditionally public in production and
explicitly exempted from rate limiting, publishing the entire route surface anonymously —
inconsistent with the deliberate 404-on-`/metrics` and 404-on-`/internal/*` hardening elsewhere.

`CFG-01` / `TRD-020` (medium) — `APP_SECRET_KEY` has **zero** references outside its
declaration, yet `.env.example:13` documents it as "Secret used to sign CSRF tokens" and
`render.yaml` auto-generates it as a required secret. CSRF tokens are unsigned
`secrets.token_urlsafe(32)`. An operator rotating it after an incident would believe they had
invalidated tokens. `app_name` and `sync_database_url` are likewise unreferenced.

`TRD-019` (medium) — CSP sets `script-src 'self' 'unsafe-inline'` with no nonce (load-bearing
for the pre-paint theme script, and honestly documented) and `connect-src 'self' ws: wss:`,
which permits a WebSocket to **any** host — a ready-made exfiltration channel. `object-src` is
absent.

`TRD-026` (medium) — the position-size calculator silently substitutes a different sizing method
when inputs are unusable (ATR missing, or `stop >= entry`, a plausible typo) and then reports
`risk_amount = 0`. A risk calculator reporting zero risk for a real position is the wrong
failure mode.

---

## 8. Frontend and product UX

### 8.1 Route inventory

**Public** (no session per `src/proxy.ts:14-20`):

| Route | File | Notes |
|---|---|---|
| `/` | `app/page.tsx` | hero, 6 feature cards, server-rendered `<TrackRecord/>`, 4 stat tiles, CTA |
| `/methodology` | `app/methodology/page.tsx` | 7 sections + a genuinely rare "what we deliberately don't claim" list |
| `/markets/[ticker]` | `app/markets/[ticker]/page.tsx` → `market-view.tsx` | delayed price, chart, indicators, reference backtest, FAQ, `FinancialProduct` + `FAQPage` JSON-LD |
| `/robots.txt`, `/sitemap.xml`, `/manifest.webmanifest`, `/opengraph-image`, `/apple-icon`, `/icon.svg` | metadata routes | `SITE_URL` placeholder issue (`FE-14`) |

**`(auth)` group:** `/login` (dual login/register toggle), `/forgot-password`,
`/reset-password`. There is **no `(auth)/layout.tsx`** — each page re-implements the same
centered card (`FE-19`).

**`(app)` group** (gated by `proxy.ts:43-50` and re-checked in `(app)/layout.tsx:15-18`):
`/dashboard`, `/markets`, `/chart/[id]`, `/strategies`, `/backtests`, `/paper`, `/calculator`,
`/alerts`, `/account`.

`/account` is **not in the sidebar** — its only entry point is the user's email rendered as
muted text in `user-menu.tsx:25-31`, which reads as a label rather than a link (`FE-20`).

### 8.2 Existing vs. target v2 navigation

| v2 nav item | Status | Evidence |
|---|---|---|
| Overview | **partial** | `/dashboard` exists; "Portfolio Value" is a naive client-side float sum of Decimal strings (`FE-07`); "AI Insights" is static copy with no AI call (`PC-22`) |
| Markets | **partial** | flat table; no asset-class filter (the `api.instruments(assetClass)` param is never passed), no screener, no sparklines |
| Research | **missing** | no route, no component, no backend endpoint at HEAD |
| Strategies | **partial + mislabeled** | a raw `<textarea rows={16}>` of spec JSON plus an AI prompt; no detail page and no version UI despite `/strategies/{id}/versions` existing (`FE-10`) |
| Backtests | **partial (strong core)** | full result UI; missing run comparison, benchmark overlay, parameter sweep, URL-addressable runs |
| Robustness | **missing** | no walk-forward, no OOS split — `/methodology` explicitly admits both are absent |
| Paper | **partial** | read-only 5-column table; `/paper/sessions/{id}`, `/run`, `/stop` unwired (`FE-10`) |
| ML Lab | **missing** | nothing in repo |
| AI Evals | **missing** | nothing in repo (`AI-12`) |
| Traces | **missing** | nothing in repo (`AI-11`) |
| Methodology | **complete** | genuinely good — but unreachable from the authed sidebar |
| Settings | **partial** | `/account` is password change + delete only, and is not in the nav |

**Six modes:** Explore *partial* · Build *partial and mislabeled* (JSON, not visual) ·
Research *missing* · Validate *partial* (backtests only, no robustness) · Paper *partial*
(read-only) · Lab *missing*.

Nav items outside the v2 target: Calculator, Alerts, Live Trading (a `href`-less "Gated" pill —
an honest label, worth keeping).

### 8.3 Blocking defects

`FE-01` (critical) — `infra/Dockerfile.web:8-13` runs `npm run build` with no `ARG`/`ENV` for
any `NEXT_PUBLIC_*`, and `.dockerignore` excludes `.env*`, while `infra/compose.prod.yaml:56-59`
supplies them as *runtime* env. Next inlines `NEXT_PUBLIC_*` at build time, so the shipped bundle
bakes in `use-market-socket.ts:18`'s fallback `ws://localhost:8080/market/ws`. Every browser on
an HTTPS page attempts a plaintext WS to the user's own machine, which fails and is
mixed-content-blocked, then retries forever with backoff. `NEXT_PUBLIC_SENTRY_DSN` has the same
defect. The Vercel path works only because Vercel injects env at build time.

`FE-02` (critical) — `calculator-view.tsx:217` renders `pct_of_equity` under the label
"Portfolio risk". The backend defines that field as `notional / equity` and comments it as such.
With the screen's own defaults (equity 100k, entry 100, stop 95, 1% risk) the tile reads
"Portfolio risk: 20.00%" while capital at risk is 1% — and the adjacent "Risk amount" row shows
the true figure, so the two tiles contradict each other on the same screen.

`FE-05` (high) — `isError` is never destructured in `markets-view`, `paper-view`, `alert-feed`
or `strategies-view`; a 401/500/network failure renders as "No markets available", "No paper
sessions yet", etc. There is no global 401 handler anywhere (`grep '401'` across `apps/web/src`
returns one hit, a 404 check). Because `proxy.ts` bounces `/login` → `/dashboard` on cookie
*presence*, a user with an expired cookie sees a fully-chromed app in which every screen claims
there is no data, with the Log out button as the only escape — which then hits `TRD-001`.

`FE-06` (high) — `localInput()` builds a `datetime-local` value from `toISOString()` (UTC) and
feeds it to an input the browser reads as *local*, then converts back with `toISOString()`,
applying the offset twice. At UTC+05:30 the default `end` is 5.5 hours in the future and the
last 5.5 hours of real bars are excluded from every default run. The helper's name asserts the
opposite of its behaviour.

### 8.4 Quality and accessibility

`FE-11` (medium) — the OHLC legend is `aria-hidden` and none of the four chart containers carry
`role="img"`, `aria-label`, `<figure>`, or a data-table alternative. `lightweight-charts` renders
to `<canvas>`, so for a screen-reader user the price chart, equity curve and drawdown chart —
the app's three core visualizations — convey nothing. The most recent commit claims an a11y
pass, so this is a visible gap in that work.

`FE-13` (medium) — the a11y commit fixed solid fills (adding `--primary-strong`,
`--loss-strong` with explicit 4.5:1 comments) but not opacity-scaled text: the 10px uppercase
section headers at `text-muted-foreground/60` measure ~3.0:1, the gated nav item at `/70` ~3.6:1,
and light-theme `text-primary` on the page background ~4.35:1 — marginally under AA, and it is
the styling of every inline action link.

`FE-12` (medium) — `lightweight-charts` is Apache-2.0 with an additional attribution
requirement. The in-canvas `attributionLogo` defaults to `true` and none of the three
`createChart` call sites disable it, so the **linking obligation is met** (`DEP` §1) — but there
is no visible "Charts by TradingView" notice and no third-party licenses page, and
`page.tsx:31`'s "TradingView-grade" phrasing implies an endorsement that does not exist.

`FE-09` (medium) — zero frontend tests. No `test` script, no vitest/jest/testing-library/
playwright, and CI runs only lint/typecheck/build. Nothing verifies the login redirect flow, the
CSRF header attachment, decimal-string rendering, the chart mount/unmount lifecycle, or the
empty-vs-error states above.

`FE-15` (low) — oscillator pane indices are recomputed on every toggle but existing series are
never moved between panes, so disabling one indicator leaves an empty pane; neither chart calls
`fitContent()` after `setData`.

`FE-16` (low) — the chart workspace is hardcoded to 1-minute bars over the backend's default
1-day window with no timeframe or range control, and feeds `SignalCard` a hardcoded SMA 10/30
spec whose `timeframe: "1h"` disagrees with the chart's 1m — so the card evaluates bars the user
is not looking at, and the user's own strategies cannot be evaluated on the chart at all.

`FE-21` (low) — `/markets` is split across two route groups, kept apart only by a hand-written
`pathname.startsWith("/markets/")` check in `proxy.ts` that no test covers.

### 8.5 What the frontend does well

`backtest-results.tsx` is the strongest screen: eight metrics plus fees paid, a cost disclosure
linking to `/methodology`, an equity curve, a client-derived underwater drawdown, paginated
trades, CSV export — and an `explain()` call that sends only four summary fields rather than the
trade list or equity curve. That minimal payload is the right call and should be preserved.
`mobile-nav.tsx` is a standout hand-rolled drawer (Escape handler, scroll lock, focus management
and restore, `motion-reduce:` variants, `role="dialog" aria-modal`). `lib/chart-theme.ts` and
`lib/chart-legend.ts` give one source of truth for chart colour and one shared OHLC legend
between the public and authed charts, so they cannot drift. `instrumentation.ts` and the Next 16
error boundaries use the correct current conventions.

---

## 9. Documentation state

### 9.1 Accurate and worth preserving

`/methodology`'s "what we deliberately don't claim" section is accurate against the code on
every item (no SIP feed, no survivorship-free fundamentals, no IS/OOS split, no deflated Sharpe,
no buy-and-hold overlay) and is the single strongest documentation asset in the project.
`docs/DEPLOY.md` is honest about Grafana having datasources but no dashboards, and about Grafana
being unreachable without a tunnel. ADR-0005 states outright that tenancy is `owner_id` scoping
with no billing/orgs/RBAC. The 8 ADRs are short, dated and decision-shaped.

### 9.2 Documentation that contradicts the code

| Claim | Location | Reality |
|---|---|---|
| `core/` includes an `events` module | `README.md:56` | no `events.py` anywhere (`DOC-01`) |
| "shadcn/ui … + Zustand" | `README.md:36` | no `components.json`, no `@radix-ui/*`, no `data-slot`; `components/ui/*` are 8 hand-written CVA components. `zustand` is absent from `package.json` and from every source file (`FE-08`, `DEP-14`) |
| "packages/contracts/ → generated TS client + zod" | `README.md:69` | that directory holds only `openapi.json`; the artifact is a types-only `schema.ts`; the client is hand-written; zod is not a dependency |
| `trading/` contains a "portfolio" | `README.md:62` | no portfolio component exists |
| "Live market data" | `README.md:7` | contradicted at `README.md:89` in the same file (`PC-10`) |
| Three numbered invariants | `README.md:74-77` | source comments cite an invariant #4 with no README entry and use #3 for a different rule; 20+ comments key off the numbering (`DOC-02`) |
| "Prometheus scrapes api:/metrics" | `docs/DEPLOY.md:77` | cannot happen as configured (`OBS-01`) |
| "Add the same token to `infra/prometheus.yml`" | `.env.example:56` | that file has no field for it |
| `cd "AI Powered Trading System"` | `docs/DEPLOY.md:55` | directory renamed in `05a3a77` (`DOC-03`) |
| "see the README frontmatter" | `Dockerfile:3-4` | frontmatter removed in `d1d8b1e` |
| Live trading gated by "2FA + step-up + kill-switch…" | `SECURITY.md:24-26` | none implemented; the gate's own docstring says deferred (`PC-14`) |
| ADR-0002: AI calls run off the request path | `docs/adr/0002:6` | they run inline, up to 180 s/360 s (`AI-16`) |
| ADR-0008: the AI consumes the generated schema artifact and uses tool-use | `docs/adr/0008:9` | it consumes a hand-written prose guide; no tool-use/function-calling anywhere (`AI-10`) |
| ADR-0001: the DAG is enforced in CI | `docs/adr/0001:11` | the gate exists but the contract fails (`ARCH-01`) |
| `apps/web/README.md` | whole file | untouched `create-next-app` boilerplate (`PC-24`, `FE-08`) |

### 9.3 Marketing copy vs. the product's own methodology page

This is the highest-signal documentation problem, because the contradictions are internal.

| Claim | Location | Contradicted by |
|---|---|---|
| "Sub-second" / "Live data" | `page.tsx:53` | 30 s cron; `refetchInterval: 30_000`; `DELAYED` badge; `/methodology:69` "polled on a ~30-second cadence" (`PC-01`) |
| "measured against buy & hold" | `opengraph-image.tsx:128-129` | `/methodology:97` lists a buy-and-hold overlay under *deliberately not claimed*; no benchmark exists in `metrics.py` (`PC-02`) |
| "models real commission, slippage, and **spread**" | `page.tsx:21` | `ExecutionConfig` has two friction fields; repo-wide, "spread" appears only in that sentence (`PC-05`) |
| "One canonical spec across AI, code, and **a visual builder**" | `page.tsx:36` | a JSON textarea (`PC-06`, `FE-03`) |
| "real-time data over WebSockets" | `page.tsx:30-31` | real-time *transport* of 30 s-polled closed bars — and non-functional in production per `FE-01` |
| "Delayed … with a **live** candlestick chart" | `markets/[ticker]/page.tsx:55` | `public-chart.tsx:35` "NO live WebSocket append" (`PC-18`) |
| "Institutional-grade analytics" | `brand.ts:5`, `page.tsx:102` | no benchmark, no attribution, no multiple-testing correction, and a wrong annualization constant (`PC-11`) |
| "Every AI response ends with a not-investment-advice note" | `/methodology:87`, `README.md:91`, `ai/router.py:5` | a prompt instruction with no server-side check or append; `/ai/strategy` returns JSON with no note (`PC-12`, `AI-09`) |
| "The one performance figure on our marketing pages" | `/methodology:62` | every public ticker page publishes five more (`PC-17`) |
| "AI Insights" / "summarize a market" | `dashboard-view.tsx:104-110` | two AI endpoints exist; neither summarizes a market; the card body is static prose (`PC-22`, `AI-17`) |

Positive note: a case-insensitive repo-wide grep for "open source" returns **zero** hits, so
nothing contradicts the proprietary `LICENSE`. The one tension is
`docs/DEPLOY_FREE_CLOUD.md:9-10`, which instructs publishing the tree to a public Space
(`PC-19`).

### 9.4 Missing documentation

No NOTICE / THIRD-PARTY-NOTICES file exists anywhere (`DEP-02`), while `deploy.yml` pushes
container images to GHCR — object-form redistribution of Apache-2.0 code with §4(d) attribution
duties and MPL-2.0 code with §3.2 source-availability duties. No privacy policy or terms page
exists under `apps/web/src` (`AI-08`). No data-source licensing posture is documented anywhere
(`MD-08`). `pyproject.toml` declares no license metadata, so a built wheel ships as unlicensed
despite the proprietary LICENSE (`DEP-15`).

---

## 10. Consolidated findings register

All non-refuted findings, every area. Severity as corrected by verification where verification
changed it. `Status` uses the raw finding's own taxonomy (`bug`, `insecure`, `misleading`,
`missing`, `partial`, `unused`, `stale`, `duplicated`, `complete`).

### 10.1 Architecture, CI, infrastructure

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| ARCH-01 | architecture | critical | bug | `pyproject.toml:119` | Import-linter layered contract broken at HEAD; six unsanctioned `market_data → backtesting/strategies` edges; CI gate red. |
| CI-01 | ci | high | bug | `apps/api/app/modules/market_data/public_router.py:87` | `ruff format --check` fails; five commits (from `55fe20d`) landed on `main` against a red required gate. |
| DB-01 | migrations | medium | stale | `apps/api/alembic/versions/0addaba53686_baseline_schema_auth_audit.py:40` | `CREATE EXTENSION vector` is unguarded, breaking the portability the same file claims; `vector`/`citext`/`pgcrypto` all unused. |
| TEST-01 | testing | medium | missing | `apps/api/tests/conftest.py:59` | Tests build schema via `create_all`; no `alembic check` in CI, so model/migration drift is unguarded. `_TABLES` omits `alerts`. |
| OBS-01 | infra | medium | misleading | `infra/prometheus.yml:5` | Prometheus cannot scrape `/metrics` — no credential in the scrape config and `METRICS_TOKEN` unset; every scrape 404s. |
| BACKUP-01 | infra | medium | partial | `infra/restore.sh:31` | TimescaleDB `pre_restore`/`post_restore` calls missing; the smoke check counts tables and would pass on an empty `ohlcv`. |
| WEB-01 | infra | medium | bug | `infra/compose.prod.yaml:58` | `NEXT_PUBLIC_*` passed at runtime but Next inlines at build time; VPS WebSocket URL falls back to localhost. |
| WEB-02 | web/config | medium | bug | `apps/web/src/lib/brand.ts:11` | `SITE_URL` defaults to a domain the project does not own; `NEXT_PUBLIC_SITE_URL` set nowhere. |
| PERF-01 | api | medium | bug | `apps/api/app/modules/market_data/reference_backtest.py:162` | Unauthenticated `/public/track-record` triggers a full engine run per instrument, backed by an unbounded in-process cache. |
| API-01 | api | medium | partial | `apps/api/app/modules/market_data/router.py:82` | Authed bars endpoint has no row or span cap while its public twin does. |
| API-02 | api | low | insecure | `apps/api/app/main.py:65` | `/docs` and `/openapi.json` unconditionally public in production and exempt from rate limiting. |
| MW-01 | api | low | partial | `apps/api/app/main.py:68` | `SecurityHeadersMiddleware` is innermost, so short-circuited 413/429/404 responses carry no security headers. |
| UOW-01 | api | low | partial | `apps/api/app/modules/trading/alerts.py:172` | A domain function commits the request-scoped session mid-request, breaking the unit-of-work boundary. |
| OPS-01 | ops | low | bug | `apps/api/app/ops_router.py:68` | `/internal/backfill` returns 422 to an unauthenticated probe, contradicting its documented 404-only behaviour. |
| CFG-01 | config | low | unused | `apps/api/app/core/config.py:30` | `app_secret_key`, `app_name`, `sync_database_url` are read by nothing; `.env.example` documents the first as securing CSRF. |
| DEAD-01 | code | low | unused | `apps/api/app/modules/trading/brokers/alpaca.py:14` | Five implemented components referenced by nothing: Alpaca adapter, `decrypt`, `get_owned`, `resume_start`, `bars_as_of`. |
| DUP-01 | code | low | duplicated | `apps/api/app/modules/strategies/spec.py:24` | The timeframe whitelist is defined in four places; adding one requires four coordinated edits. |
| GOOD-01 | architecture | info | complete | `apps/api/app/core/repository.py:37` | Tenancy seam, migration chain and contract drift guards are genuinely strong — preserve while refactoring. |

### 10.2 Market data

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| MD-01 | market data | high | bug | `apps/api/app/modules/market_data/repository.py:176` | `get_bars` returns a still-forming trailing bucket above 1m; the signal card's "latest closed bar" contract is false and repaints. |
| MD-03 | market data | high | bug | `apps/api/app/modules/market_data/streaming.py:27` | XNYS window hardcoded to EDT; the closing hour of every winter session is never polled, so bars are missing from the store. |
| MD-04 | market data | high | insecure | `apps/api/app/modules/market_data/reference_backtest.py:162` | Unauthenticated endpoints run full-year aggregations before the cache is consulted; the memo never shields the DB. |
| MD-05 | market data | high | insecure | `apps/api/app/core/ratelimit.py:42` | Leftmost `X-Forwarded-For` trusted with no allowlist; every middleware-enforced limit is bypassable per request. |
| MD-06 | market data | high | missing | `apps/api/app/modules/market_data/repository.py:63` | No data-quality validation at any layer; NaN/negative/`high<low` accepted and made permanently immutable. |
| MD-07 | market data | high | missing | `apps/api/app/modules/market_data/providers/yfinance_provider.py:48` | No split/dividend handling in either equity provider; unadjusted history is unrepairable by re-ingestion. |
| MD-08 | market data | high | missing | `apps/api/app/modules/market_data/public_router.py:135` | No data licensing or redistribution posture for Yahoo/Coinbase data republished on crawlable pages. |
| MD-02 | market data | medium | bug | `apps/api/app/modules/backtesting/engine.py:269` | `TimeOfDayFilter.timezone="exchange"` is accepted, validated, offered to the AI, and evaluated in UTC. |
| MD-09 | market data | medium | bug | `apps/api/app/modules/backtesting/service.py:21` | Data fingerprint hashes only count and endpoints, so interior bar revisions do not invalidate the cache. |
| MD-10 | market data | medium | bug | `apps/api/app/modules/market_data/reference_backtest.py:162` | `_CACHE` is unbounded and never evicted; entries accumulate for the process lifetime. |
| MD-11 | market data | medium | misleading | `apps/api/app/modules/market_data/repository.py:178` | UTC epoch origin means 4h/1d buckets ignore exchange sessions; the docstring conflates DB alignment with market alignment. |
| MD-12 | market data | medium | bug | `apps/api/app/modules/market_data/router.py:82` | Authed bars/indicator endpoints have no span cap and no DB-side row limit. |
| MD-13 | market data | medium | misleading | `apps/web/src/components/live-price.tsx:30` | `QuoteOut` has no timestamp, so "Last updated" renders React Query's fetch time, hiding stale bars. |
| MD-14 | market data | medium | misleading | `apps/api/app/modules/market_data/repository.py:141` | `limit` bounds the payload but not the scan; every `_MAX_SPAN` exceeds the row cap so max-span requests silently truncate. |
| MD-15 | market data | medium | bug | `apps/api/app/modules/market_data/streaming.py:56` | Provider construction sits outside the `try`, so one bad instrument aborts the whole poll cycle. |
| MD-16 | market data | medium | partial | `apps/api/app/modules/market_data/providers/yfinance_provider.py:48` | yfinance 1m fetch not chunked against Yahoo's ~7-day limit; CCXT pagination uncapped. |
| MD-17 | market data | medium | unused | `apps/api/app/modules/market_data/repository.py:96` | The forming→final lifecycle is dead code — nothing writes `is_final=false`; three docstrings describe a lifecycle that does not exist. |
| MD-18 | market data | medium | missing | `apps/api/alembic/versions/ee76d2a81338_market_data_instruments_sources_ohlcv_.py:88` | No retention or compression policy on the `ohlcv` hypertable, on free-tier Postgres targets. |
| MD-26 | market data | medium | missing | `apps/api/app/modules/market_data/ingestion.py:33` | No gap detection or gap fill; `resume_start` uses a max-ts watermark and is unreachable in production. |
| MD-19 | market data | low | unused | `apps/api/app/modules/market_data/repository.py:102` | `bars_as_of` is production-dead and its `limit` returns the oldest N, inconsistent with `get_bars`. |
| MD-20 | market data | low | unused | `apps/api/app/worker.py:27` | `ingest_backfill` is registered but never enqueued anywhere. |
| MD-21 | market data | low | unused | `apps/api/app/modules/market_data/models.py:78` | `OHLCV.source` is written and never read; incompatible feeds (Yahoo consolidated vs IEX) can interleave, first-writer-wins. |
| MD-22 | market data | low | misleading | `apps/api/app/modules/market_data/public_router.py:219` | Public bars silently truncate to 1500 rows with no `has_more` flag or cursor. |
| MD-23 | market data | low | bug | `apps/api/app/modules/market_data/public_router.py:122` | `_normalize_slug` breaks hyphenated equity tickers (`brk-b` → `BRK/B`); `resolve_symbol` ignores `asset_class`. |
| MD-24 | market data | low | misleading | `apps/web/src/app/markets/[ticker]/page.tsx:53` | SEO meta description calls delayed data a "live candlestick chart". |
| MD-25 | market data | low | stale | `apps/api/tests/conftest.py:57` | Stale Timescale comment, and the test schema bypasses Alembic so the hypertable path is never exercised. |

### 10.3 Backtesting and quantitative correctness

> Full evidence in [`QUANT_CORRECTNESS_AUDIT.md`](./QUANT_CORRECTNESS_AUDIT.md).

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| BT-01 | backtesting | high | bug | `apps/api/app/modules/backtesting/engine.py:240` | Trailing-stop exits fill at the bar's open instead of the trail, because the gap test runs after the ratchet. |
| BT-02 | backtesting | high | bug | `apps/api/app/modules/backtesting/engine.py:206` | ATR position sizing reads the fill bar's own high/low — intrabar look-ahead the canary cannot detect. |
| BT-03 | backtesting | high | misleading | `apps/api/app/modules/strategies/spec.py:167` | `entry_short` is validated, advertised to the AI and typed in the client schema, then silently never executed. |
| BT-04 | backtesting | high | bug | `apps/api/app/modules/backtesting/metrics.py:37` | Annualization is calendar-blind (365d/8760h regardless of instrument); authed equity backtests are inflated up to ~5x. |
| BT-05 | backtesting | high | misleading | `apps/api/app/modules/backtesting/metrics.py:47` | No minimum-sample guard; Sharpe/Sortino explode on tiny runs and render verbatim to authenticated users. |
| BT-06 | backtesting | medium | unused | `apps/api/app/modules/strategies/spec.py:146` | `max_open_positions` is validated, set by the UI, described to the AI, and never read by the engine. |
| BT-07 | backtesting | medium | misleading | `apps/api/app/modules/backtesting/engine.py:269` | `time_of_day.timezone` ignored; the window is always UTC. |
| BT-08 | backtesting | medium | bug | `apps/api/app/modules/backtesting/compute.py:44` | RSI is NaN, never 100, when there are no losses — so upside momentum entries silently never fire. |
| BT-09 | backtesting | medium | partial | `apps/api/app/modules/backtesting/compute.py:42` | Non-Wilder seeding for RSI/ATR/EMA; RSI(14) is ~8 points off TA-Lib for ~30 bars after warm-up. |
| BT-10 | backtesting | medium | bug | `apps/api/app/modules/backtesting/compute.py:84` | VWAP is cumulative from the first loaded bar, so results depend on the query start date. |
| BT-11 | backtesting | medium | bug | `apps/api/app/modules/backtesting/metrics.py:42` | Sortino uses stddev of negative returns about their own mean, not downside deviation; systematically inflated. |
| BT-12 | backtesting | medium | misleading | `apps/api/app/modules/backtesting/metrics.py:65` | `profit_factor` returns gross dollars when there are no losses — and is rendered on crawlable ticker pages. |
| BT-15 | backtesting | medium | misleading | `apps/api/app/modules/backtesting/service.py:38` | Multi-symbol `universe` silently backtests only `universe[0]`. |
| BT-16 | backtesting | medium | partial | `apps/api/app/modules/backtesting/snapshot.py:28` | `ExecutionConfig` is not recorded in the snapshot, so the UI's printed cost claim is not backed by the artifact. |
| BT-17 | backtesting | medium | partial | `apps/api/app/modules/backtesting/service.py:21` | Weak `data_fingerprint` misses mid-series bar revisions and keys the public reference cache. |
| BT-18 | backtesting | medium | misleading | `apps/api/app/modules/backtesting/engine.py:59` | ATR sizing hardcodes a 1% risk fraction; `risk_per_trade` without a stop silently degrades to percent-equity. |
| BT-22 | backtesting | medium | partial | `apps/api/tests/test_backtest.py:73` | The canary cannot detect intrabar look-ahead; no hand-calculated fixtures; `hypothesis` declared and unused. |
| BT-13 | backtesting | low | bug | `apps/api/app/modules/backtesting/engine.py:244` | Take-profit (a limit order) is charged adverse slippage, breaking parity with the signal card's advertised target. |
| BT-14 | backtesting | low | misleading | `apps/api/app/modules/backtesting/engine.py:247` | `time_exit_bars = N` actually holds N+1 bars. |
| BT-19 | backtesting | low | partial | `apps/api/app/modules/backtesting/engine.py:216` | Insufficient-cash clamp and zero-size drops emit no risk event; Decimal clamp can overspend by ~5e-22. |
| BT-20 | backtesting | low | stale | `apps/api/app/modules/backtesting/types.py:31` | `trailing` is a documented exit reason that is never emitted; the consecutive-loss halt never resets and is undocumented. |
| BT-21 | backtesting | low | partial | `apps/api/app/modules/strategies/spec.py:212` | `spec_hash` mixes cosmetic fields (`name`) into strategy identity and excludes engine/config. |
| BT-23 | backtesting | low | partial | `apps/api/app/modules/backtesting/engine.py:234` | Same-bar entry-and-exit yields zero-duration trades (undocumented, untested); `engine.run([])` raises `IndexError`. |
| BT-24 | backtesting | low | partial | `apps/api/app/modules/backtesting/snapshot.py:58` | Snapshot tail-truncates trades/equity while metrics cover the full run, with no truncation flag in the payload. |
| BT-25 | backtesting | low | missing | `apps/api/app/modules/backtesting/metrics.py:18` | No benchmark, exposure, turnover, Calmar or holding-period metrics; an always-invested strategy compares head-to-head with a 2%-exposure one. |

### 10.4 AI system

> Full evidence in [`AI_SYSTEM_AUDIT.md`](./AI_SYSTEM_AUDIT.md).

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| AI-03 | ai | high | bug | `apps/api/app/modules/ai/budget.py:30` | Token budget is advisory: check-then-call with no reservation, no per-request cap, no `/ai/*` rate limit; body cap bypassable via chunked encoding. |
| AI-11 | ai | high | missing | `apps/api/app/modules/ai/service.py:58` | No per-run record: no latency, cost, model, prompt version or audit entry — and provider failures are logged nowhere at all. |
| AI-12 | ai | high | missing | `apps/api/tests/test_ai.py:21` | No evaluation harness or dataset; providers, factory, `/ai/explain` and the global budget cap are entirely untested; the happy path is circular. |
| AI-01 | ai | medium | insecure | `apps/api/app/modules/ai/schemas.py:22` | `/ai/explain` narrates arbitrary client-supplied numbers; "grounded in your data" is unverifiable server-side. |
| AI-04 | ai | medium | bug | `apps/api/app/modules/ai/budget.py:38` | A zero/absent token usage report makes the call free and uncounted, with no log or metric. |
| AI-05 | ai | medium | partial | `apps/api/app/modules/ai/providers/factory.py:12` | No capabilities, health probe, retry, fallback chain or circuit breaker; a new `httpx.AsyncClient` per call, 3x per repair loop. |
| AI-06 | ai | medium | partial | `apps/api/app/modules/ai/providers/ollama.py:15` | Ollama model hardcoded and never passed by the factory; no `OLLAMA_MODEL` setting exists. |
| AI-07 | ai | medium | misleading | `Dockerfile:27` | Every shipped deployment pins the remote provider; the local option is unreachable inside containers. |
| AI-08 | ai | medium | missing | `apps/api/app/core/config.py:69` | Third-party AI egress is disclosed in operator docs but nowhere in-product; no privacy policy; free-tier retention caveat absent. |
| AI-09 | ai | medium | misleading | `apps/api/app/modules/ai/router.py:5` | "Every AI response ends with a not-investment-advice note" is unenforced and false for `/ai/strategy`. |
| AI-10 | ai | medium | duplicated | `apps/api/app/modules/ai/prompts.py:20` | No prompt versioning or registry; `DSL_GUIDE` hand-duplicates `spec.py` with no drift guard and omits every numeric constraint. |
| AI-13 | ai | medium | missing | `apps/api/app/modules/ai/providers/factory.py:12` | No fake/echo provider in app code, so CI and keyless dev cannot exercise the real factory path. |
| AI-14 | ai | medium | partial | `apps/api/app/modules/ai/service.py:54` | No semantic validation of the generated spec against user intent or platform reality (unknown symbols surface as a 404 much later). |
| AI-15 | ai | medium | bug | `apps/api/app/modules/ai/providers/ollama.py:33` | Provider transport and configuration errors surface as opaque 500s; `finishReason` never inspected; no `maxOutputTokens`. |
| AI-16 | ai | medium | bug | `apps/api/app/modules/ai/router.py:26` | Multi-minute synchronous AI call on the request path contradicts ADR-0002; no client `AbortController`. |
| AI-17 | ai | low | misleading | `apps/web/src/app/(app)/dashboard/dashboard-view.tsx:109` | Dashboard advertises a "summarize a market" capability that does not exist, plus an "assistant" with no chat UI. |
| AI-18 | ai | low | bug | `apps/api/app/core/config.py:69` | `ai_default_provider` is an untyped `str`; misconfiguration fails at first request rather than at boot. |
| AI-19 | ai | low | partial | `apps/api/app/modules/ai/service.py:23` | `_strip_fences` only handles a fence at exact string boundaries; leading prose costs a full repair round-trip. |
| AI-20 | ai | low | unused | `apps/api/app/modules/ai/providers/base.py:24` | `@runtime_checkable` on `LLMProvider` is dead decoration and would raise `TypeError` if used. |
| AI-21 | ai | info | stale | `.env:21` | Orphan `ANTHROPIC_API_KEY` in the untracked local `.env`, silently swallowed by `extra="ignore"`. |

### 10.5 Paper trading, live seam, application security

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| SEC-01 | security | high | insecure | `docs/DEPLOY_FREE_CLOUD.md:41` | A real 32-byte `BROKER_CRED_KEY` is published in a committed guide and recommended for a public Space; `/brokers/connections` is ungated. |
| SEC-02 | security | high | insecure | `apps/api/app/core/email.py:23` | No deploy target sets `FRONTEND_URL` or SMTP: reset is 100% broken in production and the live token is logged in full. |
| TRD-001 | security | high | bug | `apps/api/app/core/security.py:67` | Logout does not clear the production cookie (`__Host-` rejects a `Set-Cookie` without `Secure`), creating a logout redirect trap. |
| TRD-002 | security | high | insecure | `apps/api/app/core/ratelimit.py:42` | Rate limiting bypassable with a spoofed `X-Forwarded-For`; no trusted-proxy config anywhere in app, uvicorn or Caddy. |
| TRD-003 | security | high | bug | `apps/api/app/modules/auth/router.py:38` | Login and password-reset limits bucket the whole platform under the proxy IP; one visitor can lock out all logins. |
| TRD-005 | security | high | missing | `apps/api/app/modules/auth/service.py:66` | Password change and reset revoke no sessions; no per-user session index; a stolen cookie survives a reset up to 14 days. |
| SEC-03 | security | medium | bug | `apps/api/app/core/ratelimit.py:42` | Split-brain client-IP resolution: middleware trusts a spoofable header, login uses the raw peer address. |
| SEC-04 | security | medium | partial | `apps/api/app/modules/auth/deps.py:44` | CSRF double-submit enforced on 3 of 21 unsafe endpoints (13 cookie-authed mutations unprotected). |
| TRD-004 | security | medium | partial | `apps/api/app/modules/auth/deps.py:44` | Same as SEC-04 from the security side; exploitability narrowed by JSON-body requirements and `SameSite=lax`. |
| TRD-007 | trading | medium | insecure | `apps/api/app/modules/trading/broker_schemas.py:14` | `env="live"` broker credentials accepted and stored with no gate, no audit, no delete endpoint, and no UI consumer. |
| TRD-008 | security | medium | partial | `apps/api/app/core/crypto.py:19` | Credential ciphertext carries no key id or version, so rotating `BROKER_CRED_KEY` silently bricks every stored credential. |
| TRD-009 | security | medium | insecure | `apps/api/app/core/errors.py:83` | `AppError`-class 500s return their internal detail to the client and are never logged — both halves backwards. |
| TRD-010 | security | medium | bug | `apps/api/app/ops_router.py:32` | `compare_digest` on attacker-controlled non-ASCII `str` raises `TypeError` → a 500-vs-404 configuration oracle. |
| TRD-011 | security | medium | partial | `apps/api/app/core/security.py:121` | Body-size limit inspects only `Content-Length`, so chunked transfer encoding bypasses it entirely. |
| TRD-012 | security | medium | insecure | `apps/api/app/core/email.py:23` | Reset links and every recipient address are written to logs; `TICK_SECRET` travels as a query parameter into access logs. |
| TRD-013 | trading | medium | bug | `apps/api/app/modules/trading/repository.py:44` | Soft-deleted accounts keep running paper sessions and keep receiving alert emails. |
| TRD-014 | trading | medium | bug | `apps/api/app/modules/trading/alerts.py:174` | Blocking per-message SMTP inside the request handler and inside the sequential cross-owner cron loop. |
| TRD-015 | trading | medium | bug | `apps/api/app/ops_router.py:50` | No lock or single-flight around paper-session advancement; concurrent runs 500 on the alert unique constraint. |
| TRD-016 | security | medium | partial | `apps/api/app/modules/auth/router.py:49` | `/auth/register` has no rate limit and returns a 409 enumeration oracle; select-then-insert TOCTOU yields a 500. |
| TRD-017 | api | medium | partial | `apps/api/app/modules/market_data/reference_backtest.py:193` | Heaviest anonymous endpoints fall outside the dedicated rate bucket and do uncached full-history reads per request. |
| TRD-019 | web/security | medium | partial | `apps/web/next.config.ts:14` | CSP permits `script-src 'unsafe-inline'` (no nonce) and `connect-src` to any `ws:`/`wss:` host — an exfiltration channel. |
| TRD-020 | security | medium | misleading | `apps/api/app/core/config.py:30` | `app_secret_key` is dead config documented as securing CSRF tokens and auto-generated as a required secret. |
| TRD-022 | trading | medium | partial | `apps/api/app/modules/trading/service.py:54` | Paper sessions start with zero indicator warm-up and silently no-op while the UI shows them as freshly run. |
| TRD-025 | testing | medium | missing | `apps/api/tests/test_paper.py:1` | No test for the alert idempotency invariant, password reset, or the live gate with the flag enabled. |
| TRD-026 | trading | medium | misleading | `apps/api/app/modules/trading/calc.py:34` | The calculator silently substitutes a different sizing method and reports zero risk for a real position. |
| TRD-018 | api | low | bug | `apps/api/app/modules/market_data/reference_backtest.py:162` | Reference-backtest cache is an unbounded process-lifetime dict. |
| TRD-021 | trading | low | unused | `apps/api/app/modules/trading/brokers/alpaca.py:14` | `AlpacaBrokerAdapter` and the `BrokerAdapter` protocol are entirely unused, with a hard `alpaca-py` dependency and no conformance test. |
| TRD-023 | trading | low | bug | `apps/api/app/core/db.py:47` | `Alert.created_at` is a naive timestamp, so the feed renders it in the viewer's local time. |
| TRD-024 | security | low | partial | `apps/api/app/main.py:71` | Security headers applied innermost; `/docs` unconditionally public in production. |
| TRD-027 | trading | low | partial | `apps/api/app/modules/trading/alerts.py:172` | `dispatch_snapshot_alerts` commits the caller's request-scoped session mid-request. |

### 10.6 Frontend

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| FE-01 | frontend | critical | bug | `infra/Dockerfile.web:13` | `NEXT_PUBLIC_*` never reach the production bundle; the live WebSocket is hardcoded to `ws://localhost:8080`. |
| FE-02 | frontend | critical | misleading | `apps/web/src/app/(app)/calculator/calculator-view.tsx:217` | The calculator labels notional exposure as "Portfolio risk" (20.00% where risk is 1%). |
| FE-03 | frontend | high | misleading | `apps/web/src/app/page.tsx:36` | Landing advertises a visual strategy builder that does not exist. |
| FE-04 | frontend | high | misleading | `apps/web/src/app/page.tsx:21` | Landing + OG card make four data/engine claims the product's own methodology page disclaims. |
| FE-05 | frontend | high | misleading | `apps/web/src/app/(app)/markets/markets-view.tsx:18` | Every API error renders as a benign "nothing here yet" empty state; no 401 handling anywhere. |
| FE-06 | frontend | high | bug | `apps/web/src/app/(app)/backtests/backtests-view.tsx:12` | Backtest default date range is shifted by the UTC offset; the default end date is in the future. |
| FE-07 | frontend | high | bug | `apps/web/src/app/(app)/dashboard/dashboard-view.tsx:36` | "Portfolio Value" does client-side float math on Decimal strings and mixes post-run equity with pre-run cash. |
| FE-08 | docs | medium | stale | `README.md:36` | Frontend stack claim is false: Zustand absent, `components/ui/*` is not shadcn; `apps/web/README.md` is scaffold boilerplate. |
| FE-09 | testing | medium | missing | `apps/web/package.json:5` | Zero frontend tests; CI runs only lint, typecheck, build. |
| FE-10 | frontend | medium | partial | `apps/web/src/app/(app)/paper/paper-view.tsx:55` | Paper sessions and strategy versions are read-only in the UI although the backend exposes full controls. |
| FE-11 | frontend | medium | insecure | `apps/web/src/components/chart-workspace.tsx:256` | Charts have no text alternative — the legend is `aria-hidden` and canvases carry no role or label. |
| FE-12 | licensing | medium | missing | `apps/web/package.json:14` | No visible TradingView attribution or third-party licenses page (the in-canvas logo default does satisfy the link requirement). |
| FE-13 | frontend | medium | partial | `apps/web/src/components/app-nav.tsx:50` | Residual WCAG AA contrast failures on opacity-scaled muted text and light-theme inline links. |
| FE-14 | frontend | medium | stale | `apps/web/src/lib/brand.ts:11` | Every deployed page emits the placeholder origin in canonicals, sitemap, robots and JSON-LD. |
| FE-15 | frontend | low | bug | `apps/web/src/components/chart-workspace.tsx:198` | Oscillator pane indices drift when indicators are toggled off; charts never `fitContent()`. |
| FE-16 | frontend | low | partial | `apps/web/src/components/chart-workspace.tsx:25` | Chart workspace locked to 1m/1d with a hardcoded 1h reference spec, so the signal card evaluates unseen bars. |
| FE-17 | frontend | low | stale | `apps/web/src/app/markets/[ticker]/page.tsx:19` | `generateStaticParams` is inert — `cache: "no-store"` forces dynamic rendering with two upstream calls per crawl. |
| FE-18 | frontend | low | partial | `apps/web/src/components/alert-feed.tsx:47` | "Alerts" is a read-only feed with no rules, acknowledgement or configuration; `<time>` lacks `dateTime`. |
| FE-19 | frontend | low | duplicated | `apps/web/src/lib/api/client.ts:114` | Dead `api.csrf`, unreachable `assetClass` filter, unused scaffold SVGs, and triplicated auth-form markup. |
| FE-20 | frontend | low | missing | `apps/web/src/app:1` | No `not-found.tsx`, no `loading.tsx`, no skip link; `/account` unreachable from the nav; `robots.ts` disallow list incomplete. |
| FE-21 | frontend | low | partial | `apps/web/src/proxy.ts:35` | `/markets` is split across two route groups, kept apart only by an untested `startsWith` check. |

### 10.7 Product positioning and public claims

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| PC-01 | claims | critical | misleading | `apps/web/src/app/page.tsx:53` | Stat tile claims "Sub-second / Live data" while the platform polls every 30 s and labels everything DELAYED. |
| PC-02 | claims | critical | misleading | `apps/web/src/app/opengraph-image.tsx:128` | The OG social card claims results are "measured against buy & hold" — a benchmark `/methodology` says is not built. |
| PC-03 | claims | high | bug | `apps/api/app/modules/backtesting/metrics.py:65` | Public `profit_factor` returns gross dollar P&L, not a ratio, when a run has no losing trades. |
| PC-04 | claims | high | bug | `apps/api/app/modules/backtesting/metrics.py:37` | Sharpe/Sortino/CAGR annualized with 24/7 periods-per-year even for equities, beneath an "auditable" footnote. |
| PC-05 | claims | high | misleading | `apps/web/src/app/page.tsx:21` | Landing claims the engine models "spread"; no spread modeling exists anywhere. |
| PC-06 | claims | high | misleading | `apps/web/src/app/page.tsx:36` | Landing advertises "a visual builder"; the UI is a raw JSON textarea. |
| PC-07 | claims | high | misleading | `apps/api/app/modules/market_data/seed.py:21` | The public track record aggregates a hand-picked 5-symbol survivor universe without disclosing the selection. |
| PC-08 | claims | high | bug | `apps/api/app/modules/strategies/spec.py:167` | `entry_short` accepted by the spec and advertised to the copilot, then silently ignored by the engine. |
| PC-09 | claims | high | bug | `apps/web/src/lib/brand.ts:11` | `NEXT_PUBLIC_SITE_URL` never configured, so canonicals, OG urls, JSON-LD, robots host and the sitemap emit a placeholder domain. |
| PC-10 | claims | high | misleading | `README.md:7` | README opens with "Live market data" and "production-grade, SaaS-ready", contradicted 80 lines later in the same file. |
| PC-11 | claims | medium | misleading | `apps/web/src/lib/brand.ts:5` | "Institutional-grade analytics" claimed in the hero and the shared brand description. |
| PC-12 | claims | medium | misleading | `apps/web/src/app/methodology/page.tsx:87` | "Every AI response ends with a not-investment-advice note" is a prompt instruction asserted as a guarantee. |
| PC-13 | claims | medium | insecure | `apps/api/app/modules/ai/schemas.py:21` | `/ai/explain` narrates arbitrary client-supplied numbers, so "grounded in your data" is unenforced. |
| PC-14 | claims | medium | misleading | `SECURITY.md:24` | SECURITY.md describes live-trading controls (2FA, opt-in, step-up, kill-switch) that are not implemented. |
| PC-15 | claims | medium | misleading | `apps/api/app/modules/market_data/reference_backtest.py:352` | Track-record averages include zero-trade runs as 0% return and 0% win rate. |
| PC-16 | claims | medium | misleading | `apps/web/src/app/(app)/dashboard/dashboard-view.tsx:55` | Dashboard shows a dollar "Portfolio Value" from paper equity with no PAPER/SIMULATED provenance badge. |
| PC-17 | claims | medium | misleading | `apps/web/src/app/methodology/page.tsx:62` | "The one performance figure on our marketing pages" — every public ticker page publishes five more. |
| PC-18 | claims | medium | misleading | `apps/web/src/app/markets/[ticker]/page.tsx:55` | Meta description calls the chart "live" in the same sentence that calls the price delayed. |
| PC-19 | claims | medium | misleading | `docs/DEPLOY_FREE_CLOUD.md:9` | The free-tier guide instructs publishing source to a public HF Space, conflicting with the proprietary LICENSE. |
| PC-20 | claims | medium | bug | `apps/api/app/modules/market_data/streaming.py:27` | The equity poll window is a fixed UTC range, so the 30 s cadence claim is wrong for an hour of every EST session. |
| PC-21 | claims | low | misleading | `apps/web/src/components/live-price.tsx:30` | The LivePrice tooltip hard-codes "Polled every 30s", contradicting the documented free-tier ~5-minute cadence. |
| PC-22 | claims | low | misleading | `apps/web/src/app/(app)/dashboard/dashboard-view.tsx:104` | The "AI Insights" card contains no AI output. |
| PC-23 | claims | low | unused | `apps/web/src/components/data-badge.tsx:3` | `DataBadge` LIVE / EOD / SIMULATED / PAPER variants are defined but never used. |
| PC-24 | claims | low | stale | `apps/web/README.md:1` | `apps/web/README.md` is untouched create-next-app boilerplate. |
| PC-25 | claims | low | stale | `apps/api/app/main.py:62` | FastAPI app title is the generic "Trading Platform API", inconsistent with the product brand. |
| PC-26 | claims | low | bug | `apps/web/src/app/manifest.ts:10` | PWA `start_url` points at an auth-gated route, so a fresh install opens on a redirect. |
| PC-27 | claims | info | missing | `README.md:23` | The README screenshot could not be inspected in this environment — content unverified. |
| PC-28 | claims | info | complete | `apps/api/app/modules/backtesting/engine.py:186` | Preserve: look-ahead-free engine, public metric stripping, universal hypothetical banners, auth-gated signal cards. |

### 10.8 Dependencies and licensing

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| DEP-01 | licensing | high | insecure | `apps/api/app/modules/market_data/providers/yfinance_provider.py:46` | yfinance uses `curl_cffi` Chrome TLS impersonation to evade Yahoo bot detection; derived data is served on public crawlable pages. |
| DEP-02 | licensing | high | missing | `LICENSE:1` | No NOTICE / THIRD-PARTY-NOTICES anywhere; Apache-2.0 §4(d) and MPL-2.0 §3.2 duties unmet for images pushed to GHCR. |
| DEP-03 | dependencies | high | bug | `apps/api/app/modules/backtesting/compute.py:14` | `pandas` and `numpy` are imported by the engine but are not declared dependencies — only transitively reachable via two optional vendors. |
| DEP-07 | supply chain | high | stale | `.github/dependabot.yml:6` | Dependabot's `pip` ecosystem cannot maintain `uv.lock`, and every constraint is an open lower bound — no Python update can ever be produced. |
| DEP-04 | dependencies | medium | unused | `pyproject.toml:23` | `orjson` is declared, never imported, and is the only MPL-2.0 package in the production runtime. |
| DEP-05 | dependencies | medium | unused | `pyproject.toml:21` | `python-multipart` is declared but the API has no form or file-upload endpoint. |
| DEP-06 | testing | medium | unused | `pyproject.toml:41` | `hypothesis` is a declared dev dependency with zero property-based tests. |
| DEP-08 | licensing | medium | insecure | `infra/Dockerfile.web:18` | LGPL-3.0 libvips binaries ship in the web image via an unused image optimizer; LICENSE's anti-reverse-engineering clause conflicts with LGPL-3 §4. |
| DEP-09 | licensing | medium | insecure | `apps/web/next.config.ts:40` | `@sentry/cli` (FSL-1.1-MIT, non-OSI) installs as a production dependency although `withSentryConfig` is never applied. |
| DEP-10 | licensing | medium | insecure | `infra/compose.prod.yaml:8` | TimescaleDB (TSL), Redis 7.4+ (RSALv2/SSPL) and three AGPL Grafana images behind floating tags, undocumented anywhere. |
| DEP-11 | supply chain | medium | insecure | `.github/workflows/ci.yml:96` | The gitleaks binary is installed with no checksum, and a mutable-tag third-party action receives the deploy SSH key. |
| DEP-12 | supply chain | medium | misleading | `.github/workflows/ci.yml:60` | Both vulnerability audits are `continue-on-error`, and `pip-audit` itself is unpinned. |
| DEP-13 | tooling | medium | bug | `.pre-commit-config.yaml:1` | `pre-commit` is the documented entry point but is not a declared dependency, is not installed, and its hooks never run in CI. |
| DEP-14 | docs | medium | misleading | `README.md:36` | The stack section claims two frontend dependencies (Zustand, shadcn/ui) that do not exist. |
| DEP-20 | data | medium | missing | `apps/api/app/modules/market_data/seed.py:22` | No bundled deterministic dataset; every real-data option is encumbered, so synthetic generation is the only redistribution-safe path. |
| DEP-15 | licensing | low | missing | `pyproject.toml:1` | No license metadata in `pyproject.toml`, so a built wheel ships as unlicensed despite the proprietary LICENSE. |
| DEP-16 | tooling | low | stale | `.pre-commit-config.yaml:4` | Pre-commit hook revisions pinned to ~2024 releases with no update mechanism. |
| DEP-17 | web | low | unused | `apps/web/public/vercel.svg:1` | Five unused Next scaffold SVGs, including Vercel's trademarked logo, ship in the production image. |
| DEP-18 | dependencies | low | stale | `pyproject.toml:16` | The `redis<6` cap cites an `arq` constraint that may no longer hold for the locked `arq` version. |
| DEP-19 | licensing | low | misleading | `apps/api/app/modules/ai/providers/ollama.py:15` | The default local LLM is Llama 3.1, whose community licence is not OSI-approved and carries AUP and naming terms. |
| DEP-21 | privacy | low | insecure | `.env.example:68` | Free-tier Gemini is the default provider; user strategy text leaves the trust boundary under terms permitting provider-side retention. |

### 10.9 Documentation

| Id | Area | Sev | Status | file:line | Summary |
|---|---|---|---|---|---|
| DOC-01 | docs | medium | misleading | `README.md:56` | README describes three architectural components that do not exist: a `core/events` module, Zustand/shadcn, and a generated TS client + zod. |
| DOC-02 | docs | low | stale | `README.md:74` | README lists three invariants; source comments cite a fourth and number #3 differently, and 20+ comments key off that numbering. |
| DOC-03 | docs | low | stale | `Dockerfile:3` | Stale references in the root Dockerfile (removed README frontmatter) and `docs/DEPLOY.md:55` (a directory name retired in `05a3a77`). |

### 10.10 Register totals

| Severity | Count |
|---|---|
| critical | 5 |
| high | 39 |
| medium | 92 |
| low | 52 |
| info | 4 |
| **Total** | **192** |

Two findings raised during the audit were **refuted** by verification and are excluded
entirely: a claim that untrusted `/ai/explain` context lacked prompt-injection delimiting as a
standalone defect (the injection channel is retained inside `AI-01`), and a claim that
paper-trading produced unretractable phantom fill alerts (the narrower, verified version is
`MD-01`).

---

## Baseline Verification (see BASELINE_VERIFICATION.md)

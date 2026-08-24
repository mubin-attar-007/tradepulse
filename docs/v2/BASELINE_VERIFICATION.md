# Baseline Verification — TradePulse (pre-v2)

**Purpose.** Record what the repository actually does *before* any v2 change, so every later
claim of improvement has a measured starting point. Every row below was executed on this
machine. Commands that were **not** run are marked `NOT RUN` with the reason — nothing is
recorded as passing that was skipped, and no test was modified to make it pass.

| Field | Value |
|---|---|
| Commit | `8b8236858c854021b206739636f59667a5e8e1a1` (`8b82368`, branch `main`, clean tree) |
| Date of run | 2026-08-24 (UTC) |
| OS | Windows 10 Pro 19045 (win32) |
| Python | 3.12.13 (`uv` 0.11.6) |
| Node / npm | v24.14.1 / 11.11.0 |
| Docker | Engine 29.3.1, Compose v5.1.1 |
| Hardware | 6 logical CPUs, 15.9 GiB RAM, GeForce GT 710 (2 GiB — not usable for local LLM inference) |
| Ollama | **not installed** |
| `just` | 1.51.0 |

---

## 1. Summary

| Result | Count | Items |
|---|---|---|
| ✅ Passed | 16 | dependency install (both stacks), ruff check, mypy, migrations, pytest (78), OpenAPI drift, TS types drift, frontend lint/typecheck/build, seed, backfill (crypto + equity), worker startup + crons, API health/ready, backtest E2E, paper deploy, live-gate refusal, prod API image, prod web image |
| ❌ Failed | 4 | `ruff format --check`, `lint-imports`, `docker compose up --wait` (pinned DB image), AI copilot smoke (`/ai/strategy` → 500) |
| ⚠️ Passed with concerns | 3 | `npm audit` (11 vulns), coverage 68 % with 0 % on worker/brokers, paper session produced no snapshot |
| ⏭️ NOT RUN | 5 | gitleaks secret scan, `infra/backup.sh`, `infra/restore.sh`, load/performance tests, full `just bootstrap` |

Four failures are real repository defects (three) plus one environment/key issue that is
*caused by* a repository design choice (remote-AI-by-default). They are detailed in §4.

---

## 2. Command-by-command record

### 2.1 Dependency installation

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 1 | `uv sync --frozen` | yes | ✅ pass | `Checked 104 packages in 65ms` — lockfile resolves, no drift against `uv.lock`. |
| 2 | `npm ci` (in `apps/web`) | yes | ⚠️ pass w/ concerns | `added 497 packages … in 3m`. Reported **11 vulnerabilities (4 moderate, 7 high)**. CI treats `npm audit` as `continue-on-error`, so this never blocks a merge. |

### 2.2 Backend static gates

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 3 | `uv run ruff check apps/api` | yes | ✅ pass | `All checks passed!` |
| 4 | `uv run ruff format --check apps/api` | yes | ❌ **FAIL** | `2 files would be reformatted`: `apps/api/app/modules/market_data/public_router.py`, `apps/api/app/modules/market_data/reference_backtest.py`. CI runs this gate → **CI is red on `main`.** |
| 5 | `uv run mypy apps/api/app` | yes | ✅ pass | `Success: no issues found in 101 source files` (26.5 s). Strict-ish config (`disallow_untyped_defs`). Genuinely good. |
| 6 | `uv run lint-imports` | yes | ❌ **FAIL** | 6 contract violations — see §4.2. CI runs this gate → **second reason `main` is red.** |

### 2.3 Infrastructure

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 7 | `docker compose up -d --wait` | yes | ❌ **FAIL** | `container tradepulse-db-1 exited (1)`. Root cause in §4.1 — the pinned image is broken upstream. |
| 8 | `docker compose … up -d --wait` with DB image overridden to `timescale/timescaledb:2.18.2-pg16` | yes | ✅ pass | Both containers healthy in 7.9 s. Used as the substrate for every later step; the override lives in a scratch file, **not** in the repo. |
| 9 | `docker build -f infra/Dockerfile.api -t tradepulse-api:baseline .` | yes | ✅ pass | Exit 0. |
| 10 | `docker build -f infra/Dockerfile.web -t tradepulse-web:baseline apps/web` | yes | ✅ pass | Exit 0. |
| 11 | `just bootstrap` | **NOT RUN** | — | It chains `just up`, which fails at step 7. Its sub-steps (`uv sync`, `migrate`, `seed`, `backfill`) were each run individually instead. |

### 2.4 Database & migrations

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 12 | `uv run alembic upgrade head` | yes | ✅ pass | 6 migrations applied cleanly in 3.5 s: `0addaba53686 → ee76d2a81338 → b13d9815e40d → 91d0566854c9 → 8d734251ff4e → a3f7c2e91b44`. |
| 13 | `uv run alembic heads` | yes | ✅ pass | `a3f7c2e91b44 (head)` — **single linear head**, no branching. |

### 2.5 Tests

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 14 | `uv run pytest --cov=app --cov-report=term-missing` | yes | ✅ pass | **78 passed in 59.66 s**, `TOTAL … 68 %` line coverage (3460 statements, 940 missed, branch coverage on). |

Coverage concentrations worth recording (from the same run):

| Module | Coverage | Comment |
|---|---|---|
| `app/worker.py` | **0 %** | The entire background-job entrypoint is untested. |
| `app/modules/trading/brokers/*` | **0 %** | `base.py`, `alpaca.py` — the broker adapter layer is dead code at runtime (see §3.4). |
| `app/modules/market_data/seed.py` | **0 %** | |
| `app/ops_router.py` | 25 % | The `/internal/tick` + `/internal/backfill` surface. |
| `app/modules/market_data/router.py` | 27 % | |
| `app/modules/trading/calc.py` | 31 % | |
| `app/modules/market_data/public_router.py` | 37 % | Unauthenticated public surface. |
| `app/modules/backtesting/compute.py` | 40 % | Indicator math — the correctness-critical module. |
| `app/modules/backtesting/engine.py` | 72 % | |
| `app/modules/backtesting/metrics.py` | 91 % | |

There are **no** property-based tests despite `hypothesis` being a declared dev dependency,
and no frontend test runner is installed at all (`apps/web/package.json` has no vitest/jest/playwright).

### 2.6 Contracts

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 15 | `uv run python -m app.cli.export_openapi` | yes | ✅ pass | Wrote `packages/contracts/openapi.json`. |
| 16 | `git diff --exit-code packages/contracts/openapi.json` | yes | ✅ pass | **No drift** — the committed spec matches the code. |
| 17 | `npm run gen:api` + `git diff --exit-code src/lib/api/schema.ts` | yes | ✅ pass | **No drift** — generated TS types match the spec. This guard genuinely works. |

### 2.7 Frontend

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 18 | `npm run lint` | yes | ✅ pass | ESLint clean, no output. |
| 19 | `npm run typecheck` | yes | ✅ pass | `tsc --noEmit` clean. |
| 20 | `npm run build` | yes | ✅ pass | 52 s. Compiled in 26 s, 22 static pages generated. Route table: 22 routes (`/`, `/methodology`, `/login`, `/markets/[ticker]` SSG, and the `(app)` dynamic routes). |
| 21 | Frontend unit/e2e tests | **NOT RUN** | — | **None exist.** No test script, no runner in `package.json`. |

### 2.8 Application smoke runs

All against the API started with `uv run uvicorn app.main:app --app-dir apps/api --port 8080`
on the compose stack from step 8.

| # | Check | Ran | Result | Evidence |
|---|---|---|---|---|
| 22 | `GET /health` | yes | ✅ | `{"status":"ok","env":"local"}` |
| 23 | `GET /ready` | yes | ✅ | `{"status":"ready","checks":{"db":true,"redis":true}}` |
| 24 | `GET /metrics` without token | yes | ✅ | `404` — fail-closed gate works as documented. |
| 25 | `python -m app.cli.seed` | yes | ✅ | `Seeded 5 instruments.` (AAPL, MSFT, SPY, BTC/USD, ETH/USD) |
| 26 | `python -m app.cli.backfill "BTC/USD" --days 1` | yes | ✅ | **1439 real bars** via Coinbase (CCXT, no API key) in 18.5 s, `2026-08-23 09:16 → 2026-08-24 09:14 UTC`. |
| 27 | `python -m app.cli.backfill SPY --days 3` | yes | ✅ | **390 real bars** via yfinance in 13.8 s — one RTH session only (`2026-08-21 13:30 → 19:59 UTC`); the two prior calendar days returned nothing (weekend). |
| 28 | `POST /auth/register` → `GET /auth/me` | yes | ✅ | Session cookie issued; `/auth/me` returns the user. |
| 29 | Backtest E2E (1 h, BTC/USD, 25 bars) | yes | ✅ | `status=done`, 0 trades (no crossover in the window), `spec_hash=3b53441701…`, `engine_version=0.1.0`, `data_fingerprint=aaa636902a…`. |
| 30 | Backtest E2E (1 m, BTC/USD, 1437 bars) | yes | ✅ | **36 trades**, final equity `98938.35…`, commission `717.67…`, `win_rate 0.361`, `profit_factor 0.587`, `max_drawdown -0.0166`, response in **0.12 s**. Costs are genuinely applied and the result is honestly negative. |
| 31 | `POST /paper/deploy` | yes | ⚠️ | `201`, session `running`. But after two worker cron passes the session still had `snapshot: null` — see §4.4. |
| 32 | `GET /alerts` | yes | ✅ | `[]` (consistent — no fills yet). |
| 33 | `GET /live/preflight` | yes | ✅ | `allowed:false`, reasons `live_feature_disabled, user_not_opted_in, 2fa_not_enabled, no_recent_2fa_step_up, missing_confirmation`. |
| 34 | `POST /live/orders` | yes | ✅ | **403** with the blocking reasons. No real-money path is reachable. This control works and must be preserved. |
| 35 | `GET /public/markets/btc-usd` | yes | ✅ | Returns instrument, latest delayed price, SMA/EMA/RSI arrays, and `reference_backtest.available:false` with an honest `note` when history is short. |
| 36 | `GET /public/track-record` | yes | ✅ | `available:false` + explanatory `note` + `data_note` naming the data as DELAYED polled bars. Degrades honestly. |
| 37 | `arq app.worker.WorkerSettings` (75 s) | yes | ✅ | Worker started `4 functions`; both crons executed: `cron:run_paper_sessions ● 1` and `cron:poll_quotes ● 2` (published 2 instruments). Note `poll_quotes` took **10.6 s and 6.9 s** against a 30 s schedule. |
| 38 | AI copilot `POST /ai/strategy` | yes | ❌ **FAIL** | `500` — `"Gemini request failed (400)."` Root cause in §4.3. |

### 2.9 Security & operations

| # | Command | Ran | Result | Notes |
|---|---|---|---|---|
| 39 | `gitleaks detect` | **NOT RUN** | — | `gitleaks` is not installed on this machine. It is configured in `.pre-commit-config.yaml` and installed on the fly in CI. Substituted: `git ls-files` confirms only `.env.example` and `infra/.env.prod.example` are tracked — **no real `.env` or `infra/.env.prod` is in version control**, and `.gitignore` covers `.env`/`.env.*` with explicit `!*.example` negations. |
| 40 | `pip-audit` | **NOT RUN** locally | — | CI runs it as `continue-on-error` (informational only). |
| 41 | `infra/backup.sh` | **NOT RUN** | — | Requires `restic`, a configured repository, `infra/.env.prod`, and the prod compose stack. None exist here. |
| 42 | `infra/restore.sh` | **NOT RUN** | — | Same prerequisites. The script is well-written (restores into a throwaway DB, counts tables, cleans up) but has **never been executed in this environment**, so "restore-verified" is unproven. |
| 43 | Load / performance tests | **NOT RUN** | — | **None exist in the repository.** No k6/locust/artillery config, no benchmark suite. Any latency or throughput claim is therefore unmeasured. |
| 44 | CSRF enforcement probe | yes | ❌ finding | `POST /strategies` with only the session cookie and **no `x-csrf-token` header** returned **201**. See §4.5. |

---

## 3. What the baseline proves *works*

Recorded so future changes do not regress it:

1. **The event-driven backtest engine runs end to end on real market data** and is fast
   (1437 bars, 36 trades, 0.12 s). Commission and slippage are applied by default and the
   reported result was negative — the pipeline does not flatter itself.
2. **Look-ahead discipline holds under test.** `test_lookahead_canary` perturbs all bars after
   index 35 by 3× and asserts the equity curve through bar 35 is unchanged; it passes.
3. **Money stays `Decimal` end to end** and crosses the API as strings (`final_equity`,
   `total_commission`, `qty`, `entry_price` are all quoted strings in the JSON responses above).
4. **Tenancy is enforced at the repository layer**, including against a caller that pre-sets a
   spoofed `owner_id` (`test_add_overrides_caller_supplied_owner`).
5. **The live-trading gate is genuinely closed** (step 34) and cannot be opened by configuration
   alone — `LIVE_TRADING_ENABLED=true` would still leave four other blockers.
6. **Contract generation is drift-free in both directions** (steps 16–17) — this is a real,
   working guard that most projects claim and few have.
7. **`/metrics` fails closed** without a token (step 24).
8. **Migrations are linear and apply cleanly** from scratch (steps 12–13).
9. **mypy passes on 101 files** with `disallow_untyped_defs`.
10. **Both production container images build.**

## 4. Failures — root causes

### 4.1 `compose.yaml` pins a TimescaleDB image that cannot start (blocks the documented quick start)

`compose.yaml:6` pins `timescale/timescaledb:2.17.2-pg16`. The container exits 1 with:

```
FATAL: could not load library "/usr/local/lib/postgresql/timescaledb.so":
       Error loading shared library …: Exec format error
```

Verified this is **upstream image corruption, not a local cache problem**: after
`docker rmi` + a fresh `docker pull --platform linux/amd64` (digest
`sha256:4e459e21…`), the library is still a **0-byte file**:

```
-rwxr-xr-x 1 root root       0 Jan 22  2025 /usr/local/lib/postgresql/timescaledb-2.17.2.so
-rwxr-xr-x 1 root root       0 Jan 22  2025 /usr/local/lib/postgresql/timescaledb.so
```

Neighbouring tags are intact — `2.17.1-pg16` (238 KB), `2.18.2-pg16` (243 KB),
`2.19.3-pg17` (273 KB), `latest-pg16` (259 KB) — so only this exact tag is broken.

**Blast radius:** `just up`, `just bootstrap`, and `.github/workflows/ci.yml` (whose `services.db`
pins the identical tag) all fail. A new contributor cannot start the project by following the README.

### 4.2 `lint-imports` fails — the layering contract is violated on `main`

```
app.modules.market_data is not allowed to import app.modules.strategies:
  - app.modules.market_data.router -> app.modules.strategies.spec (l.31)
  - app.modules.market_data.signal -> app.modules.strategies.spec (l.37)
app.modules.market_data is not allowed to import app.modules.backtesting:
  - app.modules.market_data.signal -> app.modules.backtesting.compute (l.33)
  - app.modules.market_data.signal -> app.modules.backtesting.engine (l.33)
  - app.modules.market_data.router -> app.modules.backtesting.compute (l.20)
  - app.modules.market_data.signal -> app.modules.backtesting.types (l.34)
```

`pyproject.toml` carries an `ignore_imports` allowlist for exactly five
`market_data.reference_backtest → …` edges, added when that file was introduced. The later
`signal.py` and `market_data/router.py` upward edges were never added to it, so the contract
now genuinely fails. This is an architecture regression that CI would have caught had CI been green.

### 4.3 The AI copilot is dead at baseline

`POST /ai/strategy` → `500 {"detail":"Gemini request failed (400)."}`.

Direct probe of the configured key against `generativelanguage.googleapis.com/v1beta/models`:

```json
{"code":400,"message":"API key not valid. Please pass a valid API key.",
 "status":"INVALID_ARGUMENT","reason":"API_KEY_INVALID"}
```

Three distinct repository-level problems are exposed by this one failure:

1. **Remote-by-default.** `AI_DEFAULT_PROVIDER=gemini` (`core/config.py:70`) means the entire AI
   feature depends on a third-party account and network egress. Contrary to a "free, local-first"
   posture, the *default* path sends the user's research prompts to Google.
2. **No fallback, no classification.** A permanent `API_KEY_INVALID` is indistinguishable from a
   transient failure in this code: `providers/gemini.py:41` raises a bare
   `AppError(f"Gemini request failed ({resp.status_code}).")` for every non-200 except 429. There
   is no circuit breaker, no provider health, and no automatic fallback to the local Ollama provider.
3. **A permanent upstream 4xx is surfaced as a 500.** `AppError` defaults to `status_code = 500`
   (`core/errors.py:550`), so a misconfiguration is reported to the client as a server fault, and
   the actual upstream message (`API key not valid`) is discarded before it reaches any log the
   operator would read.

Local alternative unavailable too: `ollama` is not installed here, and `providers/factory.py:14`
constructs `OllamaProvider(settings.ollama_base_url)` **without passing a model**, so it would
silently use the hardcoded default `llama3.1` (`providers/ollama.py:14`) regardless of what the
operator has actually pulled.

### 4.4 A fresh paper session shows nothing

After `POST /paper/deploy` and two full worker cron passes, `GET /paper/sessions` returned
`snapshot: null` with `last_run_at` set. Cause: `PaperService.run_session` replays the strategy
only over `[session_start, now]` (`modules/trading/service.py:78-80`) and returns early when
`len(bars) < 2` (`:81`). For a `1h` strategy that means the desk stays empty for at least two
hours after deployment, with no UI signal explaining why.

### 4.5 CSRF double-submit is set up but never validated

`core/security.py` defines `CSRF_COOKIE`, `CSRF_HEADER`, `SAFE_METHODS` and sets a readable
`csrf_token` cookie — the standard double-submit setup. Empirically, a state-changing
`POST /strategies` carrying **only** the session cookie succeeded with `201` (step 44).
`grep` finds no code that compares the header to the cookie. The residual protection is
`SameSite=Lax` on the session cookie, which does block cross-site form POSTs — so this is not an
open CSRF hole today, but the token machinery is inert and gives false assurance, and any future
move to `SameSite=None` (or a cross-site embed) would silently remove the only real defence.

---

## 5. Environment caveats affecting later work

- **No local LLM runtime.** Ollama is absent and the GPU (GT 710, 2 GiB) cannot serve models. The
  v2 "local-first" path must therefore be verified with a deterministic in-process provider plus a
  stubbed HTTP server, with real-model runs documented as operator-run rather than claimed here.
- **A native PostgreSQL 17.9 is also running on `localhost:5432`** (service `postgresql-x64-17`).
  It offers `pgvector 0.8.1` as an available extension but **not** `timescaledb`. Useful as a
  fallback substrate and relevant to the v2 retrieval design.
- **Docker Desktop's service (`com.docker.service`) cannot be started from this shell** (requires
  elevation); the daemon was started via the Docker Desktop UI process instead.

---

## 6. Reproducing this baseline

```bash
git checkout 8b82368
uv sync --frozen
docker compose up -d --wait                 # ← fails; see §4.1
# workaround used here:
docker compose -f compose.yaml -f <override-with-2.18.2-pg16> up -d --wait
uv run alembic upgrade head
uv run pytest --cov=app --cov-report=term-missing
uv run ruff check apps/api && uv run ruff format --check apps/api   # ← format fails
uv run mypy apps/api/app && uv run lint-imports                     # ← lint-imports fails
uv run python -m app.cli.export_openapi && git diff --exit-code packages/contracts/openapi.json
cd apps/web && npm ci && npm run lint && npm run typecheck && npm run build
```

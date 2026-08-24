# TradePulse — Dependency & License Audit (pre-v2)

**Date:** 2026-08-21
**Baseline commit:** `8b82368` (`main`) — the same commit measured in
[`BASELINE_VERIFICATION.md`](./BASELINE_VERIFICATION.md) and audited in
[`CURRENT_STATE_AUDIT.md`](./CURRENT_STATE_AUDIT.md).
**Scope:** third-party code entering the product — Python backend, Next.js frontend,
container base images, and the CI supply chain — plus the licence clearance list for v2.

## How to read this document

- Every `path:line` reference is against **commit `8b82368`** unless explicitly marked
  otherwise. An uncommitted working tree containing v2 remediation exists on this machine;
  where it changes a finding's status that is called out inline and never used as the baseline.
- Every licence attributed to an **installed Python package** was read from the on-disk
  `.venv/Lib/site-packages/*.dist-info/METADATA` in this checkout, not from recall. npm
  licences come from the `license` field npm recorded in `apps/web/package-lock.json`.
  Where recall is the only source — upstream relicensing trends, image licences that are
  not files in this repo — it is flagged as such and marked **unverified offline**.
- Findings carry stable ids (`DEP-nn`). Claims that verification refuted are absent from
  this document entirely; claims that verification corrected appear only in corrected form.
- "Used?" means *reachable from application code at this commit*, established by
  repo-wide `grep` excluding `node_modules/`, `.venv/`, `.next/` and the lockfiles.

---

## 1. Scope & method

### 1.1 Sources read

| Source | What it establishes |
|---|---|
| `pyproject.toml:7-29` | Declared Python runtime dependencies (21 specs) |
| `pyproject.toml:31-42` | Declared Python dev group (9 specs) |
| `uv.lock` | Resolved backend graph: 105 `name =` entries, one of which is the root project `trading-platform` (`uv.lock`, `source = { editable = "." }`) → **104 third-party packages** |
| `.venv/Lib/site-packages/*.dist-info/METADATA` | Authoritative, offline licence text for every installed backend package |
| `apps/web/package.json:13-24, 25-35` | Declared frontend deps (10) and dev deps (9) |
| `apps/web/package-lock.json` | Resolved frontend graph: 601 `packages` entries, one being the root workspace `""` (`web@0.1.0`) → **600 third-party packages**, all 600 carrying a `license` field |
| `apps/web/.next/standalone/` | What the shipped web image actually contains |
| `LICENSE`, `README.md` | The proprietary grant and its stated obligations |
| `compose.yaml`, `infra/compose.prod.yaml`, `Dockerfile`, `infra/Dockerfile.api`, `infra/Dockerfile.web` | Container base images and what is copied into runtime layers |
| `.github/dependabot.yml`, `.github/workflows/ci.yml`, `.github/workflows/deploy.yml`, `.pre-commit-config.yaml` | Update policy and supply-chain posture |

### 1.2 What was and was not executed

Read-only inspection only: `git show`/`git ls-files` against `8b82368`, `grep`, `find`, and
two short Python scripts that parse `package-lock.json` and the installed `METADATA`
headers. **No** package manager, resolver, build, container, or network call was run for
this document. In particular `pip-audit`, `npm audit`, `uv lock --upgrade`, and every
`docker build` were **not run here**; where their results matter they are the lead's to
record in `BASELINE_VERIFICATION.md`, not this document's to assert.

### 1.3 Knowledge-cutoff caveat

The lock resolves several packages released after this model's May 2026 training cutoff
(`pandas 3.0.3`, `numpy 2.4.6`, `mypy 2.1.0`, `pytest 9.0.3`, `starlette 1.2.1`,
`next 16.2.7`, `react 19.2.7`, plus `librt 0.11.0`, `ast_serialize 0.5.0`,
`annotated_doc 0.0.4`). This is precisely why every installed-package licence below is
read from disk. It also means statements about *upstream licence policy* — Redis's
relicensing, Grafana's current major, the exact name of Dependabot's uv ecosystem — carry
an explicit **unverified offline** marker.

### 1.4 Headline result

The permissive-licence posture is **clean and should be preserved**. Zero GPL, LGPL, or
AGPL packages exist in the backend graph (a regex scan of every installed `METADATA`
header for `GPL|GNU General|GNU Lesser|Affero` returned no matches). The frontend graph
is 470 MIT / 44 Apache-2.0 / 20 ISC / 13 BSD-2 / 5 BSD-3 among direct-and-transitive
production and dev packages. Nothing in the first-party dependency set threatens the
proprietary `LICENSE`.

Four things do need attention, none of them a licence *incompatibility*:

1. No attribution artefact of any kind exists, while CI pushes container images to a
   registry (§6, `DEP-02`).
2. LGPL-3.0 binaries reach the shipped web image through a feature the app never uses
   (§6, `DEP-08`).
3. Three declared dependencies are not used, and two used ones are not declared (§5).
4. The single largest legal exposure is not a licence at all — it is the **market-data
   acquisition path** (§8, `DEP-01`), which also dictates the v2 fixture design (§10).

### 1.5 What is genuinely good — preserve

| Strength | Evidence |
|---|---|
| Both lockfiles committed and enforced everywhere | `uv.lock` and `apps/web/package-lock.json` are tracked; every build path uses the frozen resolution — `.github/workflows/ci.yml:41` (`uv sync --frozen`), `infra/Dockerfile.api:8` and `Dockerfile:13` (`uv sync --frozen --no-dev`), `infra/Dockerfile.web:5` (`npm ci`) |
| Zero copyleft in the backend | Scan of all installed `METADATA` headers: no GPL/LGPL/AGPL match |
| The TradingView attribution requirement is actually met | §6.1 |
| Optional paid services fail closed, never degrade silently | §7 |
| Dependabot's *intent* is right — monthly, grouped, minor/patch only, majors ignored | `.github/dependabot.yml:1-3` states the policy explicitly; the Python half does not function (`DEP-07`) |
| No secrets in the dependency surface | `.gitignore` covers `.env*`; gitleaks runs in CI over full history (`ci.yml:96-101`) — though see the integrity gap in §11 |

---

## 2. Backend direct dependencies

Licences are the installed `License-Expression:` where present, otherwise the legacy
`License:` field or the trove classifier, all read from `.venv/Lib/site-packages/*.dist-info/METADATA`.

### 2.1 Runtime (`pyproject.toml:7-29`)

| Package (declared spec) | Locked | Licence (from METADATA) | Used? | Purpose | Obligations / risk |
|---|---|---|---|---|---|
| `fastapi>=0.115` | 0.136.3 | MIT | yes — `apps/api/app/main.py:12` | HTTP framework | Notice retention only |
| `uvicorn[standard]>=0.30` | 0.48.0 | BSD-3-Clause | yes, as CLI — `infra/Dockerfile.api:24`, `render.yaml:17`, `justfile:34` | ASGI server | Notice retention only |
| `pydantic>=2.7` | 2.13.4 | MIT | yes — schemas throughout | Validation | None material |
| `pydantic-settings>=2.3` | 2.14.1 | MIT | yes — `apps/api/app/core/config.py:12` | Env config | None material |
| `email-validator>=2.1` | 2.3.0 | **Unlicense** (public domain) | yes, via `EmailStr` — `apps/api/app/modules/auth/schemas.py:8` | Email syntax/deliverability check | None (public domain) |
| `sqlalchemy[asyncio]>=2.0.30` | 2.0.50 | MIT | yes — `apps/api/app/core/db.py:15-22` | ORM / async engine | None material |
| `asyncpg>=0.29` | 0.31.0 | **Apache-2.0** | yes — DSN driver, `apps/api/app/core/db.py:69-77` | Postgres driver | Apache §4(d) NOTICE on redistribution |
| `alembic>=1.13` | 1.18.4 | MIT | yes — `apps/api/alembic/env.py:19` | Migrations | None material |
| `redis>=5.0,<6` | 5.3.1 | MIT | yes — `apps/api/app/core/redis.py:9-10` | Sessions, rate limit, pub/sub, budgets | Cap may be stale (`DEP-18`) |
| `arq>=0.26` | 0.28.0 | MIT | yes — `apps/api/app/worker.py:12-13` | Task queue + crons | Source of the `redis<6` cap |
| `structlog>=24.1` | 25.5.0 | MIT OR Apache-2.0 | yes — `apps/api/app/core/logging.py:13` | Structured logging | Dual-licensed; take MIT |
| `argon2-cffi>=23.1` | 25.1.0 | MIT (bundles the Argon2 reference implementation, CC0/Apache-2.0) | yes — `apps/api/app/core/security.py:12-13` | Password hashing (argon2id) | Bundled C sources add an Apache/CC0 notice entry |
| `pynacl>=1.5` | 1.6.2 | **Apache-2.0** (bundles libsodium, ISC) | yes — `apps/api/app/core/crypto.py:13` | Broker-credential SecretBox | Apache §4(d) + libsodium ISC notice |
| `python-multipart>=0.0.9` | 0.0.30 | **Apache-2.0** | **NO** — `DEP-05` | (form/file parsing) | Unused attack surface + a needless notice entry |
| `httpx>=0.27` | 0.28.1 | BSD-3-Clause | yes — `apps/api/app/modules/ai/providers/ollama.py:7`, `.../gemini.py` | Async HTTP to AI providers | Notice retention only |
| `orjson>=3.10` | 3.11.9 | **MPL-2.0 AND (Apache-2.0 OR MIT)** | **NO** — `DEP-04` | (fast JSON) | Sole MPL-2.0 source in the backend image, for zero benefit |
| `sentry-sdk[fastapi]>=2.7` | 2.61.1 | MIT | yes — `apps/api/app/core/observability.py:18-25` | Error tracking | SaaS optional and DSN-gated (§7) |
| `ccxt>=4.5.56` | 4.5.56 | MIT | yes — `apps/api/app/modules/market_data/providers/ccxt_provider.py:14,55` | Crypto OHLCV | Library MIT; **exchange ToS governs the data** (§8) |
| `yfinance>=1.4.1` | 1.4.1 | Apache-2.0 (`License: Apache` in METADATA) | yes — `.../providers/yfinance_provider.py:46,48` | Equity OHLCV (primary) | Library Apache; **Yahoo ToU governs the data — highest-risk item in the tree, `DEP-01`** |
| `alpaca-py>=0.43.4` | 0.43.4 | Apache-2.0 | yes — `.../providers/alpaca_provider.py:43-50`, `apps/api/app/modules/trading/brokers/alpaca.py` | Equity OHLCV (keyed) + broker seam | Apache §4(d); **market-data agreement governs redistribution** |
| `prometheus-fastapi-instrumentator>=8.0.0` | 8.0.0 | ISC | yes — `apps/api/app/main.py:86-88` | `/metrics` exposition | Notice retention only |
| **`pandas` — undeclared** | 3.0.3 | BSD-3-Clause | **imported directly** — `apps/api/app/modules/backtesting/compute.py:15` | Bar frames in the backtest engine | **Undeclared dependency, `DEP-03`** |
| **`numpy` — undeclared** | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | **imported directly** — `compute.py:14`, `apps/api/app/modules/backtesting/metrics.py:11`, `apps/api/app/modules/market_data/router.py:11` | Vectorised metrics/indicators | **Undeclared dependency, `DEP-03`** |

### 2.2 Dev group (`pyproject.toml:31-42`)

| Package | Locked | Licence | Used? |
|---|---|---|---|
| `pytest>=8.2` | 9.0.3 | MIT | yes |
| `pytest-asyncio>=0.23` | 1.4.0 | **Apache-2.0** | yes (`asyncio_mode = "auto"`, `pyproject.toml:95`) |
| `pytest-cov>=5.0` | 7.1.0 | MIT | yes |
| `anyio>=4.4` | 4.13.0 | MIT | yes |
| `asgi-lifespan>=2.1` | 2.1.0 | MIT | yes (`apps/api/tests/conftest.py`) |
| `ruff>=0.5` | 0.15.15 | MIT | yes (`ci.yml:44-45`) |
| `mypy>=1.10` | 2.1.0 | MIT | yes (`ci.yml`) |
| `import-linter>=2.0` | 2.11 | BSD-2-Clause | yes (`ci.yml:49`) |
| `hypothesis>=6.100` | 6.155.1 | **MPL-2.0** | **no at `8b82368`** — `DEP-06` |

**Absent from the dev group entirely:** `pre-commit` (`DEP-13`) and `pip-audit` (`DEP-12`).
Neither appears in `uv.lock` (`grep -c 'name = "pre-commit"' uv.lock` → 0; same for
`pip-audit`), so `uv run pre-commit install` — the literal instruction at
`.pre-commit-config.yaml:1` — cannot succeed on a clean checkout, and the auditing tool in
`ci.yml:61` floats unpinned via `uv run --with pip-audit`.

---

## 3. Frontend direct dependencies

### 3.1 Production (`apps/web/package.json:13-24`)

| Package | Locked | Licence | Used? (files under `apps/web/src`) | Purpose | Obligations / risk |
|---|---|---|---|---|---|
| `next` | 16.2.7 | MIT | yes | App Router framework | Pulls `sharp` (`DEP-08`) and `caniuse-lite` (CC-BY-4.0) |
| `react` / `react-dom` | 19.2.7 | MIT | yes | UI runtime | None material |
| `lightweight-charts` | 5.2.0 | **Apache-2.0 + attribution clause** | yes — 5 files | Charting | Attribution link required; **satisfied**, §6.1 |
| `@sentry/nextjs` | 10.57.0 | MIT | yes — 4 files | Error tracking | Drags in `@sentry/cli` (FSL-1.1-MIT), `DEP-09` |
| `@tanstack/react-query` | 5.101.0 | MIT | yes — 13 files | Server-state cache | None material |
| `class-variance-authority` | 0.7.1 | **Apache-2.0** | yes — 4 files | Variant styling primitive | Apache §4(d) notice |
| `clsx` | 2.1.1 | MIT | yes — 1 file | Class merging | None material |
| `lucide-react` | 1.17.0 | ISC | yes — 19 files | Icons | Notice retention only |
| `tailwind-merge` | 3.6.0 | MIT | yes — 1 file | Tailwind class dedupe | None material |

**All ten production dependencies are genuinely imported.** There are no dead frontend
dependencies — a notably better result than the backend (§5).

### 3.2 Dev (`apps/web/package.json:25-35`)

`tailwindcss` 4.3.0 MIT · `@tailwindcss/postcss` MIT · `typescript` 5.9.3 **Apache-2.0** ·
`eslint` 9.39.4 MIT · `eslint-config-next` 16.2.7 MIT · `openapi-typescript` 7.13.0 MIT ·
`@types/*` MIT.

### 3.3 Aggregate licence distribution (`package-lock.json`, all 600 third-party entries)

| Licence | Count | Note |
|---|---|---|
| MIT | 470 | |
| Apache-2.0 | 44 | |
| ISC | 20 | |
| MPL-2.0 | 13 | `lightningcss` ×11 (dev), `axe-core` (dev), one more |
| BSD-2-Clause | 13 | |
| **LGPL-3.0-or-later** | 10 | `@img/sharp-libvips-*@1.2.4`, all `dev=false, optional=true` — `DEP-08` |
| **FSL-1.1-MIT** | 9 | `@sentry/cli@2.58.6` + 8 platform binaries, `dev=false` — `DEP-09` |
| BlueOak-1.0.0 | 6 | |
| BSD-3-Clause | 5 | |
| Apache-2.0 AND LGPL-3.0-or-later | 3 | `@img/sharp-win32-*@0.34.5` |
| (MIT OR CC0-1.0) | 2 | |
| Apache-2.0 AND LGPL-3.0-or-later AND MIT | 1 | `@img/sharp-wasm32@0.34.5` |
| Python-2.0 | 1 | `argparse@2.0.1` (dev) |
| CC-BY-4.0 | 1 | `caniuse-lite@1.0.30001793` (`dev=false`) |
| CC0-1.0 | 1 | |
| 0BSD | 1 | `tslib@2.8.1` |

The lock enumerates every platform's optional binaries; only a subset installs on any one
OS, so an installed-package count on a given machine will be lower than 600. That is
expected and is not drift.

---

## 4. Transitive notables

These are the transitive packages that change the obligation picture, as opposed to merely
appearing in the graph.

### 4.1 Backend

| Package | Locked | Licence (METADATA) | Why it matters |
|---|---|---|---|
| `certifi` | 2026.5.20 | **MPL-2.0** | Ships in both images; MPL §3.2 source-availability applies to the covered files (unmodified, so a pointer suffices) |
| `curl_cffi` | 0.15.0 | MIT | yfinance's HTTP layer. Licence is fine; **its behaviour is the problem** — see `DEP-01` |
| `cryptography` | 48.0.0 | Apache-2.0 OR BSD-3-Clause | Wheels statically link OpenSSL; the OpenSSL notice travels with the wheel |
| `coincurve` | 21.0.0 | MIT OR Apache-2.0 | Bundles libsecp256k1 (MIT) |
| `pathspec` | 1.1.1 | **MPL-2.0** (trove classifier; no `License`/`License-Expression` field) | Dev-only, via mypy — does not ship |
| `peewee` | 4.0.6 | **no licence field and no licence classifier in METADATA** | Only unlicensed-in-metadata package in the graph. Upstream is understood to be MIT (**unverified offline**). Pulled transitively; confirm before it lands in a notices file |
| `typing_extensions` | 4.15.0 | PSF-2.0 | Ubiquitous; PSF is permissive |
| `greenlet` | 3.5.1 | MIT AND PSF-2.0 | SQLAlchemy asyncio bridge |
| `aiohttp` | 3.14.0 | Apache-2.0 AND MIT | via ccxt |
| `requests` | 2.34.2 | Apache-2.0 | Apache §4(d) notice entry |
| `msgpack` | 1.1.2 | Apache-2.0 | via arq |
| `starlette` | 1.2.1 | BSD-3-Clause | FastAPI's substrate |

### 4.2 Frontend

- **`@sentry/cli@2.58.6` + 8 platform binaries — FSL-1.1-MIT, `dev=false`.** The Functional
  Source License is source-available, *not* OSI open source, and carries a non-compete
  restriction (it converts to MIT on a delay). This is the only non-OSI licence in the npm
  tree. Arrives via `@sentry/nextjs` → `@sentry/webpack-plugin` →
  `@sentry/bundler-plugin-core` → `@sentry/cli`. See `DEP-09` — nothing uses it.
- **`sharp@0.34.5` (Apache-2.0) + `@img/sharp-libvips-*@1.2.4` (LGPL-3.0-or-later),
  `dev=false, optional=true`.** Not theoretical: `apps/web/.next/standalone/node_modules/sharp`
  and `apps/web/.next/standalone/node_modules/@img/` both exist in this checkout's build
  output (`@img/colour`, `@img/sharp-win32-x64` on this machine; a Linux build carries
  `@img/sharp-libvips-linux-x64`), and `infra/Dockerfile.web:18` copies `.next/standalone`
  wholesale into the runtime image. See `DEP-08`.
- **`caniuse-lite@1.0.30001793` — CC-BY-4.0, `dev=false`.** Browser-support data consumed at
  build time by the Next/PostCSS toolchain. Attribution is nominally required for the data;
  practically de minimis since the dataset is not emitted into `.next/standalone` output.
- **`lightningcss` (×11, MPL-2.0) and `axe-core` (MPL-2.0)** — dev-only, do not ship.
- **`argparse@2.0.1` — Python-2.0**, dev-only.

### 4.3 Container base images

| Image | Where | Licence | Note |
|---|---|---|---|
| `timescale/timescaledb:2.17.2-pg16` | `compose.yaml:5`, `infra/compose.prod.yaml:8`, `ci.yml` services | **Timescale License (TSL)** — non-OSI, no-DBaaS restriction (**unverified offline**) | Exposure is low: TSL restricts offering *the database* as a service, which TradePulse does not do. Should still be a documented decision |
| `redis:7-alpine` | `compose.yaml:22`, `infra/compose.prod.yaml:23` | Floating tag. Redis 7.4+ upstream is **RSALv2/SSPLv1**, non-OSI (**unverified offline — recall only**) | A floating tag means the licence can change under the deployment without a commit. Pin it |
| `grafana/grafana:latest`, `grafana/loki:latest`, `grafana/promtail:latest` | `infra/compose.prod.yaml:103,83,92` | **AGPL-3.0** in current majors (**unverified offline**) | Behind the opt-in `observability` profile, no published ports, no Caddy route — so not distributed and not network-served to third parties. Pin and document |
| `prom/prometheus:latest` | `infra/compose.prod.yaml:74` | Apache-2.0 | Pin by digest |
| `caddy:2` | `infra/compose.prod.yaml:62` | Apache-2.0 | |
| `python:3.12-slim` | `infra/Dockerfile.api:2,10`, `Dockerfile:7,15` | Composite (PSF + Debian) | Unpinned by digest |
| `node:22-slim` | `infra/Dockerfile.web:2,7,14` | Composite (MIT + Debian) | Unpinned by digest |
| `ghcr.io/astral-sh/uv` | build stage | Apache-2.0 OR MIT | |

`DEP-10`: none of the non-OSI or copyleft image licences is recorded in `LICENSE`,
`README.md`, `SECURITY.md`, or `docs/`.

---

## 5. Unused dependencies

Three declared packages are never used; two used packages are never declared. Each is a
one-line fix and each removes either legal surface or a correctness hazard.

| id | Package | Declared at | Locked | Licence | Evidence of non-use | Why it matters |
|---|---|---|---|---|---|---|
| `DEP-04` | `orjson` | `pyproject.toml:23` | 3.11.9 | **MPL-2.0 AND (Apache-2.0 OR MIT)** | Repo-wide `grep -rn "orjson\|ORJSONResponse"` across `*.py`/`*.toml`/`*.ts`/`*.tsx` matches exactly one line: `pyproject.toml:23` itself. FastAPI is constructed with the default `JSONResponse` | An unused package is the **sole** MPL-2.0 source in the production backend image |
| `DEP-05` | `python-multipart` | `pyproject.toml:21` | 0.0.30 | Apache-2.0 | `grep -rnE "multipart\|UploadFile\|Form\(\|File\(" apps/api --include="*.py"` → **zero matches**. Auth uses JSON bodies and cookie sessions. Starlette only requires it when a route declares form data | A multipart parser you never invoke is pure attack surface plus one more Apache notice entry |
| `DEP-06` | `hypothesis` | `pyproject.toml:41` | 6.155.1 | **MPL-2.0** | At `8b82368`, `grep -rniE "hypothesis\|@given" apps/api` → zero matches. `.gitignore` already ignores `.hypothesis/`, so the intent existed and was never executed | Only MPL-2.0 dev package, unused. **Status changes in the working tree:** the uncommitted `apps/api/tests/quant/` (untracked — `git ls-files apps/api/tests/quant` is empty) adds real property tests using `from hypothesis import given, settings` (`test_properties.py:13-14`, `test_differential.py:22-23`). If that work lands, `DEP-06` closes by use rather than removal, which is the better outcome |
| `DEP-03` | `pandas`, `numpy` | **nowhere** | 3.0.3 / 2.4.6 | BSD-3-Clause / BSD-3 AND 0BSD AND MIT AND Zlib AND CC0-1.0 | Imported at `apps/api/app/modules/backtesting/compute.py:14-15`, `.../backtesting/metrics.py:11`, `.../market_data/router.py:11`; absent from `pyproject.toml:7-29`. `uv.lock` reaches `pandas` only via `alpaca-py`/`yfinance` and `numpy` only via `pandas`/`yfinance`. `pyproject.toml:89` even adds a mypy override for `pandas.*`, acknowledging the import while leaving the dependency undeclared | **The backtest engine — the core of the product — depends on a transitive edge owned by two optional market-data vendors.** Dropping or swapping `yfinance`/`alpaca-py` breaks the engine at import time. Declaring them also puts two BSD-3 packages on the attribution manifest where they belong |

Related dead weight outside the dependency graph proper:

- `DEP-17` — five Next.js scaffold SVGs ship in the production image. `apps/web/public/`
  contains `file.svg`, `globe.svg`, `next.svg`, `vercel.svg`, `window.svg`; `grep` for any
  of those filenames across `apps/web/src` returns **no matches**, and
  `infra/Dockerfile.web:20` copies `public/` wholesale into the runtime image. Trademark is
  not covered by any licence in this tree, so serving Vercel's mark from a commercial
  product's own origin has no upside. Delete all five.
- `DEP-09` — `@sentry/cli` (FSL-1.1-MIT, `dev=false`) is installed but inert:
  `grep -rn "withSentryConfig"` over `apps/web/next.config.ts` and `apps/web/src` returns
  nothing, so no source maps are uploaded and no release is injected. Only the runtime SDK
  is wired (`apps/web/src/instrumentation.ts:7`). The one non-OSI licence in the npm tree
  currently buys nothing.
- `DEP-08` (second half) — `sharp` exists only as Next's optional image-optimizer backend;
  `next/image` is imported nowhere in `apps/web/src` (the only `_next/image` occurrence is
  a matcher exclusion at `apps/web/src/proxy.ts:67`).

---

## 6. Attribution obligations, and whether they are satisfied

`LICENSE:1` is an all-rights-reserved proprietary grant. Every licence in the tree —
MIT, BSD-2/3, ISC, Apache-2.0, Unlicense, PSF-2.0, 0BSD, CC0, BlueOak — permits
proprietary linking and redistribution. **There is no licence incompatibility.** What
exists is a set of unmet *notice* duties, plus one textual conflict.

| # | Obligation | Triggered by | Satisfied? |
|---|---|---|---|
| 1 | **Apache-2.0 §4(d)** — retain attribution notices when redistributing in Source **or Object** form | `.github/workflows/deploy.yml:31-44` builds and pushes both images to `ghcr.io` (`push: true`) — object-form redistribution. Those images contain `asyncpg`, `PyNaCl`, `alpaca-py`, `yfinance`, `requests`, `msgpack`, `python-multipart`; web side `typescript`, `class-variance-authority`, `sharp`, `lightweight-charts` | **No.** `find` for `*notice*`, `*third*party*`, `*attribution*` returns no such file anywhere in the repo. `README.md`'s License section points only at the proprietary `LICENSE` |
| 2 | **MPL-2.0 §3.2** — make source available for the covered files when distributing binaries | `certifi`, `orjson` (unused, `DEP-04`), plus npm `lightningcss`/`axe-core` (dev only) | **No.** Usage is unmodified, so a pointer to upstream discharges it — but a pointer must exist |
| 3 | **LGPL-3.0-or-later** — relinking + the §4 reverse-engineering-for-debugging permission | libvips inside `sharp`, shipped via `infra/Dockerfile.web:18` (`DEP-08`) | **No — and it conflicts textually.** `LICENSE:16-19` forbids anyone to "reverse-engineer … the Software" with **no carve-out for bundled third-party components**, while LGPL-3.0 §4 requires recipients be permitted reverse engineering for debugging modifications to the LGPL portion |
| 4 | **CC-BY-4.0** — attribution for the data | `caniuse-lite` at build time | Practically de minimis; the dataset does not ship in `.next/standalone` |
| 5 | **Apache-2.0 + TradingView's linking requirement** | `lightweight-charts` | **Yes** — see §6.1 |

### 6.1 TradingView / lightweight-charts — this one is met, do not "clean it up"

`apps/web/node_modules/lightweight-charts/LICENSE` is the Apache License 2.0 text; the
package adds a requirement to display a link back to TradingView. The library exposes
`LayoutOptions.attributionLogo` (`apps/web/node_modules/lightweight-charts/dist/lightweight-charts.d.ts:3176`),
which **defaults to `true`**, rendering the in-canvas TradingView logo/link that the vendor's
own documentation states satisfies the requirement.

All three `createChart` call sites at `8b82368` leave it at the default:

| Call site | Line |
|---|---|
| `apps/web/src/components/public-chart.tsx` | `:64` |
| `apps/web/src/components/chart-workspace.tsx` | `:145` |
| `apps/web/src/components/backtest-results.tsx` | `:112`, `:126` |

`grep -rn "attributionLogo" apps/web/src` returns **no matches**, confirming nothing
disables it. This is a genuine pass. Any future refactor that sets
`layout: { attributionLogo: false }` breaks a licence obligation, so it is worth a comment
at the call sites.

*(Working-tree note: an untracked `apps/web/src/components/chart-attribution.tsx` exists on
this machine. It is not part of the `8b82368` baseline and the obligation is already met
without it.)*

### 6.2 `DEP-02` — the fix

Generate a `THIRD-PARTY-NOTICES.md` at the repo root from the lockfiles and copy it into
both images (`infra/Dockerfile.api`, `infra/Dockerfile.web`). Add a one-line carve-out to
`LICENSE` stating that third-party components are licensed under their own terms as listed
in that file — this simultaneously discharges obligations 1, 2 and 4 and removes the
textual conflict in obligation 3. Optionally expose it at a `/licenses` route. The
generation should be a `just` recipe so the file cannot drift from the lock.

---

## 7. Paid / account-gated services

Every account-gated service is genuinely optional and **fails closed rather than degrading
silently** — this is a real strength and should survive v2.

| Service | Cost / account | Gate | Optional? |
|---|---|---|---|
| **Sentry** (SaaS) | Free tier / paid | `apps/api/app/core/observability.py:16-17` returns early without a DSN; `apps/web/src/instrumentation.ts:10-11` returns early without `SENTRY_DSN`/`NEXT_PUBLIC_SENTRY_DSN` | **Yes** — correctly DSN-gated on both sides, no-op when absent |
| **Alpaca** | Free paper keys; live requires an account | `apps/api/app/modules/market_data/providers/alpaca_provider.py:41-42` raises `AppError` on missing keys rather than returning empty data | **Yes** — key-gated, fails loudly |
| **Google Gemini** | Free-tier key | `apps/api/app/modules/ai/providers/gemini.py:19-20` raises on a missing key | Yes, but it is the **default** provider (`.env.example:68`, `Dockerfile:27`). See `DEP-21` |
| **Ollama** | Free, fully local | `.env.example:67` base URL; no key | Yes. But the default model is Llama 3.1 — see `DEP-19` |
| **yfinance → Yahoo** | Free, no key | none | Yes in the sense that no account is needed; **no** in the sense that it is the primary equity source (§8) |
| **CCXT → exchange public endpoints** | Free, no key | none | Public OHLCV only |

**No dependency requires an account to run the application.** A clean checkout with no
keys boots, seeds, and serves crypto data.

Two documentation-level issues sit on top of that good design:

- `DEP-21` — `.env.example:62` frames the AI choice as "both options are FREE", which
  conflates *zero cost* with *unrestricted use*. Gemini is the default
  (`.env.example:68`, `Dockerfile:27`), and free-tier terms for consumer AI APIs generally
  permit the provider to use submitted content for product improvement including human
  review (**unverified offline — check current terms**). What leaves the boundary is the
  user's natural-language strategy text and backtest result numbers, POSTed to
  `https://generativelanguage.googleapis.com` (`gemini.py:12,37`). One line in
  `.env.example` noting that Ollama is the zero-egress option would fix the framing.
  Separately, `gemini.py:37` passes the key as a URL query parameter
  (`params={"key": self._api_key}`) rather than the `x-goog-api-key` header, so it lands in
  proxy and access logs.
- `DEP-19` — the Ollama runtime is MIT, but **model weights are licensed separately from
  the library.** `apps/api/app/modules/ai/providers/ollama.py:15` defaults to
  `model: str = "llama3.1"` and `.env.example:64` instructs `ollama pull llama3.1`.
  Llama 3.x ships under the Meta Llama Community License — not OSI-approved, with an
  acceptable-use policy, a commercial MAU threshold, and a "Built with Llama" attribution
  requirement (**unverified offline**). Default to a permissively licensed model instead —
  `qwen2.5` or `mistral`, both Apache-2.0 — and keep `llama3.1` as a documented opt-in.

---

## 8. Market-data ToS and redistribution risk

This is the largest legal exposure in the repository, and it is not a software licence.

### 8.1 `DEP-01` — yfinance is the default equity source, and it impersonates a browser

**Severity: high.** Four facts, each verified in this checkout:

1. **yfinance is the primary source for every equity in the seed universe.**
   `apps/api/app/modules/market_data/seed.py:28,36,44` register
   `("yfinance", "AAPL", True)`, `("yfinance", "MSFT", True)`, `("yfinance", "SPY", True)` —
   the trailing `True` marks the primary source; Alpaca is registered as the non-primary
   fallback on each.
2. **Its HTTP layer forges a Chrome TLS fingerprint.** yfinance 1.4.1 routes through
   `curl_cffi`; the installed source at `.venv/Lib/site-packages/yfinance/_http.py:61` reads
   `return _backend.Session(impersonate="chrome")`. `uv.lock` confirms `curl_cffi 0.15.0` is
   pulled solely by yfinance. Impersonating a browser's JA3/TLS fingerprint is a
   circumvention of anti-automation controls, not an incidental user-agent string.
3. **The derived data is served to anonymous callers on crawlable pages.**
   `apps/api/app/modules/market_data/public_router.py:1-4` — "PUBLIC, unauthenticated read
   API that powers the per-ticker SEO pages … these endpoints are crawlable".
4. **The library licence does not cover the data.** yfinance's METADATA declares
   `License: Apache` for the *library*. Yahoo's Terms of Use prohibit automated access to
   and redistribution of Yahoo Finance data (**unverified offline — the ToU is not a file in
   this repo**).

The library licence is clean; the acquisition path and the public redistribution are the
problem. The combination — scrape via impersonation, then re-serve on an SEO surface — is
what converts a tolerated developer convenience into a product-level risk.

**Recommendation.** Treat yfinance as a local/dev convenience, not a production source for a
public product: (a) make Alpaca IEX (contractual, attributable) the primary source for the
public equity pages and demote yfinance to a keyless local fallback behind an env flag; or
(b) if yfinance stays, remove equities from the unauthenticated public surface entirely so
no scraped data is redistributed. Independently, surface the per-bar `source` — it is already
stored on the `ohlcv` model — in the public schemas and render it in the data badge, so every
displayed price names its vendor.

### 8.2 The other two sources

| Source | Access | Redistribution | Attribution |
|---|---|---|---|
| **CCXT → exchange public OHLCV** (`ccxt_provider.py:55` `fetch_ohlcv`) | Public endpoints; access is permitted | Exchange terms generally restrict onward redistribution of market data (**unverified offline**) | Typically required; none is currently shown anywhere in the UI or schemas |
| **Alpaca / IEX** (`alpaca_provider.py:43-50`) | Requires an account | **Contractual** — redistribution requires a market-data agreement | Defined by the agreement |

### 8.3 The implication for bundling demo data

There is currently **no bundled dataset**: `apps/api/app/modules/market_data/seed.py`
registers instruments and vendor symbol mappings only, and bars are fetched live
(`justfile:16-22`, `seed-demo` calls `just backfill` per symbol and tolerates provider
failure with `-` prefixes). Tests synthesise their own bars inline. There is no
`apps/api/tests/fixtures/` directory at all.

So backtest reproducibility in CI and in demos currently depends on network calls to Yahoo
and Coinbase. v2 wants a deterministic fixture. Every real-data option for a *committed*
fixture is encumbered:

| Candidate | Verdict |
|---|---|
| Yahoo-derived bars | **Not redistributable.** ToU prohibits redistribution, and the acquisition path here is impersonation-based scraping (§8.1). Committing a Yahoo-derived CSV converts a usage-ToS question into a distribution one — and the repo is pushed to a public Hugging Face Space per `docs/DEPLOY_FREE_CLOUD.md` |
| Exchange (Coinbase/Binance) public OHLCV | **Restricted.** Access is permitted; onward redistribution generally is not, and attribution is typically required. Better than Yahoo, still not clean |
| Alpaca / IEX | **Contractual.** Requires a market-data agreement |
| Genuinely free-to-redistribute real series (some exchange archives, some government data) | Exists, but each needs individual licence review, and none of it is the 1-minute equity/crypto OHLCV this engine consumes |

**Conclusion: no real-data path yields a committed fixture with clean rights.** See §10.

---

## 9. Proposed v2 additions — licence clearance

`docs/v2/` contained no brief at the time this list was drawn up, so this is a
forward-looking clearance list rather than a validation of a fixed plan. Nothing below has
been added to any manifest.

### 9.1 Safe to adopt — permissive, no new obligation class

| Candidate | Licence | Why acceptable |
|---|---|---|
| `langgraph` | MIT | Same obligation class as the existing tree (notice retention). No new duty |
| `langchain-core` | MIT | As above |
| `pgvector` (extension) | PostgreSQL Licence | Permissive, BSD-like. **Note:** the baseline migration already creates the `vector` extension unconditionally without using it — v2 should make that create *intentional* rather than inherit it |
| `pgvector-python` | MIT | |
| `sentence-transformers` | Apache-2.0 | Adds a NOTICE entry — already required for `asyncpg`/`PyNaCl`, so no new class of work once `DEP-02` is fixed |
| `fastembed` | Apache-2.0 | As above; lighter than sentence-transformers for pure inference |
| `onnxruntime` | MIT | |
| `mlflow` | Apache-2.0 | NOTICE entry only |
| `scikit-learn` | BSD-3-Clause | Same class as `pandas`/`numpy` |
| `xgboost` | Apache-2.0 | NOTICE entry |
| `lightgbm` | MIT | |
| `opentelemetry-*` | Apache-2.0 | NOTICE entry. Note `@sentry/opentelemetry` is already present transitively in the web tree |
| `exchange-calendars` | Apache-2.0 | Calendar *code* is Apache; verify any bundled holiday data separately |
| `pandas-market-calendars` | MIT | |
| `pyarrow` | Apache-2.0 | The natural fixture format (§10) |
| `polars` | MIT | |
| `bt` | MIT | The permissive differential-testing oracle — see §9.3 |
| `evidently` | Apache-2.0 | Drift monitoring |
| Ollama runtime | MIT | Already in use; the *weights* are the licence question (§7) |

All licences in this table are **unverified offline** — they are recalled, not read from a
lockfile, because none of these packages is installed in this checkout. Verify each against
its `METADATA` at the moment it is added, exactly as §1.2 did for the current tree.

### 9.2 Needs an explicit decision before adoption

| Candidate | Issue | Decision |
|---|---|---|
| **Embedding model weights** | Weights are licensed *separately from the library*. `BAAI/bge-small-en-v1.5` is MIT and `all-MiniLM-L6-v2` is Apache-2.0 — both fine | Pin the model card explicitly rather than relying on a library default, and record the weights' licence alongside the code's in the notices file |
| **`vectorbt`** | The OSS core is Apache-2.0, but **vectorbt PRO is a paid commercial licence** with a distinct API surface | Adopt only if CI can assert that no PRO-only API is imported. Otherwise prefer `bt` |
| **Local LLM weights** | Same code-vs-weights split as above | Default to **Qwen2.5** or **Mistral** (Apache-2.0); Phi is MIT/Apache-2.0. Offer Llama 3.x and Gemma as opt-in only |

### 9.3 What to avoid

- **`backtesting.py` — AGPL-3.0. Do not add it, in any dependency group.** A differential
  oracle runs *in-process* with TradePulse code, and AGPL §13's network-use clause reaches a
  hosted product. Classifying it "dev-only" does not fix this: dev dependencies are imported
  by test code living in the same repository, and CI images that bundle it are distributed.
  This would be the first copyleft package in a currently copyleft-free backend and would
  put the proprietary `LICENSE` in direct conflict. **Use `bt` (MIT) or a hand-written
  oracle instead** — the property/differential tests already drafted in the working tree
  (`apps/api/tests/quant/`) take the hand-written-oracle route, which is the right call.
- **Non-OSI model licences as defaults.** Llama Community License, Gemma Terms of Use, and
  similar carry acceptable-use policies, commercial thresholds, and naming requirements that
  a *default* silently imposes on every operator. Permissive weights as the default; anything
  else opt-in and documented. `DEP-19` is the existing instance of this mistake.
- **Any new FSL / BUSL / SSPL / Elastic-Licence package on the production path.** The tree
  currently has exactly one (`@sentry/cli`, unused, `DEP-09`); the target is zero.
- **New floating `:latest` image tags.** `DEP-10` — a floating tag can change licence
  without a commit.

---

## 10. Recommendation — the bundled deterministic dataset

`DEP-20`. **Generate the v2 fixture synthetically, and say so in the file.**

Given §8.3, a seeded generator is the only path with *zero* third-party rights attached:

| Property | Why synthetic delivers it |
|---|---|
| **Redistributable** | The output is an original work of the repo owner, distributable under the proprietary `LICENSE`. No vendor ToS, no market-data agreement, no attribution duty |
| **Deterministic** | Fixed RNG seed plus a pinned generator version makes it byte-identical across platforms and across CI runs — which is the actual requirement |
| **Honest** | A synthetic series cannot be mistaken for a track record, which matters for a product whose public surface already carries a hypothetical-results banner (`apps/api/app/modules/market_data/public_router.py:6-7` cites product invariant #3) |
| **Auditable** | The generator is code in the repo; anyone can regenerate the bytes and diff them |

**Concrete shape:**

1. A seeded GBM or jump-diffusion generator producing OHLCV, committed as code (not just as
   output) so the fixture is reproducible from source.
2. Output written to `apps/api/tests/fixtures/` as Parquet (or CSV if `pyarrow` is not
   adopted) — this directory does not exist yet and is a clean addition.
3. A `README` **beside the data** recording: the generator function and its module path, the
   exact seed, the generator version, the schema, and an explicit
   **"synthetic — not market data"** statement. That last line is what keeps the fixture from
   ever being mistaken for a track record if it leaks onto a public page.
4. A test that regenerates from the seed and asserts byte-equality with the committed file,
   so silent drift in numpy/pandas versions is caught rather than absorbed.
5. Keep `just backfill` (`justfile:16-22`) as the opt-in developer path for real data, and
   **never commit real bars.**

One caveat worth stating plainly: synthetic data validates *determinism, plumbing, and
invariants*, not *realism*. It is the right substrate for CI reproducibility and for demos;
it is not evidence that the engine behaves correctly on real market microstructure. Those
are different tests and the fixture README should not blur them.

---

## 11. Supply-chain observations (CI)

Recorded here because they govern how third-party code enters the product, even though none
is a licence issue.

| id | Observation | Evidence |
|---|---|---|
| `DEP-07` | **Dependabot's Python config cannot produce a single update.** `.github/dependabot.yml:6-8` declares `package-ecosystem: "pip"`, but the project is uv-managed and `uv.lock` is what CI enforces (`ci.yml:41`, `infra/Dockerfile.api:8`, `Dockerfile:13`). The pip ecosystem does not maintain `uv.lock`. Compounding it, every specifier at `pyproject.toml:8-28` is an unbounded `>=` except `redis>=5.0,<6` (`:16`), so new upstream releases already satisfy the range and there is nothing to bump. Net effect: the backend dependency set is frozen indefinitely, and `pip-audit` findings have no remediation path | Fix: switch to Dependabot's dedicated **uv** ecosystem (**verify the exact key against current Dependabot docs — this predates the lockfile dates**), keep the monthly/grouped/minor-patch policy, and add a scheduled `uv lock --upgrade` PR workflow as a belt-and-braces measure |
| `DEP-12` | **Both vulnerability audits are advisory-only, and the auditing tool is unpinned.** `ci.yml:61-62` runs `uv run --with pip-audit pip-audit` under `continue-on-error: true`; `ci.yml:78-79` runs `npm audit --audit-level=high` under `continue-on-error: true`. Neither can fail the build. `pip-audit` floats per run via `--with` and is absent from the dev group | Fix: add `pip-audit` to `[dependency-groups].dev` so it is version-locked; drop `continue-on-error` from a narrow gate first (`npm audit --audit-level=critical`), then tighten — but only alongside the `DEP-07` fix, or findings remain unfixable |
| `DEP-11` | **The gitleaks binary is installed with no integrity check, and a mutable-tag third-party action holds the deploy key.** `ci.yml:98-99` pipes `curl -sSfL …gitleaks_8.21.2_linux_x64.tar.gz` straight into `sudo tar -xz -C /usr/local/bin` — no checksum, no signature, root-owned PATH destination. `deploy.yml:56` uses `appleboy/ssh-action@v1` (mutable major tag) and hands it `secrets.DEPLOY_SSH_KEY`; `docker/build-push-action@v7` (`:31,:40`) and `docker/login-action@v4` (`:25`) are likewise tag-pinned. `.github/dependabot.yml` ignores major updates for `github-actions`, so these tags are never reviewed | Fix: `sha256sum -c` before extraction; SHA-pin every third-party action to a full commit SHA with a version comment, starting with the one that handles a production credential |
| `DEP-13` | **`pre-commit` is the documented entry point but is not a dependency.** `.pre-commit-config.yaml:1` instructs `uv run pre-commit install`. `pre-commit` appears nowhere in `pyproject.toml`, is absent from `uv.lock`, and is not installed — so the documented command fails on a clean checkout. CI never runs `pre-commit run --all-files` either; `ci.yml` invokes ruff/mypy/lint-imports directly and runs the gitleaks binary standalone | Fix: add `pre-commit>=3.7` to the dev group, add a `just hooks` recipe, optionally add a CI job so the config is enforced rather than aspirational |
| `DEP-16` | **pre-commit hook revisions are stale with no update mechanism.** `.pre-commit-config.yaml:4` pins `pre-commit-hooks` at `v5.0.0` and `:23` pins `gitleaks` at `v8.21.2` (duplicated at `ci.yml:98`), both late-2024 releases. The ruff hook at `:15` is `v0.15.15`, matching locked ruff — so the drift is specific to the other two. Dependabot covers pip, npm, and github-actions only; nothing updates pre-commit revs | Fix: `pre-commit autoupdate` and re-pin, keeping the gitleaks rev and the `ci.yml:98` URL in sync |
| `DEP-15` | **`pyproject.toml` declares no licence metadata**, so a built wheel ships as unlicensed despite `LICENSE:1` saying "All rights reserved". `[project]` at `pyproject.toml:1-29` sets name/version/description/requires-python/readme/dependencies but no `license`, no `license-files`, no `classifiers`. The backend is hatchling (`pyproject.toml:48-53`) packaging `apps/api/app` | Fix: add PEP 639 `license = "LicenseRef-Proprietary"` + `license-files = ["LICENSE"]`, and `classifiers = ["Private :: Do Not Upload"]` — the classifier is the standard guard that makes an accidental `twine upload` fail |
| `DEP-18` | **The `redis<6` cap cites an arq constraint that may no longer hold.** `pyproject.toml:16` reads `"redis>=5.0,<6",  # capped: arq (the task queue) requires redis[hiredis]>=4.2,<6`. The lock resolves `arq 0.28.0`, whose dependency block lists `{ name = "redis", extra = ["hiredis"] }` without exposing the specifier. Whether arq 0.28 still carries the `<6` bound **cannot be confirmed offline**. If stale, it silently holds redis-py a major version back and blinds Dependabot/pip-audit to fixes in redis 6.x | Fix: check `arq 0.28.0`'s `requires-dist`; if relaxed upstream, drop `<6` and re-lock. Either way, name the arq version the comment was derived from so the next reader can re-verify cheaply |

---

## 12. Finding register

| id | Title | Severity | Class |
|---|---|---|---|
| `DEP-01` | yfinance (default equity source) uses Chrome TLS impersonation to evade Yahoo bot detection; derived data is served on public crawlable pages | high | ToS / redistribution |
| `DEP-02` | No NOTICE / THIRD-PARTY-NOTICES anywhere; Apache-2.0 §4(d) and MPL-2.0 §3.2 duties unmet for images pushed to GHCR | high | attribution |
| `DEP-03` | `pandas` and `numpy` imported by the backtest engine but undeclared; reachable only via optional market-data vendors | high | correctness + attribution |
| `DEP-07` | Dependabot's `pip` ecosystem cannot maintain `uv.lock`, and every spec is an open lower bound — no Python update can ever be produced | high | supply chain |
| `DEP-04` | `orjson` declared, never imported; sole MPL-2.0 package in the production backend | medium | unused |
| `DEP-05` | `python-multipart` declared; API has no form or file-upload endpoint | medium | unused |
| `DEP-06` | `hypothesis` declared with no property tests at `8b82368`; only MPL-2.0 dev package (closes by use if the untracked `tests/quant/` work lands) | medium | unused |
| `DEP-08` | LGPL-3.0-or-later libvips binaries ship in the web image via an unused image optimizer; `LICENSE:16-19` anti-reverse-engineering clause conflicts with LGPL-3 §4 | medium | licence conflict |
| `DEP-09` | `@sentry/cli` (FSL-1.1-MIT, non-OSI, `dev=false`) installs on the production path, yet `withSentryConfig` is never applied | medium | non-OSI, unused |
| `DEP-10` | Three infrastructure images carry non-OSI or copyleft licences behind floating tags, undocumented | medium | image licensing |
| `DEP-11` | gitleaks installed with no integrity check; mutable-tag third-party action holds the deploy SSH key | medium | supply chain |
| `DEP-12` | Both vulnerability audits are advisory-only; `pip-audit` itself unpinned and undeclared | medium | supply chain |
| `DEP-13` | `pre-commit` documented as the entry point but not a dependency, not installed, never run in CI | medium | tooling |
| `DEP-20` | No bundled deterministic dataset; every real-data path for one is encumbered — synthetic generation is the only clean option | medium | v2 design |
| `DEP-15` | `pyproject.toml` declares no licence metadata; a built wheel ships unlicensed | low | metadata |
| `DEP-16` | pre-commit hook revisions pinned to ~2024 with no update mechanism | low | staleness |
| `DEP-17` | Five unused Next.js scaffold SVGs, including Vercel's trademarked logo, ship in the production image | low | unused / trademark |
| `DEP-18` | The `redis<6` cap cites an arq constraint that may no longer hold for the locked arq version | low | staleness |
| `DEP-19` | Default local LLM is Llama 3.1, whose community licence is not OSI-approved and carries AUP and naming terms | low | model licensing |
| `DEP-21` | Free-tier Gemini is the default AI provider; user strategy text leaves the trust boundary under terms permitting provider-side retention, and the key travels in the URL | low | privacy / framing |

---

## Baseline Verification (see BASELINE_VERIFICATION.md)

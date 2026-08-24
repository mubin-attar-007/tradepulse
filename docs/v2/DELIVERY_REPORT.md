# TradePulse v2 — Delivery Report

**Date:** 2026-08-24 · **Baseline commit:** `8b82368` · **State:** all changes in the working tree, not committed.

This records what was audited, what was changed, what was measured, and what was
deliberately left undone. Every number below came from a command that was run on
this machine; anything not executed is marked `NOT RUN` with the reason.

---

## 1. Headline

| | Baseline (`8b82368`) | Now |
|---|---|---|
| Backend tests | 78 passing | **305 passing, 1 skipped** |
| Coverage (backend) | 68% | **77%** |
| `ruff format --check` | ❌ 2 files unformatted | ✅ 177 formatted |
| `lint-imports` | ❌ 6 violations, 5 waivers | ✅ **2 contracts kept, 0 waivers** |
| `mypy` | ✅ 101 files | ✅ **135 files** |
| `docker compose up --wait` | ❌ DB image exits 1 | ✅ healthy |
| AI copilot | ❌ HTTP 500 (invalid key, no fallback) | ✅ works with **no key, no network** |
| AI evaluation | none | **235 cases; 210 graded, 210 pass (100%) in 1.0 s** |
| API surface | 33 paths | 46 paths |
| Backend source | 101 files / 9,099 LOC | 135 files / 15,019 LOC |
| Test source | 12 files | 30 files / 5,664 LOC |

Four defects were found that silently corrupted results and were invisible to the
existing tests. Each is now fixed with a regression test that fails against the old
code (§3).

---

## 2. What was done

### 2.1 Audit and baseline (deliverable §3, §4)

Eight parallel domain audits, each finding adversarially verified by an independent
reviewer before being accepted. **188 findings** (6 critical, 45 high), one refuted
and dropped. Documents in `docs/v2/`:

| Document | Contents |
|---|---|
| `CURRENT_STATE_AUDIT.md` | Master audit: structure, routes, models, migrations, workers, infra, CI, plus the consolidated findings register |
| `QUANT_CORRECTNESS_AUDIT.md` | Engine, indicators, metrics, reproducibility, test-coverage gaps |
| `AI_SYSTEM_AUDIT.md` | Providers, prompts, structured output, injection surface, data egress, evaluation gaps |
| `CLAIM_AUDIT.md` | 70-entry claims register with verdicts and required fixes |
| `DEPENDENCY_LICENSE_AUDIT.md` | Per-dependency licence, obligations, ToS/redistribution risk |
| `BASELINE_VERIFICATION.md` | Every baseline command, its exact result, and what was NOT run |
| `TARGET_ARCHITECTURE.md` | The architecture as built, with a known-limitations section |
| `IMPLEMENTATION_ROADMAP.md` | Status per capability area and the sequenced remaining phases |

The baseline verification recorded four genuine failures before any change: the
pinned TimescaleDB image cannot start (upstream ships a 0-byte `timescaledb.so`, so
`just up`, `just bootstrap` and CI's `services.db` were all broken), `ruff format`
and `lint-imports` were red on `main`, and the AI copilot returned 500.

### 2.2 Architecture (deliverable §8)

Both import-linter violations were fixed **structurally**, not waived:

- **`indicators/` created below `market_data`.** An indicator is a primitive the
  chart API, the DSL, the engine and the feature store all need to read identically
  — not a backtesting concern. It owns the closed catalog and the causal computation.
- **`research/` created above `backtesting`.** The composition surfaces (`signal.py`,
  `reference_backtest.py`, `public_router.py`) moved up out of `market_data`.

`ignore_imports` is now **empty**. New modules: `indicators`, `robustness`,
`experiments`, `evaluations`, `research`, `ai/graph`. The API surface is unchanged
by the move — the OpenAPI diff for the refactor was a single added docstring.

### 2.3 Quant correctness (deliverable §16, §17)

New suite in `apps/api/tests/quant/` — 92 tests across five kinds of evidence:

- **Golden fixtures** — hand-derived exact fills, commissions and equity, with the
  arithmetic written out in the test so a reviewer can check it without running it.
- **Look-ahead canaries** — inter-bar across all eight indicators, plus the
  **intrabar** class the original canary structurally could not see.
- **Differential testing** — an independently written reference engine, driven by
  Hypothesis over 200 random price paths, cost models and exit configurations,
  compared trade-by-trade.
- **Property tests** — accounting identity, determinism, fills inside the bar,
  position caps, risk-halt enforcement, commission rate.
- **Definition tests** — every metric against series with known answers.

### 2.4 Robustness lab (deliverable §18)

`app/modules/robustness/`: walk-forward (anchored and rolling, with embargo), purged
k-fold, a bounded parameter-sweep language, cost stress, Monte Carlo (trade
reshuffling and block bootstrap), and multiple-testing correction (Probabilistic and
Deflated Sharpe, Benjamini-Hochberg).

The stability verdict is a **checklist of seven named checks**, each carrying its
evidence and threshold. The headline is the **weakest link, never an average**, and
a check that could not run reports `insufficient_evidence` rather than passing. No
language model is involved.

### 2.5 Experiments (deliverable §19)

`experiments` table: append-only, with the provenance needed to reproduce a run —
strategy version, spec hash, dataset fingerprint, engine/metrics/cost-model
versions, seed, and the full analysis config. A rerun creates a new row.

### 2.6 AI layer (deliverable §10–§14, §22)

The pipeline is now: **deterministic extraction → refusal → IR generation → schema
validation → semantic verification → compilation → bounded repair → trace**.

Design decisions worth naming:

- **The model emits a compact IR, never a StrategySpec.** It removes a whole class
  of errors (invented indicator ids, missing output selectors) and is ~5× fewer
  tokens — which on a CPU-only local model is the difference between usable and not.
- **Semantic verification** was entirely missing. The v1 pipeline checked that
  output was schema-*valid*, which is silent about whether it was the strategy the
  user asked for. The same deterministic extractor that parses the request is the
  reference the model is checked against.
- **A deterministic provider** makes the whole pipeline testable and demonstrable
  with no key, no model download and no network — and is always labelled as
  rule-based, never presented as model output.
- **Provider routing** with capabilities, a local-only policy gate, and a circuit
  breaker; every routing decision is returned in the trace.
- **Grounded narration** is checked arithmetically: every number in generated text
  is matched against the evidence payload. No LLM judge.

### 2.7 Research graph (deliverable §10)

One LangGraph state graph: `classify → extract → generate → validate → plan →
await_approval → experiment → report`. Its entire capability surface is the typed
functions in `ai/graph/tools.py` — there is no code execution, no SQL, no shell, no
HTTP client and no order-placing tool, because none exist for it to call.

**Approval is an HMAC over content** (strategy hash + dataset fingerprint + plan
hash + risk-policy version + owner), not a boolean. Verified end to end below.

### 2.8 Evaluation (deliverable §22)

235 reviewable JSON cases (100 valid, 30 ambiguous, 30 unsupported, 30 safety, 20
injection, 25 grounding), a runner that grades against the IR vocabulary, a CLI, and
a CI gate at `--min-pass-rate 1.0`.

### 2.9 Security, claims and frontend

Security: global CSRF enforcement at the single auth choke point, session revocation
on credential change, trusted-proxy IP derivation (default off), per-account login
budgets that **count failures only**, single-use hashed reset tokens, a published
encryption key removed from the deploy guide.

Claims: README, landing page, OG card and FAQ rewritten around what the engine
actually does. Removed: "Sub-second", "Live data", "spread" modelling, "visual
builder", "institutional-grade", "measured against buy & hold", "production-grade".

---

## 3. The four silent-corruption defects

Each was invisible to the existing tests, changed reported numbers, and now has a
regression test that fails against the old code.

### 3.1 Still-forming bars served as closed bars (critical)

Only 1-minute bars are stored; higher timeframes are aggregated on read. That
aggregation returned the **current, partial bucket** as a finished bar. Measured on
live data at 09:48 UTC:

```
bucket 2026-08-24T03:00:00+00:00  constituent 1m bars = 13  <-- PARTIAL
...
bucket 2026-08-24T09:00:00+00:00  constituent 1m bars = 18  <-- PARTIAL
```

Every surface that reads bars — the engine, the signal card, the public reference
backtest — was therefore making decisions on unfinished bars, which is exactly what
invariant #3 exists to prevent, on **all** the timeframes the product defaults to.
A second bug in the same query built the first bucket from only the slice inside the
query window, so its open/high/low were wrong.

Fixed in `market_data/repository.py:get_bars` (a `HAVING` clause on elapsed time,
plus widening the scan to the containing bucket) and verified:

```
1h buckets: 6 — every one bar_count=60, every one fully elapsed
```

### 3.2 ATR position sizing read the fill bar's own high/low (high)

`atr_arr[i]` where `i` is the bar being filled at. Perturbing only that bar's
high/low — holding its open and close identical, so nothing knowable at decision
time changed — moved position size **250 → 9.90**, a 25× difference. The existing
look-ahead canary perturbs only bars *after* the cut, so it structurally could not
see this. Fixed to read the decision bar, with an intrabar canary that was confirmed
to fail against the old code.

### 3.3 Trailing stops filled at the open instead of the trail (high)

The trail ratchets on the bar's high, and the gap test then compared against the
**already-ratcheted** level — and an open is mechanically below a freshly ratcheted
trail, so every trailing exit on a rallying bar was booked as a gap. On a 102 → high
130 → low 101 bar with a 10% trail, the exit was reported at 102 when the level that
fired was 117. Fixed by capturing the level live at the open; the genuine gap path
is preserved and separately tested.

### 3.4 Metrics that were confidently wrong (high)

- Annualization was calendar-blind: hourly equity bars annualized at 8,760 periods
  per year instead of ~1,638 (2.3× too large), and the reference backtest runs
  hourly on a mixed crypto/equity universe.
- No sample-size floor: a six-bar run reported `sharpe: -12.33, sortino: -54045.13`.
  A smooth five-point curve scored 14,820 at `1d` and 562,410 at `1m` — the same
  curve, relabelled.
- `profit_factor` returned the **gross dollar profit** when there were no losing
  trades: two wins of $500 and $700 reported a "ratio" of 1200.0, on a crawlable page.
- Sortino used the standard deviation of losses about their own mean, not downside
  deviation.

Rewritten with calendar-aware annualization, wall-clock CAGR, documented sample-size
floors that return `None` with a stated reason, and "undefined is not zero"
throughout. The frontend now renders `n/a` rather than coercing null to a number.

Also fixed: `Trade.commission` recorded only the exit leg, so anything summing it
understated frictions by half; `upsert_bars` had no chunking and failed past ~3,600
bars with an opaque driver error.

---

## 4. Verification — every command run

Backend gates, from the repository root:

| Command | Result |
|---|---|
| `uv run pytest` | **305 passed, 1 skipped** (340 s) |
| `uv run pytest --cov=app` | **77%** (6,403 statements) |
| `uv run ruff check apps/api` | ✅ All checks passed |
| `uv run ruff format --check apps/api` | ✅ 177 files formatted |
| `uv run mypy apps/api/app` | ✅ 135 source files, no issues |
| `uv run lint-imports` | ✅ 2 contracts kept, 0 broken |
| `uv run alembic upgrade head` | ✅ 7 migrations, single linear head |
| `uv run python -m app.cli.export_openapi` + `git diff --exit-code` | ✅ no drift |
| `npm run gen:api` + `git diff --exit-code schema.ts` | ✅ no drift |
| `uv run python -m app.cli.evaluate --profile deterministic` | ✅ **210/210 (100%)**, 1.0 s |

Frontend, from `apps/web`:

| Command | Result |
|---|---|
| `npm run lint` | ✅ clean |
| `npm run typecheck` | ✅ clean |
| `npm run build` | ✅ 27 static pages |

Infrastructure:

| Command | Result |
|---|---|
| `docker compose up -d --wait` | ✅ both containers healthy |
| `docker build -f infra/Dockerfile.api` | ✅ exit 0 |
| `docker build -f infra/Dockerfile.web` | ✅ exit 0 |

### 4.1 End-to-end on real market data

14,399 real 1-minute BTC/USD bars backfilled via Coinbase (no API key), aggregated
to 240 closed hourly bars.

**CSRF now enforced** — the baseline accepted a state-changing POST with only a
session cookie:

```
POST /ai/clarify  without x-csrf-token  -> 403
POST /ai/clarify  with    x-csrf-token  -> 200
```

**Research graph, propose phase** — stops at the gate, runs nothing:

```
stage: await_approval   approval_required: True   experiment_id: None
trace: classify=ok extract=ok generate=ok validate=ok plan=ok await_approval=blocked
```

**Approval is bound to content** — editing the stop from 2% to 10% and replaying the
same token:

```
403 — "This approval was issued for a different strategy, dataset, plan, or risk
policy. Anything material changed since it was granted, so it no longer applies."
```

**Approved execution** — and the lab reaches a negative verdict on a real strategy:

```
stage: done    verdict: fail
"Failed on out_of_sample, cost_sensitivity. A strategy that fails any one of these
 has not demonstrated an edge, regardless of how good its headline backtest looks."
  - out_of_sample: Compounded out-of-sample return is 0.00%.
  - cost_sensitivity: Not profitable at the baseline cost assumption.
  - parameter_stability: Only 33% of the parameter grid was profitable.
reproduce: experiment_id / spec_hash / data_fingerprint / plan_hash
```

That result is the system working: 240 hourly bars is not enough history for a 50-period
EMA crossover to trade, and it says so rather than reporting an impressive-looking zero.

### 4.2 The local model, measured honestly

Ollama 0.32.15 with `qwen2.5:3b-instruct` (Apache-2.0, 1.9 GB) on 6 CPU cores, no
usable GPU. Measured throughput **~2.6–2.9 tokens/second**.

| Case | Outcome | Attempts | Tokens | Wall clock |
|---|---|---|---|---|
| EMA crossover | ✅ correct spec, 0 semantic issues | 2 (1 repair) | 2,453 | 471 s |
| RSI threshold | ❌ ran out of repairs | 3 | 3,139 | 381 s |
| Unsupported request | ✅ refused | 0 (never called) | 0 | 0 s |

Two real findings came out of this and were fixed:

1. **At temperature 0.2 the repair loop regenerated byte-identical output** — same
   token count, same error, three times. A repair has to explore or it is a retry.
   Repair now runs at 0.6 and leads with the error rather than restating the format
   guide. The RSI case then went 4 → 3 → 1 errors: converging, just not inside two
   rounds. `AI_MAX_REPAIRS` is configurable for exactly this.
2. **The model's output exposed a gap in my own semantic checker.** It produced a
   correct entry and an exit of "EMA 20 crosses below 0". Every individual constraint
   was satisfied *somewhere* in the strategy, so nothing was flagged. The checker now
   compares operand sets per rule and catches it.

**Honest conclusion:** a 3B model on CPU is viable for the demo path but not
reliable enough to be the default for complex requests. The configured chain falls
back to the deterministic compiler, which is always available and always labelled.

---

## 5. What was NOT done, and why

Scope was agreed as depth-first on the flagship spine. These are deliberate omissions,
not oversights:

| Area | State | Why |
|---|---|---|
| ML Lab, model registry, drift, MLflow | not started | A supervised lab over a few hundred bars per instrument would be theatre. It needs the dataset-snapshot layer first. |
| RAG / knowledge index | not started | The retrieval corpus does not exist yet; the graph currently needs no retrieval to do its job. |
| OpenTelemetry, Grafana dashboards | not started | The trace surface exists in-product (stage log, routing decisions, attempts). OTel adds operational weight before there is traffic to observe. |
| Paper-trading order state machine | not started | Paper trading still re-runs the engine over the session window. The audit's finding TRD-006 (retroactively mutating fills on timeframes above 1m) is **documented but unfixed**. |
| Short selling, multi-instrument portfolios | rejected at the DSL | Now refused with an explicit engine-capability error instead of being silently ignored. |
| Corporate actions, exchange calendars library | partial | Calendar-aware annualization and exchange-timezone session filtering are in; split/dividend adjustment is not. |
| Bundled deterministic dataset | not started | The free path currently uses live no-key providers (CCXT/yfinance), which works but is not reproducible across machines. |
| Frontend v2 navigation (Research/Robustness/Evals/Traces pages) | not started | The backend endpoints exist and are contract-generated; the UI for them does not. |

`docs/v2/IMPLEMENTATION_ROADMAP.md` sequences these.

---

## 6. Deployment status

**Nothing was deployed.** The deployable artifacts are verified, but I do not have —
and did not ask for — the credentials any target requires.

Ready:
- `infra/Dockerfile.api` and `infra/Dockerfile.web` both build (exit 0).
- Migrations apply cleanly from scratch to a single head.
- `compose.yaml` and `infra/compose.prod.yaml` now pin a **working** TimescaleDB tag
  (`2.18.2-pg16`); the previously pinned `2.17.2-pg16` cannot start at all.

Blocking, in the order they must be resolved:

1. **`infra/.env.prod` does not exist.** Copy `infra/.env.prod.example` and fill it.
   Generate a fresh `BROKER_CRED_KEY`; **the key previously published in
   `docs/DEPLOY_FREE_CLOUD.md` must be treated as compromised** — it is in git
   history, so anything ever encrypted with it needs re-entering.
2. **`NEXT_PUBLIC_SITE_URL` is unset**, and the frontend now degrades honestly by
   emitting `noindex` and an empty sitemap rather than asserting a placeholder
   domain. No deploy path currently passes it as a build arg — `deploy.yml` and
   `infra/compose.prod.yaml` need it added before a public deploy, or the site ships
   de-indexed.
3. **The Gemini key in `.env` is invalid** (`API_KEY_INVALID`, verified directly).
   This no longer breaks anything — the chain falls back — but the remote profile
   will stay unconfigured until it is replaced.

To run the full stack locally right now:

```bash
docker compose up -d --wait
uv run alembic upgrade head
uv run python -m app.cli.seed
uv run python -m app.cli.backfill "BTC/USD" --days 10
uv run uvicorn app.main:app --reload --app-dir apps/api --port 8080   # API
uv run arq app.worker.WorkerSettings                                   # worker
npm --prefix apps/web run dev                                          # web
```

For a local-first AI path: `ollama pull qwen2.5:3b-instruct` and set
`AI_PROFILE_CHAIN_RAW=local-balanced,deterministic`. With nothing configured the AI
surface still works, served by the deterministic compiler and labelled as such.

---

## 7. Outstanding review findings not yet actioned

From the independent review of the remediation streams, verified but not fixed:

- **`deploy.yml` / `compose.prod.yaml` do not pass `NEXT_PUBLIC_*` as build args**, so
  a deploy today ships the site de-indexed (see §6.2).
- **`infra/prometheus.yml` references a `credentials_file` the compose stack does not
  mount**, so the observability profile will not scrape until that volume is added.
- **`TRUST_PROXY_HEADERS` is not documented for the Hugging Face path**, where it must
  be `true` or every user shares one rate-limit bucket.
- **The CSRF cookie has no `__Host-` prefix** while the session cookie does. Fixing it
  requires a coordinated backend/frontend change.
- **Paper-trading fills can change retroactively** on timeframes above 1m (TRD-006).

---

## 8. Repository state

All work is in the working tree, **uncommitted** — 124 changed or new paths, nothing
pushed. Recommended before committing: review `git diff` for the four engine fixes in
§3, which change reported numbers for any stored result.

`.gitattributes` now pins `*.py/*.ts/*.tsx/*.md/*.yaml` to LF, because editing on
Windows was silently rewriting whole files with CRLF and burying real changes.

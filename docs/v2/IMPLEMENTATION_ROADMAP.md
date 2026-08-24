# TradePulse v2 — Implementation Roadmap

**Status date:** 2026-08-24.
**Companion document:** `docs/v2/TARGET_ARCHITECTURE.md` describes the system as built. This
document describes what remains, and in what order.

The status table below is derived from reading the code, not from the v2 brief's intent. An area
is `done` only when a reader could verify it from the repository without being told to trust
anything. Where a capability is half-wired — implemented, unit-tested, and called by nothing — it
is `partial`, not `done`.

---

## 1. Status summary

| Area | State | Evidence, and what is missing |
|---|---|---|
| Repository audit | **done** | `docs/v2/CURRENT_STATE_AUDIT.md` (1,350+ lines, findings register with ids), plus `CLAIM_AUDIT.md`, `AI_SYSTEM_AUDIT.md`, `QUANT_CORRECTNESS_AUDIT.md`, `DEPENDENCY_LICENSE_AUDIT.md`. |
| Baseline verification | **done** | `docs/v2/BASELINE_VERIFICATION.md` — 16 passed / 4 failed / 3 with concerns / 5 not run, command by command. The four failures are fixed: `lint-imports` is green, the AI layer no longer depends on a remote key, formatting is enforced, and the compose image pin is resolved. |
| StrategySpec DSL | **done** | `strategies/spec.py`. Closed catalog, mandatory exits/sizing/risk, `extra="forbid"` everywhere, `spec_hash`, and a capability boundary that rejects rather than ignores (`spec.py:206-245`). |
| Engine correctness | **done** | `backtesting/engine.py:221-336`. Next-bar-open fills, gap-aware brackets, trail armed from entry, ATR read from the decision bar, round-trip commission, enforced risk halts. Limits are capability limits (long-only, one instrument, one position), not correctness gaps. |
| Quant test suite | **done** | `apps/api/tests/quant/` — 1,940 lines across seven files: hand-derived golden fixtures, inter- and intra-bar look-ahead canaries, a differential reference implementation driven by Hypothesis, property tests, indicator seeding parity, metric definitions, and a robustness suite whose tests assert the lab can reach a *negative* conclusion. |
| Robustness lab | **partial** | The five attacks, the bounded override language and the stability checklist all run and are wired into `POST /robustness/suite`. Missing: `purged_kfold`, `holdout`, `describe_splits` and `benjamini_hochberg` are implemented and tested but called by nothing; `perturb_start` is documented but does not exist; runs are synchronous and in-process; the reshuffle distribution compounds on notional rather than account equity. |
| Experiments domain | **partial** | The table, the provenance stamping and the append-only write path are real (`experiments/models.py`, `robustness/service.py:81-131`). Missing: nothing ever sets `parent_id`, so lineage is a schema affordance; `by_fingerprint` and `count_trials` are unused, so the deflation sees only one grid's trials; `tags`/`notes` have no write endpoint. |
| Dataset snapshots | **not started** | No `DatasetSnapshot` type exists. `backtesting/service.py:23-28` forward-references one. `data_fingerprint` does hash every bar, so *identity* is solved; *retrieval* of the exact bars behind a past run is not. |
| Market-data quality | **not started** | No NaN, negative-price, `high >= low`, monotonicity or outlier check at any layer, and no DB `CHECK` constraint (`market_data/models.py:62-78`). With immutable final bars, corruption is unrepairable by re-ingestion. Audit `MD-06`. |
| Corporate actions | **not started** | No split or dividend handling anywhere; yfinance is fetched with `auto_adjust=False` (`providers/yfinance_provider.py:48`). Audit `MD-07`. |
| Trading calendars | **partial** | `Instrument.calendar` exists and flows into the engine, the indicators and the metrics (`engine.py:125-130`, `metrics.py:44-47`, `indicators/compute.py:76`), which fixed the annualization defect. But a calendar is a timezone string and a pair of constants — no holiday table, no half-days, no early closes; the streaming session check hardcodes 13:30–20:00 UTC (`market_data/streaming.py:26-28`). |
| AI provider abstraction | **done** | `providers/base.py` (capabilities, locality, classified errors, measurement), `providers/registry.py` (profiles by name, capability-aware routing with a recorded decision trail), `circuit.py` (three-state breaker). |
| Local-first models | **done** | `AI_PROFILE_CHAIN_RAW` defaults to `local-balanced,local-small,deterministic` (`config.py:85`); `AI_LOCAL_ONLY` is a hard policy gate enforced in the router (`registry.py:237-246`); a fresh clone with no keys gets the deterministic compiler rather than a 500 (`registry.py:191-195`). |
| NL→spec compiler | **done** | `ai/ir.py` + `ai/compiler.py` + `ai/service.py`. IR instead of a raw spec, deterministic extraction, bounded repair, applied defaults reported rather than hidden. |
| Semantic verification | **done** | `compiler.verify` (`compiler.py:565-685`) with six constraint kinds including unordered rule-operand comparison. Differences are reported to the user, never silently corrected (`service.py:296-303`). |
| Prompt registry | **done** | `ai/prompts.py` — versioned prompts with temperature attached, recorded on every attempt (`service.py:99`). Four prompts, all with explicit untrusted-data delimiters. |
| AI evaluation | **partial** | 235 cases across six categories, a runner that grades mechanically, and a CI gate at `--min-pass-rate 1.0` against the deterministic provider (`ci.yml:66-69`). Missing: the 25 `grounding` cases carry no assertions and are excluded from the run (`cli/evaluate.py:89-92`) — there is no narration runner; no model-backed scores are recorded anywhere in the repository. |
| Agentic research graph | **partial** | The full stage machine, the deterministic tool surface, bounded loops and the trace are all real (`ai/graph/`). Missing: no LangGraph checkpointer, so `/research/execute` reconstructs state from the client payload; the `clarify` node records questions but has no round-trip to answer them. |
| Human approval | **done** | Content-bound HMAC over owner + spec hash + data fingerprint + plan hash + action + risk-policy version, with a one-hour TTL and error messages that distinguish expiry from subject mismatch (`ai/graph/approval.py`). Enforced by the propose/execute split (`ai/graph/router.py`). |
| RAG / knowledge | **not started** | No document store, no index, no retrieval step. `Capability.EMBEDDING` exists in the enum and nothing advertises or requests it. |
| Paper-trading order engine | **not started** | Paper trading works by re-running the backtest engine over the session window and snapshotting the result (`trading/service.py:63-96`). There is no `Order` model, no state machine, no order id, no rejection path and no reconciliation. Audit §6.1. |
| ML lab | **not started** | No model training, no feature store, no labelling. `indicators/__init__.py:5` names a feature store as a consumer; it does not exist. |
| Model registry | **not started** | Nothing to register. |
| Drift monitoring | **not started** | Nothing to monitor. |
| OpenTelemetry | **not started** | `core/observability.py:1` says the full stack is a later phase. Today: Sentry (DSN-gated), structlog, and a token-gated Prometheus `/metrics`. No spans, no trace propagation. |
| Grafana dashboards | **partial** | The compose profile runs Prometheus, Loki, Promtail and Grafana (`infra/compose.prod.yaml:73-113`), Prometheus' scrape config is written and carefully documented (`infra/prometheus.yml`), and Grafana has a provisioned datasource. There is not one dashboard JSON in the repository. |
| Frontend modes / navigation | **partial** | Nine authenticated routes, three public ones, a grouped nav with an honestly-gated "Live Trading" entry, and a "Activity" label that refuses to promise a rule builder (`app-nav.tsx:21-44`). Missing: **no UI at all** for robustness, experiments, the AI copilot or the research graph, despite all four being mounted in the API (`main.py:127-130`). |
| Security | **done** | CSRF enforced at the single auth choke point (`auth/deps.py:47`), owner-scoped repositories that stamp ownership from the repo rather than input (`core/repository.py:38`), Nth-from-right trusted-proxy IP derivation (`ratelimit.py:63-87`), raw-ASGI body limit, fail-closed metrics guard, argon2id, encrypted broker credentials, AI token budgets, and a live gate that answers 403 by construction. |
| CI/CD | **done** | `.github/workflows/ci.yml`: ruff check + format, mypy under `disallow_untyped_defs`, `lint-imports`, migrations from scratch, OpenAPI drift guard, pytest with coverage, the AI evaluation gate, informational `pip-audit`/`npm audit`, plus a frontend job with the TS-types drift guard and a full-history gitleaks scan. |
| Documentation | **partial** | The v2 audits are thorough and the module docstrings carry most of the design rationale. But at least five docstrings and README lines now contradict the code (see §3, Phase 1) — and in a codebase that explains itself in docstrings, a stale docstring is a defect, not a cosmetic issue. |

**Summary count:** 30 areas — 13 `done`, 8 `partial`, 9 `not started`.

---

## 2. What is deliberately deferred, and why

Each of these is a decision, not an oversight. The justification has to survive being read back
in six months.

**ML lab.** The platform holds minute bars measured in days-to-weeks per instrument, backfilled
from free providers, across a five-symbol seeded universe. Supervised learning on a few hundred
to a few thousand bars per instrument, with a handful of features drawn from an eight-entry
indicator catalog, cannot produce a model whose out-of-sample performance is distinguishable from
noise — and the platform's own robustness lab would say so. Building it would be theatre: the
lab would correctly report `insufficient_evidence` on every run, and the honest response to that
is not to build the lab first. The prerequisite is Phase 2 (data you can trust) and enough
history for the existing `MIN_DAYS_FOR_ANNUALIZED = 180` floor to stop suppressing CAGR on
ordinary runs.

**Model registry and drift monitoring.** Both are downstream of an ML lab. Registering zero
models and monitoring zero deployed predictors is pure ceremony.

**OpenTelemetry.** Spans, context propagation and a collector are operational weight paid up
front against traffic that does not exist. The system runs as a single API process plus one ARQ
worker; a synchronous robustness suite completes in under a second per analysis; structlog plus
Sentry already answer "what failed and where". The signal that OTel has become worth its cost is
Phase 6's trigger: the lab moves off the request path and onto the queue, at which point a run's
latency is distributed across processes and log correlation stops being sufficient. Adding it
before then buys dashboards nobody reads.

**RAG / knowledge index.** The AI layer's job is translation into a closed DSL and narration of
numbers it was handed. Neither task benefits from retrieval: the indicator catalog is eight
entries and already passed to the model in the prompt (`prompts.py:82-87`), and narration is
deliberately constrained to a supplied evidence payload so grounding stays arithmetically
checkable (`grounding.py:1-22`). Retrieval would add an unverifiable input to a pipeline whose
entire value proposition is that every input is verifiable. A corpus worth indexing — the user's
own accumulated experiments and research notes — is a Phase 5 artefact, not a Phase 1 one.

**Paper-trading order engine.** Deferred to Phase 4 rather than never. Today's re-run-the-engine
design has a genuine property worth keeping: parity with the backtester is guaranteed by
construction rather than by test. An order state machine breaks that guarantee and must earn it
back with reconciliation tests. It is the right next step, but it is a step *after* the data
underneath it is trustworthy.

**Multi-tenant scale-out, microservices, real-money execution.** See §4 — these are non-goals,
not deferrals.

---

## 3. Sequenced next phases

Ordered so that the things which make existing claims *more true* come before the things that add
new claims. A phase is not started until the previous one's definition of done (§5) is met.

---

### Phase 1 — Make every existing claim checkable

**Goal.** Eliminate the gap between what the repository says about itself and what it does, and
give the half-wired capabilities a decision: wire them or delete them. This is the cheapest,
highest-leverage work available, because this codebase explains its architecture in docstrings —
so a docstring that lies is indistinguishable from a bug until someone reads the code.

**Deliverables.**

1. Fix the five documented contradictions catalogued in `TARGET_ARCHITECTURE.md` §14.40–44:
   - `backtesting/service.py:23-28` — `data_fingerprint` hashes every bar; say so, and drop the
     `DatasetSnapshot` forward reference or replace it with a concrete Phase 2 pointer.
   - `core/config.py:30-34` — `app_secret_key` is the approval-token HMAC key
     (`ai/graph/approval.py:75-77`). Document the rotation consequence.
   - `indicators/__init__.py:5`, `indicators/compute.py:34-36` — remove "the ML feature store"
     from the list of consumers.
   - `monte_carlo.py:16-23` and `robustness/__init__.py:19-20` — either implement
     `perturb_start` or remove it from both docstrings and replace it with `perturb_costs`,
     which exists and is undocumented in the header list.
   - `README.md:120-127` — move "Deflated-Sharpe / multiple-testing correction" and "an automatic
     in-sample/out-of-sample split" out of the not-claimed list; `README.md:69` — correct the
     `packages/contracts/` description (no generated client, no zod); `market_data/models.py:6` —
     `date_bin`, not `time_bucket`.
2. Wire or delete the dead code, with the choice recorded:
   - `Experiment.parent_id` — set it. A rerun invoked against an existing experiment links to it,
     which is what makes the append-only claim mean something.
   - `count_trials` / `by_fingerprint` — feed the researcher's own repeat-trial count into
     `assess_sharpe`'s `trials`, so deflation reflects how many times this question has been
     asked, not just the size of one grid (`experiments/repository.py:51-63`).
   - `benjamini_hochberg` — either surface it as a family-wise screen over sweep cells or delete
     it.
   - `purged_kfold` / `holdout` / `describe_splits` / `bars_as_of` — annotate each as a Phase 2/4
     prerequisite with the consuming surface named, or remove.
3. Build the narration evaluation runner so the 25 `grounding.json` cases stop being inert
   documentation: run `/ai/explain`'s pipeline against fixed evidence payloads and grade with
   `check_grounding` plus per-case assertions on unsupported numbers, predictive phrases and the
   disclosure line.
4. Add a **claim-drift guard** to CI: a test that asserts the constants and capability boundaries
   named in prose match the code — for example, that every indicator listed in the prompt's
   parameter table (`prompts.py:82-87`) exists in `INDICATOR_PARAMS`, that every path listed in
   the `overrides.py` module docstring is in `_SIMPLE_PATHS` or matches `_INDICATOR_PATH`, and
   that the `_reject_unsupported` rules and their error strings are pinned.

**Tests that would prove it.**
- The claim-drift test fails when someone adds an indicator to the catalog without updating the
  prompt table (and passes after).
- A rerun test asserts the second `Experiment` row carries the first's id as `parent_id`, and
  `lineage()` returns it.
- A deflation test asserts that running the same spec over the same data twice raises the
  effective trial count and lowers the deflated Sharpe.
- The narration eval runs in CI against the deterministic path and fails on a seeded case whose
  evidence payload omits a number the expected text cites.
- `grep` for `DatasetSnapshot`, "ML feature store" and `perturb_start` returns only Phase 2/5
  planning references.

**Risk retired.** The credibility risk. Every claim in this repository is currently checkable
except the ones that are wrong, and a reader who finds one wrong claim discounts all of them.
Secondarily: the deflation currently *understates* the multiple-testing problem, which is the one
direction it must not err in.

---

### Phase 2 — Trust the bars

**Goal.** Every number the platform produces rests on the OHLCV table, and that table currently
has no integrity checks and no corporate-action handling. An unadjusted split is not a data
quality nuisance — it is a fabricated 50% gap that the engine will happily trade, and the
robustness lab will report as a genuine edge that survives cost stress.

**Deliverables.**

1. **Validation at ingest.** Reject or quarantine bars failing: any non-finite value, any
   non-positive price, `high < max(open, close)`, `low > min(open, close)`, `high < low`, negative
   volume, or a timestamp not on a minute boundary. Failures are counted, logged with the vendor
   and the symbol, and surfaced on an ingestion health endpoint — never silently dropped.
2. **Database `CHECK` constraints** mirroring the same rules, so a bad row cannot arrive by any
   path including a manual insert.
3. **A repair path for immutable final bars.** Today `is_final` bars cannot be corrected by
   re-ingestion (`repository.py:133`), which is the right default and the wrong absolute. Add an
   explicit, audited correction operation that supersedes a final bar and records the supersession,
   so a known-bad bar is fixable without weakening the immutability guarantee for everything else.
4. **Corporate actions.** An `instrument_actions` table (split ratio, cash dividend, effective
   date, source), an adjustment applied at read time in `get_bars` rather than mutating stored
   bars, and the adjustment state recorded in the data fingerprint so an unadjusted run and an
   adjusted run over the same window are distinguishable.
5. **Dataset snapshots.** Give `data_fingerprint` a retrievable counterpart: a `DatasetSnapshot`
   row recording instrument, timeframe, window, bar count, the fingerprint and the adjustment
   state, referenced by `Experiment`. Reproducing a year-old experiment currently requires the
   bars to still be there and unchanged; a snapshot makes "the data has changed since this run"
   detectable rather than assumed.
6. **Real exchange calendars.** Replace the `{"XNYS": "America/New_York"}` constants
   (`engine.py:33`, `indicators/compute.py:76`) and the `252 × 390` annualization pair
   (`metrics.py:44-47`) with a calendar that knows holidays, half-days and early closes, and use
   it consistently for session anchoring, the `time_of_day` filter, annualization and the
   streaming session check (`market_data/streaming.py:26-28`).

**Tests that would prove it.**
- Property tests: no ingested bar can violate any OHLC ordering invariant; the DB rejects one
  inserted directly.
- A golden fixture: a known AAPL split date produces identical adjusted bars before and after the
  split when read with adjustment on, and the raw gap when read with it off.
- A fingerprint test: the same window read with and without adjustment yields different
  fingerprints.
- A calendar fixture: a Thanksgiving half-day produces the right session bar count, and
  `periods_per_year` for that year matches the calendar's actual session count rather than 252.
- A `time_of_day` test on an early-close day.
- A supersession test: correcting a final bar changes the fingerprint, is written to the audit
  log, and leaves every other final bar untouched.

**Risk retired.** The correctness risk that no amount of engine rigour can compensate for. The
engine is verified against hand-derived fixtures and a differential reference; none of that
matters if the bars are wrong. This phase is also a hard prerequisite for any ML work and for
extending history beyond the free providers' minute-bar window.

---

### Phase 3 — Ship the research workbench

**Goal.** The single largest capability gain in v2 — the robustness lab, the experiment record,
the NL compiler and the approval-gated research graph — has no user interface at all. Every
endpoint is mounted (`main.py:127-130`) and typed in the generated schema; none appears in
`app-nav.tsx`. This phase turns built capability into product.

**Deliverables.**

1. **Research copilot surface.** A request box calling `/ai/clarify` live (instant, free, no
   model call) so a user sees how their wording will be read before spending a slow local
   generation; then `/ai/strategy`, rendering the proposed spec alongside `applied_defaults`,
   `ambiguities` and `semantic_issues` as first-class content rather than footnotes. A semantic
   issue must be visually impossible to miss — it is the pipeline's most important output.
2. **The approval gate as a real screen.** `/research/propose` renders the plan, the dataset it
   will use, the incomplete-bucket count, and the analyses it will run; approving posts to
   `/research/execute` with the token. The screen must make clear that nothing has run yet.
3. **Robustness suite runner and report.** An axis builder constrained to the whitelisted paths
   (`overrides.py:35-46`) with the grid-size cap enforced client-side *and* explained; a report
   rendering the stability checklist with each check's verdict, threshold and evidence, the
   walk-forward fold table with in-sample and out-of-sample side by side, the cost-stress ladder,
   and the Monte Carlo distributions.
4. **The experiment log.** A list at `/experiments` showing kind, symbol, verdict, spec hash and
   data fingerprint; a detail view with the full provenance block and a "reproduce" panel.
   Lineage from Phase 1 renders as a tree.
5. **AI status surface.** `/ai/status` already reports the chain, each profile's circuit state,
   which local models are actually pulled, and actionable notes (`ai/router.py:123-175`). Surface
   it, so "the AI is slow today" has an answer in the product.
6. **Navigation.** A "Research" group in `app-nav.tsx` — Copilot, Robustness, Experiments — kept
   distinct from the existing "Trade" group.

**Tests that would prove it.**
- Frontend typecheck and the TS-types drift guard stay green with the new surfaces (no
  hand-written response types).
- A test asserting the axis builder cannot construct a request that the server would reject with
  `OverrideError` — the client-side bound and `MAX_AXES`/`MAX_VALUES_PER_AXIS`/`MAX_COMBINATIONS`
  are read from the generated schema, not duplicated.
- A rendering test that a `fail` verdict and a `warn` verdict are visually distinct from `pass`
  and from `insufficient_evidence` — the last of these is the one a UI is most tempted to render
  as a pass.
- An accessibility pass on the report tables (the existing suite already covers contrast).
- A test that the execute screen cannot be reached without a token, and that an edited spec
  produces the server's "issued for a different strategy" message rather than a generic 403.

**Risk retired.** The product risk of having built the most defensible part of the platform where
nobody can see it — and the correlated documentation risk of describing a workbench that a user
cannot use.

---

### Phase 4 — A real paper ledger

**Goal.** Give paper trading an order lifecycle. Today a session re-runs the whole engine over
`[session_start, now]` on each pass and snapshots the result (`trading/service.py:63-96`). That
guarantees backtest parity by construction, which is valuable, but it means there are no orders,
no positions as rows, no rejection path, and no way to answer "what did the system do at 14:32".

**Deliverables.**

1. **An `Order` model and state machine.** `pending → submitted → filled | partially_filled |
   cancelled | rejected | expired`, with the transition set enforced in code and every transition
   audited. Orders carry the bar that produced them and the reason.
2. **A `Position` projection** derived from filled orders rather than from a JSONB blob, so the
   desk's position is queryable and reconcilable.
3. **Incremental session runs.** Advance a session from its last processed bar rather than
   replaying from `session_start` every pass, with an explicit cursor. This removes the
   O(session length) recompute and makes a long-running session viable.
4. **Parity reconciliation.** Because incremental execution breaks the by-construction parity
   guarantee, replace it with a test: replaying a session incrementally must produce a
   trade-for-trade identical result to running the backtest engine over the same window.
5. **Cold-start honesty.** A session with fewer than two closed bars currently shows nothing with
   no explanation (`trading/service.py:79,93`). Report the reason and the expected time to the
   first bar.
6. **Alert rules.** With an order lifecycle there is something to alert on beyond snapshot diffs;
   keep the existing `(session_id, dedup_key)` idempotency guarantee (`trading/models.py:47-60`).

**Tests that would prove it.**
- A state-machine test enumerating every illegal transition and asserting it raises.
- The reconciliation test above, run over a multi-day window with stops, targets, a trailing stop
  and a time exit.
- A resume test: killing and restarting the worker mid-session produces the same final ledger.
- An idempotency test: two concurrent cron passes over the same session create one set of orders
  and one set of alerts.
- A cold-start test asserting the explanatory state is returned rather than an empty snapshot.

**Risk retired.** The simulation-fidelity risk. "Paper trading" currently means "a backtest that
keeps running", which is honest but limited: it cannot model an order that was rejected, a fill
that was partial, or a state that persisted across a restart — all of which are the things a
simulation is supposed to teach before real money is ever considered.

---

### Phase 5 — Comparison and accumulated evidence

**Goal.** Make a single result interpretable *relative to something*. The platform is rigorous
about whether a number is real and silent about whether it is good.

**Deliverables.**

1. **Buy-and-hold benchmark overlay.** Computed by the engine over the same bars, the same
   calendar and the same cost model, reported alongside every backtest and every walk-forward
   fold. Explicitly listed today as not claimed (`README.md:126`); it is the single most useful
   missing comparison.
2. **A non-zero risk-free rate.** `compute_metrics` already accepts one and de-annualizes it
   correctly (`metrics.py:93,159-160`); no caller passes it. Source it per period and record the
   value used on the result, so a Sharpe stops silently meaning "excess over zero".
3. **Cross-experiment comparison.** Given a set of experiments, show the metrics side by side with
   spec hashes and data fingerprints, and refuse to compare runs whose fingerprints or
   `metrics_version` differ without saying so loudly.
4. **A research notebook surface** over the experiment record: hypothesis, tags, notes (all three
   fields exist and none has a write path today), so a user's own history becomes the corpus.
5. **Trial accounting across a session**, building on Phase 1: the deflation reflects everything
   the researcher tried against this spec, and the UI says how many trials the number was
   corrected for.

**Tests that would prove it.**
- A golden fixture: a strategy that returns 8% over a window where buy-and-hold returned 25%
  reports both, and the stability checklist is unaffected (the benchmark is context, not a check —
  unless a check is deliberately added, in which case it gets its own threshold and evidence).
- A test that a comparison across differing `metrics_version` values is refused or badged.
- A test that the reported trial count matches the number of completed experiments against that
  spec hash.

**Risk retired.** The interpretation risk: a positive total return with a passing stability
verdict currently looks like a good result even when the instrument doubled over the same period.

---

### Phase 6 — Operate it

**Goal.** Move the expensive work off the request path and make the system observable, at the
point where its own growth makes that necessary rather than pre-emptively.

**Deliverables.**

1. **Asynchronous robustness runs.** Move `run_suite` onto the existing ARQ worker behind an
   experiment id, using the same seam paper trading already uses (`robustness/router.py:1-8`).
   The `Experiment` row already has a `running` status and a `completed_at`, so the state model
   exists.
2. **Shared circuit-breaker state.** The breaker is per-process and in memory by design
   (`circuit.py:21-23`); with more than one API worker each rediscovers a dead provider
   independently. Add an optional shared backend with the in-memory one as the fallback, so the
   resilience mechanism never *depends* on Redis being up.
3. **OpenTelemetry** on the two things worth tracing: an engine run (bars, trades, duration, spec
   hash) and an AI call (profile, prompt id, tokens, latency, routing decisions, repair count).
   Trace ids correlate with the existing `X-Request-ID` and the graph's `stage_log`.
4. **Grafana dashboards, committed as JSON.** Ingestion lag and gap counts per instrument;
   experiment throughput and verdict distribution; AI profile latency, token spend against the
   daily budgets, and circuit-breaker state; API latency and error rate by route group.
5. **Backup and restore verification in CI**, not just in a script. `infra/backup.sh` and
   `infra/restore.sh` exist and were never run in the baseline verification
   (`BASELINE_VERIFICATION.md:22-34`).

**Tests that would prove it.**
- A queued suite returns an experiment id immediately, and the row transitions
  `running → done` with the same payload the synchronous path produced (a byte-comparison test
  against a fixture).
- A breaker test with two simulated processes: a provider that fails three times in process A is
  skipped by process B.
- A trace assertion: one strategy generation produces one root span with the expected child spans
  and no prompt text, credential or model reasoning in any attribute.
- A restore drill in CI: dump, restore into a scratch database, run migrations to head, and assert
  a known row survives.

**Risk retired.** The operational risk, at the point where it becomes real: a lab run that
monopolises an API process, a provider outage rediscovered N times, and an unverified backup.

---

## 4. Explicit non-goals

These are not deferred. They are outside what this platform is for, and code that assumes
otherwise should be rejected in review.

**Real-money order execution.** The live seam exists to *prove the gate*, not to become an
execution venue (`trading/live_router.py:1-5`). Opening it would require a control stack that is
deliberately unbuilt — 2FA, explicit opt-in, step-up authentication, a kill switch, order
confirmation and enforced risk limits (`live_gate.py:24-38`) — plus regulatory posture,
custody, and an operational on-call story this project does not have. `POST /live/orders` answers
403 by construction and should continue to.

**Autonomous trading.** No scheduled agent that decides and acts. The research graph halts at a
human approval gate bound to specific content, and that gate is the product, not an obstacle to
route around (`ai/graph/approval.py:1-18`).

**Guaranteed or predicted performance.** Requests phrased as guarantees are refused before a
model call (`compiler.py:80-84`); narration is forbidden from projecting forward and is checked
for predictive language (`grounding.py:48-54`); every result carries a hypothetical-performance
disclosure (`robustness/service.py:248-252`, `ai/graph/tools.py:292-296`). No roadmap item may
weaken any of these.

**Multi-tenant SaaS scale-out.** `owner_id` is a tenancy *seam*, not a finished SaaS: there is no
billing, no organizations, no RBAC, no per-tenant quota beyond the AI token budget, and no data
residency story (ADR-0005, `README.md:85-87`). Building toward multi-tenancy would mean paying
for isolation guarantees nobody has asked for while the single-user product is unfinished.

**Microservices.** The modular monolith with an enforced import-linter DAG (ADR-0001,
`pyproject.toml:110-140`) delivers what service boundaries are usually reached for — enforced
module boundaries, independent testability, a clear dependency direction — with none of the
distributed-systems cost. The layered contract is green with zero waivers; that is the boundary
enforcement, and it is checked on every commit.

**A visual drag-and-drop strategy builder.** Strategies are one canonical JSON spec (ADR-0008).
The landing copy previously claimed a visual builder and the audit flagged it (`FE-03`/`FE-04`,
ranked #15). A form over the DSL is in scope; a node graph implying more expressiveness than the
DSL has is not.

---

## 5. Definition of done, per phase

A phase is done when every row below is objectively true. "Objectively" means a command, a test
name, or a file that exists.

### Phase 1 — Make every existing claim checkable

- [ ] `grep -rn "DatasetSnapshot\|ML feature store\|perturb_start" apps/api/app` returns nothing
      except a Phase 2/5 planning reference that names the phase.
- [ ] `README.md` contains no claim contradicted by the code; specifically the not-claimed list no
      longer includes deflation or out-of-sample splits, and `packages/contracts/` is described as
      an OpenAPI document only.
- [ ] Every function in `robustness/splits.py`, `robustness/multiple_testing.py` and
      `market_data/repository.py` is either called by a product surface or carries a one-line
      comment naming the phase that will call it.
- [ ] A rerun sets `parent_id`; a test asserts `lineage()` returns the child.
- [ ] `assess_sharpe`'s trial count includes prior completed experiments against the same spec
      hash; a test asserts the deflated Sharpe falls as trials accumulate.
- [ ] The narration evaluation runner exists, runs the `grounding` category, and is part of the CI
      evaluation command.
- [ ] A claim-drift test exists and demonstrably fails when the indicator catalog and the prompt's
      parameter table diverge.
- [ ] Full CI green, including `lint-imports` with no `ignore_imports`.

### Phase 2 — Trust the bars

- [ ] No bar can be written that violates OHLC ordering, positivity or finiteness — enforced in
      code **and** by a database `CHECK`; a test inserts a bad row directly and gets an
      `IntegrityError`.
- [ ] An ingestion health surface reports rejected-bar counts per instrument per source.
- [ ] A split-adjusted read of a known corporate action matches a hand-derived golden fixture, and
      the unadjusted read reproduces the raw gap.
- [ ] `data_fingerprint` incorporates adjustment state; a test asserts adjusted and unadjusted
      windows fingerprint differently.
- [ ] `DatasetSnapshot` exists, is referenced by `Experiment`, and a test detects "the data behind
      this experiment has changed".
- [ ] Correcting a final bar is possible only through the audited supersession path; a test
      asserts a plain re-ingest is still a no-op.
- [ ] `periods_per_year` for a given year matches that exchange calendar's actual session count;
      a half-day fixture passes for session anchoring, the `time_of_day` filter and annualization.

### Phase 3 — Ship the research workbench

- [ ] A user can go from a plain-English request to an approved, executed robustness suite and a
      rendered report without leaving the web app.
- [ ] `app-nav.tsx` contains a Research group; every endpoint under `/ai/*`, `/research/*`,
      `/robustness/*` and `/experiments` is reachable from the UI or explicitly documented as
      API-only.
- [ ] No response type in `apps/web/src/lib/api/` is hand-declared; the TS-types drift guard is
      green.
- [ ] Semantic issues, applied defaults and `insufficient_evidence` verdicts each have a distinct
      visual treatment, verified by a rendering test.
- [ ] The execute path rejects an edited spec with the server's specific message, verified
      end-to-end.
- [ ] `npm run lint`, `npm run typecheck` and `npm run build` are green.

### Phase 4 — A real paper ledger

- [ ] An `Order` table exists with an enforced transition set; every illegal transition has a
      failing test.
- [ ] Incremental session replay is trade-for-trade identical to a backtest over the same window,
      asserted over a window containing a stop, a target, a trailing exit and a time exit.
- [ ] A worker restart mid-session yields an identical final ledger.
- [ ] Two concurrent cron passes produce one set of orders and one set of alerts.
- [ ] A session with insufficient bars returns an explanatory state, not an empty snapshot.
- [ ] Coverage on `app/modules/trading/` is materially above the baseline's 0% on worker paths
      (`BASELINE_VERIFICATION.md:22-34`).

### Phase 5 — Comparison and accumulated evidence

- [ ] Every backtest and every walk-forward fold reports a buy-and-hold figure computed under the
      same costs and calendar.
- [ ] The risk-free rate used is recorded on the result; a Sharpe never silently means
      "excess over zero".
- [ ] Comparing experiments with differing `metrics_version`, `engine_version`,
      `cost_model_version` or `data_fingerprint` is refused or badged, with a test.
- [ ] `hypothesis`, `tags` and `notes` all have write paths and appear in the UI.
- [ ] The reported trial count matches `count_trials` for that spec hash, with a test.

### Phase 6 — Operate it

- [ ] `POST /robustness/suite` returns an experiment id immediately; a byte-comparison test shows
      the queued result matches the synchronous one.
- [ ] A dead provider discovered by one process is skipped by another, with a test.
- [ ] One strategy generation emits one root span with the expected children, and an attribute
      assertion proves no prompt text, credential or model reasoning is exported.
- [ ] At least four Grafana dashboards are committed as JSON under `infra/grafana/` and
      provisioned.
- [ ] A CI restore drill dumps, restores into a scratch database, migrates to head and asserts a
      known row survives.

---

## Appendix: how to keep this document honest

This roadmap will be wrong within weeks unless it is regenerated from the code. The mechanism
that makes that cheap already exists: the status table's evidence column is a set of file and line
references, and the Phase 1 claim-drift test is the beginning of enforcing the same discipline on
prose. When a phase completes, move its rows to `done` **and** update `TARGET_ARCHITECTURE.md`
§14, which is the list this roadmap is derived from. If §14 shrinks and this table does not, one
of the two is lying.

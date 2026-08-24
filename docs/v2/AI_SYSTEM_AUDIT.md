# AI System Audit — TradePulse (pre-v2)

**Date:** 2026-08-21 · **Scope:** the AI layer only — `apps/api/app/modules/ai/**`, its
configuration, its deployment surface, its tests, and every claim made about it in
`README.md`, `docs/`, and the web UI.

**Method.** Every file under `apps/api/app/modules/ai/` was read in full (`__init__.py`,
`router.py`, `schemas.py`, `service.py`, `budget.py`, `prompts.py`,
`providers/{__init__,base,factory,gemini,ollama}.py`), together with
`apps/api/tests/test_ai.py`, the AI block of `apps/api/app/core/config.py`, `.env.example`,
`Dockerfile`, `render.yaml`, `infra/.env.prod.example`, `infra/compose.prod.yaml`,
`pyproject.toml` (import-linter contracts), `.github/workflows/ci.yml`,
`packages/contracts/openapi.json`, ADR-0002 and ADR-0008, and every frontend call site
(`apps/web/src/lib/api/client.ts`, `strategies/strategies-view.tsx`,
`components/backtest-results.tsx`, `app/methodology/page.tsx`, `app/page.tsx`,
`dashboard/dashboard-view.tsx`). Findings were re-verified against the code a second time;
claims that did not survive that pass are listed in §14 and are **not** asserted anywhere
above it.

**Tree state.** This audit reads the **working tree**, not the baseline commit. `git status`
at the time of reading shows uncommitted v2-in-progress work: the indicator catalog has been
extracted into `apps/api/app/modules/indicators/catalog.py`, the composition surfaces moved
into `apps/api/app/modules/research/`, and `StrategySpec` gained a hard capability gate
(`apps/api/app/modules/strategies/spec.py:206-245`). **No file under
`apps/api/app/modules/ai/` is modified**, which is itself the source of the highest-severity
new finding in this document (AI-22). Nothing was executed and no file was modified while
producing this audit.

The tree is also being edited concurrently by other v2 workstreams. Every citation outside
`apps/api/app/modules/ai/**` was re-verified against the tree immediately before this document
was finalised; the AI module's own files were unmodified throughout. Two AI-adjacent claims
were corrected in the UI *while this audit was being written* — they are recorded as resolved
in §11 rather than as findings.

---

## 1. Verdict

The AI layer is small (~370 lines across 9 files), correctly isolated, and safe in the one way
that matters most for a trading product: **it cannot place an order and it cannot execute
code**, and that property is structural rather than aspirational (§2). The validate-and-repair
loop and the closed DSL it targets are the right shape for "an LLM writes a strategy" (§5).

Everything else is thinner than the surrounding documentation implies. There is no provider
router, no health check, no retry, no fallback, no circuit breaker; no prompt registry or
versioning; no evaluation dataset of any kind; and **no per-call record of tokens, latency,
cost, model, or outcome** — so there is no data from which quality or spend could be measured
at all. The narration endpoint narrates whatever JSON the client posts. The token budget is a
non-reserving pre-check. And in the current working tree the hand-written DSL guide now
actively contradicts the validator it is meant to satisfy.

| Dimension | State |
|---|---|
| Safety (no order placement, no code execution) | **Strong** — structurally enforced, §2 |
| Structured-output validation + repair | **Good** — bounded, fails closed, §5 |
| Prompt ↔ schema consistency | **Broken in the working tree** — AI-22, §4.2 |
| Provider abstraction / routing / resilience | **Absent** — §3.1 |
| Local-model support | **Nominal only** — §3.2 |
| Narration grounding | **Prompt-level only, unverified server-side** — §6 |
| Budget / cost control | **Advisory** — §8 |
| Observability (tokens, latency, cost, versions) | **None** — §9 |
| Evaluation coverage | **None** — §10 |
| Data-egress disclosure | **Operator docs yes, product surface no** — §7 |

---

## 2. Safety: no order placement, no code execution (verified paths)

This is the strongest part of the module and should be preserved through v2.

| Property | Verification |
|---|---|
| AI never reaches execution code | `apps/api/app/modules/ai/service.py:14-18` imports only `app.core.errors`, `app.core.logging`, `app.modules.ai.{budget,prompts}`, `providers.base`, and `strategies.spec`. No import of `trading`, `backtesting`, or `live` anywhere in the module. |
| Nothing depends on the AI module | Grep for `modules.ai` outside `apps/api/app/modules/ai/` returns exactly one production hit: `apps/api/app/main.py:30` (router import, mounted at `main.py:124`). Test-only hits: `apps/api/tests/test_ai.py:13-15,88`. |
| No code execution | Grep for `eval(`, `exec(`, `subprocess`, `os.system`, `importlib` across `apps/api/app/modules/ai/` returns nothing. There is no free-form expression DSL — conditions are a closed algebraic tree (`apps/api/app/modules/strategies/spec.py:60-96`). |
| No tool use / function calling | Both providers send a plain text prompt: `providers/gemini.py:30-34` (`system_instruction` plus one user part) and `providers/ollama.py:22-30`. Neither sends tool or function declarations. |
| AI cannot write to the database | `AIService.__init__` takes a provider and a Redis handle only — no DB session (`service.py:34-37`). The generated spec is returned to the client and must be re-validated by Pydantic on `POST /strategies` (`apps/api/app/modules/strategies/router.py:25-30`). |
| No background AI path | `apps/api/app/worker.py:106-113` registers `heartbeat`, `ingest_backfill`, `poll_quotes`, `run_paper_sessions`. There is no AI job and no AI cron. |
| Human-in-the-loop is real, not decorative | `strategies-view.tsx:57-62` writes the returned spec into an editable textarea; persistence requires a separate explicit click (`strategies-view.tsx:77`, button at `:136`). |
| Structural guard | The import-linter layer contract (`pyproject.toml:112-133`) places `app.modules.ai` at the top layer with **no sanctioned exceptions**, so any future upward edge into AI fails CI. |

The claim `"No AI code path can place an order."` (`apps/api/app/modules/ai/__init__.py:6`) is
**accurate**, as is "generates a validated strategy spec from plain English — and never
auto-executes it" (`apps/web/src/app/methodology/page.tsx:86`).

One caveat on the structural guard: `lint-imports` is recorded as failing at the baseline
commit (`docs/v2/BASELINE_VERIFICATION.md` §4.2). The violations recorded there are
`market_data → strategies` / `market_data → backtesting` edges; **none involve
`app.modules.ai`**. Whether the working tree's restructure clears the contract is a matter for
the Baseline Verification section, not asserted here.

---

## 3. Provider layer

### 3.1 Abstraction, routing, resilience — AI-05 (medium)

`LLMProvider` (`providers/base.py:24-30`) is a two-member Protocol: `name: str` and
`generate(...)`. `LLMResponse` (`providers/base.py:11-21`) carries `text`, `tokens_in`,
`tokens_out`, `model`, `provider` — and nothing else.

| Missing from the contract | Consequence |
|---|---|
| `model` on the protocol (only on the concretes) | Callers cannot read the model without narrowing to a concrete class. |
| Capability flags (JSON mode, context window) | `json_mode=True` is passed blind (`service.py:49`); a provider that ignores it fails silently into the repair loop. |
| Cost per token | Cost cannot be computed anywhere in the system. |
| `latency_ms` | Not measured (§9). |
| `health()` | No probe exists; failure is discovered only by a user request. |
| `timeout` | Hardcoded per provider: 60 s (`gemini.py:36`), 120 s (`ollama.py:31`). |

`make_llm_provider` (`providers/factory.py:12-18`) is a two-branch dispatch on a plain string
with a terminal `raise`. There is **no ordered fallback chain, no retry, no backoff, no health
gate, and no circuit breaker** — a grep across `apps/api` for `tenacity`, `backoff`, `retry`,
or `breaker` returns nothing. If Gemini is down or misconfigured, `/ai/strategy` fails; the
Ollama provider sitting beside it is never tried. The docstrings over-promise on exactly this
point: `providers/__init__.py:1` and `providers/ollama.py:1` both describe Ollama as a
"fallback", and no fallback logic exists.

`@runtime_checkable` at `providers/base.py:24` is dead decoration — nothing calls
`isinstance`/`issubclass` against `LLMProvider`, and because the Protocol has a non-method
member (`name: str`, `base.py:26`) `issubclass()` would raise `TypeError` if anything tried
(**AI-20**, low).

The real per-request cost is HTTP client construction, not provider construction:
`GeminiProvider.__init__` (`gemini.py:18-22`) only stores two strings, but `gemini.py:36` and
`ollama.py:31` each open a fresh `httpx.AsyncClient` — a new connection pool plus TLS
handshake — on **every** `generate()`, multiplied by up to three per request by the repair
loop (`service.py:46-59`).

Highest-value fixes in order: (1) reuse a lifespan-scoped `httpx.AsyncClient`; (2) add an
ordered fallback chain with retry-and-jitter; (3) then capabilities/`health()` on the protocol
and `latency_ms`/`cost_usd` on `LLMResponse`. Caching provider *instances* is not worth doing.

### 3.2 Local-model support is nominal — AI-06, AI-07 (medium)

| Evidence | Effect |
|---|---|
| `providers/ollama.py:15` hardcodes `model: str = "llama3.1"` | Running any other local model requires a code edit. |
| `providers/factory.py:17` calls `OllamaProvider(settings.ollama_base_url)` with no model | The hardcoded default is always used, regardless of what the operator pulled. |
| `apps/api/app/core/config.py:76-79` defines `gemini_api_key`, `gemini_model`, `ollama_base_url`, `ai_default_provider` — **no** `ollama_model`; `.env.example:62-68` likewise | No configuration surface exists for the local model. |
| `Dockerfile:27`, `render.yaml:27-28`, `infra/.env.prod.example:35` all pin `AI_DEFAULT_PROVIDER=gemini` | Every shipped target defaults to the remote provider. |
| `infra/.env.prod.example:36` sets `OLLAMA_BASE_URL=http://localhost:11434` | Inside the API container that resolves to the container's own loopback, not the host. |
| `infra/compose.prod.yaml` defines `db, redis, api, worker, web, caddy, prometheus, loki, promtail, grafana` — no `ollama` service | The local path is unreachable in the compose deployment. |

`README.md:37` offers "a local Ollama model" as a co-equal option. In practice it is a
dev-machine-only escape hatch that no test and no deployment exercises. Either add an `ollama`
service (or document `host.docker.internal`) and make it the default, or mark the path
dev-only in `README.md` and `.env.example`.

### 3.3 No selectable fake provider — AI-13 (medium)

`FakeProvider` exists only inside the test module (`apps/api/tests/test_ai.py:21-33`) and
cannot be selected through configuration; `providers/factory.py:12-18` accepts only `gemini`
and `ollama`. Consequences: CI never executes the factory; a keyless local run gets an error
from `GeminiProvider.__init__` (`gemini.py:19-20`); and a demo deployment without a key has no
working AI path. Shipping `providers/fake.py`, selectable as `AI_DEFAULT_PROVIDER=fake`, is a
prerequisite for the eval work in §10 — per `docs/v2/BASELINE_VERIFICATION.md` §5, this
machine has no local LLM runtime at all.

### 3.4 Configuration typing — AI-18 (low)

`ai_default_provider: str = "gemini"  # gemini | ollama` (`apps/api/app/core/config.py:79`) —
the allowed set lives in a comment. `AI_DEFAULT_PROVIDER=openai` boots cleanly and produces a
generic 500 on the first user request (`factory.py:18`). Every other constrained setting in
that file uses `Literal` (e.g. `app_env`, `config.py:24`).

### 3.5 Error handling on the provider boundary — AI-15 (medium)

| Site | Behaviour | Should be |
|---|---|---|
| `providers/ollama.py:33` | `resp.raise_for_status()` — `httpx.HTTPStatusError` is not an `AppError`, so it reaches the catch-all (`core/errors.py:104-107`) as an opaque 500. `httpx.ConnectError` (Ollama not running — the normal case) does the same. | Map connect/timeout/status to a 503-class `AppError` with a neutral message. |
| `providers/gemini.py:19-20` | A missing key raises bare `AppError`, whose base `status_code` is 500 (`core/errors.py:25-27`), rendering `"GEMINI_API_KEY is not configured."` to the client. | 503 with a non-leaky message. |
| `providers/gemini.py:40-41` | Non-200 collapses to `f"Gemini request failed ({resp.status_code})."`; the response body is discarded and nothing is logged. | Log the upstream body server-side; classify permanent vs transient. |
| `providers/gemini.py:47-48` | `finishReason` is never inspected, so a `MAX_TOKENS` truncation is indistinguishable from invalid JSON and burns a repair attempt. | Inspect `finishReason`; fail fast on truncation. |
| `providers/gemini.py:27-29` | `generationConfig` carries only `temperature` (plus `responseMimeType` in JSON mode) — no `maxOutputTokens`, no `safetySettings`. | Set an explicit output cap (see §8). |

`docs/v2/BASELINE_VERIFICATION.md` §4.3 records this pattern reaching a user: a permanent
`API_KEY_INVALID` from Gemini surfaced as `500 {"detail":"Gemini request failed (400)."}`, with
the upstream message discarded before any log.

---

## 4. Prompt structure, versioning, and drift

### 4.1 Structure

Three static strings plus two builders, all in `apps/api/app/modules/ai/prompts.py`:

| Artifact | Lines | Role |
|---|---|---|
| `STRATEGY_SYSTEM` | `prompts.py:12-18` | Role, "output ONLY the JSON object", mandatory `exit`/`sizing`/`risk`, catalog-only indicators, non-advice framing. |
| `DSL_GUIDE` | `prompts.py:20-48` | Hand-written prose restatement of the DSL. |
| `NARRATION_SYSTEM` | `prompts.py:50-55` | "Use ONLY the numbers present … never invent"; must end with an exact disclaimer string. |
| `build_strategy_prompt` | `prompts.py:58-68` | `[DSL_GUIDE, worked example, "User request: {nl}"]`, plus a repair block when `errors` and `last_output` are set (`:63-67`). |
| `build_explain_prompt` | `prompts.py:71-72` | `"Backtest results (JSON):\n" + json.dumps(context, ...)`. |

The worked example is generated by calling `example_composite_spec()` from the spec module
(`prompts.py:61`), so the *example* can never drift from the schema — a genuinely good choice
worth keeping.

### 4.2 AI-22 (high) — the DSL guide now contradicts the validator it targets

The working-tree hardening at `apps/api/app/modules/strategies/spec.py:206-245`
(`_reject_unsupported`) converts four previously accepted-then-silently-ignored constructs into
hard `ValueError`s. `DSL_GUIDE` was not updated, and still instructs the model to produce three
of them:

| `DSL_GUIDE` says | The validator now does | Result |
|---|---|---|
| `prompts.py:29` — "entry_short: Condition (optional)" | `spec.py:225-228` raises: engine 0.1.0 is long-only | Any "short X" request follows the guide, fails validation three times (`service.py:46-59`), and returns `400 "Could not produce a valid strategy from that prompt; rephrase it."` |
| `prompts.py:24` — `universe: [symbol]`, no stated cardinality limit | `spec.py:230-235` raises when `len(universe) > 1` | Multi-symbol requests fail rather than silently truncate. |
| `prompts.py:33-34` — `risk: {max_position_pct (0-1), max_open_positions, …}` with no value constraint | `spec.py:236-240` requires `max_open_positions == 1` | A plausible `2` fails validation. |
| `prompts.py:32` — `sizing: {method: … risk_per_trade …}` with no coupling stated | `spec.py:241-245` requires `exit.stop_loss_pct` when `method="risk_per_trade"` | Fails unless the model happens to emit a stop. |

The spec hardening itself is correct and well-reasoned — its docstring (`spec.py:207-224`)
explains precisely why silently accepting and dropping a field is the worst failure mode a
research tool can have. The defect is that the AI's only description of the DSL is a
hand-maintained prose copy with no drift guard, so the copilot now instructs the model to emit
specs the platform refuses. Each such request costs three provider calls and returns an error
that names neither the offending field nor the reason.

This is the cheapest fix in this document: four lines of prose in `DSL_GUIDE`, plus the CI
generation guard described next.

### 4.3 AI-10 (medium) — no registry, no version, no drift guard

- `prompts.py` contains no version constant, no prompt id, and no changelog. A prompt edit is
  an undifferentiated code change, and nothing records which prompt produced which output (§9),
  so no behaviour change can ever be attributed to a prompt change.
- `DSL_GUIDE` (`prompts.py:20-48`) restates by hand what now lives in
  `apps/api/app/modules/indicators/catalog.py:20-49`. The indicator *names* still match
  (`catalog.py:20-29` against `prompts.py:27-28`), but the guide omits **every numeric
  constraint the validator enforces**: `RSI.period >= 2`, `BBANDS.period >= 2`,
  `BBANDS.std` in `[0.1, 10]` (`catalog.py:34-43`), and `percent_equity` / `risk_per_trade`
  value in `(0, 1]` (`spec.py:129-130`). Out-of-range guesses are caught only by a full repair
  round-trip.
- The CI drift guard (`.github/workflows/ci.yml:54-57`) covers `packages/contracts/openapi.json`
  only. Nothing regenerates or compares the prompt.
- ADR-0008 states that "the AI tool-use target … consume[s] the generated artifact"
  (`docs/adr/0008-one-canonical-strategyspec.md:9`). Neither half is true today: the AI consumes
  a hand-written prose guide, and no provider uses tool-use or function calling (§2). AI-22 is
  the direct cost of that divergence.

---

## 5. NL → StrategySpec: structured output, validation, repair

### 5.1 What the loop does

`AIService.generate_strategy` (`service.py:39-59`):

1. `budget.check` once, before the loop (`service.py:43`).
2. Up to `max_repairs + 1 = 3` iterations (`service.py:46`): build prompt →
   `provider.generate(..., json_mode=True)` → `budget.record` → `_strip_fences` →
   `json.loads` → `StrategySpec.model_validate`.
3. On `JSONDecodeError`/`ValidationError`: carry `str(exc)[:2000]` and `resp.text[:4000]` into
   the next prompt (`service.py:55-57`, rendered at `prompts.py:63-67`), and log
   `ai_strategy_repair` (`service.py:58`).
4. Exhausted → `BadRequestError` (`service.py:59`) — it **fails closed**; no half-valid object
   is ever returned.

This is the right shape. Re-prompting with the *concrete* validator error rather than a generic
"try again" is what makes single-shot repair work, and the bounded loop plus fail-closed exit
prevents unbounded spend on a hopeless prompt. JSON mode is requested per provider —
`responseMimeType: application/json` (`gemini.py:28-29`) and `format: json`
(`ollama.py:29-30`) — so the purely syntactic failure rate should be low in practice.

The DSL it targets is what makes this survivable at all: `extra="forbid"` on every model, a
closed indicator catalog, mandatory exit/sizing/risk (`spec.py:107-118`), and a canonical hash
for reproducibility (`spec.py:246-252`).

### 5.2 AI-19 (low) — fence stripping is boundary-only

`_strip_fences` (`service.py:23-31`) requires the text to *start* with a fence. Leading prose
("Here's your spec:") defeats it and costs a full extra provider call. The single test uses a
perfectly fenced payload (`tests/test_ai.py:54-59`). Extract the first balanced JSON object
instead.

### 5.3 AI-14 (medium) — validation is syntactic and schema-level only; no semantic pass

`service.py:53-54` checks that the output is a well-formed `StrategySpec`. Nothing checks that
it is the *requested* strategy or that it is runnable on this platform:

- **No intent diff.** A request for "short TSLA on RSI > 70" that comes back as a long BTC/USD
  EMA cross validates and is returned without comment. (With AI-22 present the short half now
  fails instead — but for the wrong reason and with an unhelpful message.)
- **No symbol resolution.** `universe` entries are never checked against the instrument catalog
  at generation time or at `POST /strategies` time; a hallucinated ticker surfaces much later
  as a 404 at backtest time (`apps/api/app/modules/backtesting/service.py:38-41`).
- **No economic sanity bounds.** `take_profit_pct` has no upper bound (`spec.py:102`), and
  `stop_loss_pct` may be `1e-9` (`spec.py:101` — only `gt=0, le=1`). `time_exit_bars=1` on a
  `4h` timeframe is accepted.
- **No warnings channel.** `GenerateStrategyResponse` is `{spec, provider}`
  (`schemas.py:16-18`); there is nowhere to return "the model chose BTC/USD but you said TSLA".

*Superseded in part:* an earlier form of this finding held that a multi-symbol universe is
"silently truncated to `universe[0]`". In the working tree that is no longer true —
`spec.py:230-235` rejects it outright. The remaining defects above are unchanged.

---

## 6. Narration, grounding, and hallucination controls

### 6.1 AI-01 (medium) — `/ai/explain` narrates an unconstrained client-supplied dict

`ExplainRequest.context: dict[str, Any]` (`schemas.py:22`) has no schema, no key allowlist, and
no size cap. The published contract confirms it: `ExplainRequest.context` is
`{"type": "object", "additionalProperties": true}` with no further constraints
(`packages/contracts/openapi.json`). The value flows `router.py:36` → `service.py:61-70` →
`prompts.py:71-72`, where it is `json.dumps`ed into the user turn. **`AIService` holds no DB
session** (`service.py:34-37`), so nothing ties the narrated numbers to a stored, owner-scoped
backtest.

The honest characterisation:

- The grounding instruction is real (`NARRATION_SYSTEM`, `prompts.py:50-55`) but is
  **unverifiable server-side** — "the numbers actually present in a result" means, on the
  server, "whatever JSON you posted".
- **This is not an authorization vulnerability.** Both endpoints are auth-gated
  (`router.py:24,33`), and the explanation is ephemeral client state
  (`backtest-results.tsx:94,164`) — never persisted, never shown to another user. A caller who
  posts fabricated metrics fools only their own screen.
- The concrete server-side defect on the same line is **cost and availability**: with
  `max_request_bytes = 2_000_000` (`core/config.py:57`) as the only bound and `budget.check` a
  non-reserving pre-check (`budget.py:30-34`), a single user can burn the 5 M-token global daily
  budget (`budget.py:14`) in roughly ten oversized requests. See §8.
- The raw `json.dumps` into the user turn is also an **unfiltered prompt-injection channel**
  (§6.3).

On the surrounding copy: `apps/web/src/app/methodology/page.tsx:87` is correctly hedged — "are
**instructed** to use only the numbers actually present" — and is not itself false. The two UI
strings that previously asserted grounding unconditionally ("grounded in your data" on the
dashboard, "Grounded explanations of every result" on the landing page) were rewritten in the
working tree during this audit and no longer appear (§11). The server-side finding is unaffected
by that copy change: the property is still asserted nowhere it can be checked.

**Fix:** take a `backtest_id`, load the row under owner scoping, and build the context
server-side from the DB — the pattern every other module already uses. If a free-form path must
remain, cap `context` bytes and allowlist keys.

### 6.2 AI-09 (medium) — the "every response ends with a not-investment-advice note" claim is unenforced

| Claim | Location | State |
|---|---|---|
| "Every response carries the non-advice framing in its text" | `apps/api/app/modules/ai/router.py:5` | **Still overclaims** |
| "always closes with a not-investment-advice note" | `README.md:91` | **Still overclaims** |
| "Every AI response ends with a not-investment-advice note" | `apps/web/src/app/methodology/page.tsx` | **Corrected in the working tree** — `:88` now reads "That is a prompt instruction, not a server-side guarantee — we do not currently append it if the model omits it." |

Reality: `explain_backtest` returns `resp.text.strip()` with no post-check and no append
(`service.py:70`), and `/ai/strategy` returns `{spec, provider}` — a JSON object containing no
note at all (`schemas.py:16-18`). Compliance rests entirely on the model obeying
`prompts.py:54`. The UI renders the narration in a plain bordered box with no AI-generated
label and no disclaimer (`backtest-results.tsx:255-261`); the hypothetical-performance banner
elsewhere on that page is about backtests, not AI output.

The methodology page's new wording is the honest short-term move and should stay until the
behaviour changes. The remaining work is to make the claim true rather than to keep hedging it:
append the disclaimer server-side (or assert-and-repair), fix `router.py:5` and `README.md:91`
in the meantime, and label AI output in the UI.

### 6.3 Prompt-injection surface

What is verifiable from the code:

- `build_explain_prompt` (`prompts.py:71-72`) concatenates a fully client-controlled dict into
  the user turn with no delimiter, no escaping, and no "treat the following as data" preamble.
- `build_strategy_prompt` does the same with user text: `f"User request: {nl}"`
  (`prompts.py:62`).
- No output post-check exists on either path (`service.py:54`, `service.py:70`).

What bounds the blast radius, and why this is not rated higher:

- The strategy path's output is hard-validated against a closed schema (`service.py:53-54`), so
  an injection can at most steer *which valid spec* comes back — and the user reviews it in a
  textarea before anything is saved (§2).
- `GenerateStrategyRequest.prompt` is capped at 2000 characters (`schemas.py:13`).
- The narration path has no tool access, no DB session, and no order path, and its output is
  ephemeral per-caller state.
- The realistic loss on the narration path is the disclaimer and the no-invented-numbers rule
  (§6.2), against the caller's own view.

The structural fix is the same as AI-01: load the context server-side. If a free-form path
survives, fence it explicitly as untrusted data and post-check the output.

### 6.4 Hallucination controls actually present

| Control | Where | Strength |
|---|---|---|
| Closed DSL, `extra="forbid"` everywhere | `spec.py` | Strong — an invented field is rejected, not ignored. |
| Closed indicator catalog with param ranges | `indicators/catalog.py:20-49` | Strong for indicators; not described to the model (§4.3). |
| Capability gate (long-only, single symbol, single position, stop required for `risk_per_trade`) | `spec.py:206-245` | Strong — but not described to the model, which is AI-22. |
| Validate-and-repair with concrete errors | `service.py:46-59` | Good. |
| Fail closed after three attempts | `service.py:59` | Good. |
| "Use ONLY the numbers present … never invent" | `prompts.py:51-53` | Prompt-level only; unverified (§6.1). |
| Symbol existence, intent match, economic sanity | — | **Absent** (§5.3). |
| Output post-check of any kind | — | **Absent**. |

---

## 7. AI-08 (medium) — data egress

Egress is real and is the shipped default path:

- `ai_default_provider: str = "gemini"` (`core/config.py:79`), reinforced by `Dockerfile:27`,
  `render.yaml:27-28`, and `infra/.env.prod.example:35`.
- `providers/gemini.py:12,35-37` POST to
  `https://generativelanguage.googleapis.com/v1beta/models`. The body carries user content
  verbatim: the raw natural-language strategy request (`service.py:47` via
  `build_strategy_prompt`) and the full backtest-results JSON (`prompts.py:71-72`, populated
  from the real result object at `backtest-results.tsx:158-163`).

What is disclosed, and where:

| Surface | Discloses third-party AI processing? |
|---|---|
| `README.md:37`, `:63` | **Yes** — names "Google Gemini (free tier) by default". |
| `.env.example:62-68` | **Yes** — documents both providers and links `aistudio.google.com/apikey`. |
| `docs/DEPLOY.md`, `docs/DEPLOY_FREE_CLOUD.md`, `docs/DEPLOY_FREE_WALKTHROUGH.md` | **Yes** — instruct the operator to obtain a Google key. |
| `apps/web/src/app/methodology/page.tsx:84-90` ("The AI copilot is grounded") | **No** — describes grounding, no-auto-execute, and the non-advice note; never says where the model runs. |
| `methodology/page.tsx:93-102` (the explicit "deliberately not claimed" list) | **No** — nine entries covering SIP feeds, real-money orders, survivorship bias, node-graph builder, train/test split, deflated Sharpe, benchmark overlay; third-party AI processing is absent from the list. |
| `SECURITY.md` | **No** — its only AI line is that no AI/agent path can mint a live order. |
| Privacy policy / terms page | **Does not exist** — no such route under `apps/web/src`. |
| In-product, at the point of submission | **No.** The one runtime mention is a post-hoc toast, after the prompt has already been sent: `` `Drafted via ${resp.provider}` `` (`strategies-view.tsx:59-62`). |
| Startup log | **No** — `main.py:51` logs only `logger.info("startup", env=...)`; the active provider is never logged. |

Two corrections that keep this at medium rather than high:

1. The config default alone causes no egress — `gemini_api_key` defaults to `""` and
   `providers/gemini.py:19-20` raises when it is empty. Egress requires an operator to supply a
   key deliberately. The deployment templates do steer toward exactly that.
2. Both AI endpoints are auth-gated, so no anonymous data leaves.

Also undisclosed anywhere in the repo: on Gemini's **free tier**, submitted content may be used
by the provider to improve its products. For a product whose positioning is transparency —
including an explicit "deliberately not claimed" list — that omission is the notable gap, not
the provider choice itself.

Fix: add an egress line to the methodology page's AI block and to the AI affordances in
`strategies-view.tsx` and `backtest-results.tsx` **before** submission; log the active provider
at `main.py:51`; add a flag in `providers/factory.py` that hard-disables remote providers; and
add the free-tier data-usage caveat to `README.md:37`, which already names the provider.

Related claim: **"both no-cost"** (`README.md:37`) is only partially supported — Gemini's free
tier requires a Google account and key plus the privacy cost above, and the Ollama path is not
reachable in any shipped deployment (§3.2).

Minor hygiene, **AI-21** (info): the untracked local `.env:21` carries `ANTHROPIC_API_KEY=`,
which appears in neither `core/config.py` nor `.env.example`; `Settings(extra="ignore")`
(`config.py:19`) swallows it silently. The file is gitignored, so this is dead configuration,
not a leak.

---

## 8. Budget, quota, and cost control

### 8.1 AI-03 (high) — the budget is advisory, not enforcing

`budget.check` reads the day counter **before** the call (`budget.py:30-34`); `budget.record`
increments it **after** (`budget.py:37-42`). Call sites: `service.py:43` / `:51` (strategy) and
`service.py:63` / `:69` (explain). There is no reservation, no estimate of the request's own
cost, and no per-request ceiling. Therefore:

| Weakness | Evidence |
|---|---|
| One request can overshoot the daily cap arbitrarily | `DAILY_USER_TOKENS = 200_000` (`budget.py:13`) is checked at 0 and recorded at whatever the call actually cost. |
| The input side is unbounded in practice | `ExplainRequest.context` is unconstrained (`schemas.py:22`) and serialized verbatim (`prompts.py:72`). |
| The 2 MB body bound is not guaranteed | `BodySizeLimitMiddleware` reads `content-length` and enforces only `if content_length is not None` (`core/security.py:187-192`). A chunked request carries no `Content-Length`, so the check is skipped entirely. |
| The output side is unbounded too | `providers/gemini.py:27-29` never sets `maxOutputTokens`, so `tokens_out` (`base.py:20-21`) is uncapped. |
| Concurrency is unmetered | N simultaneous requests all pass `check()` before any `record()` lands. |
| One check can authorise three calls | `service.py:43` checks once; `service.py:46-51` may call the provider three times. |
| No dedicated `/ai/*` rate limit | The only brake is the shared per-IP 120/min bucket (`core/ratelimit.py:111-117`, `config.py:56`). The auth module has meanwhile grown a full set of per-IP *and* per-account buckets — `register`, `login`, `pwchange`, `pwreset`, `pwresetconfirm` (`modules/auth/router.py:62,90-91,136,191,193,214`, with `account_bucket` at `core/ratelimit.py:90`) — so the helper and the idiom both exist; the most expensive endpoints in the app simply do not use them. |
| Limits are not operable | `budget.py:13-14` are module constants, not `Settings`. |
| No client backoff signal | `RateLimitedError` (`core/errors.py:56-57`) carries no `Retry-After`. |

Fix: reserve an estimate before the call and settle after; cap tokens per request and cap
`context` bytes; move both limits into `Settings`; add a dedicated per-user `/ai/*` limit.

### 8.2 AI-04 (medium) — a zero-token usage report makes the call free forever

`record` returns early when `tokens <= 0` (`budget.py:37-39`). `GeminiProvider` defaults usage
to `0` when `usageMetadata` is absent (`gemini.py:49-53`), as does Ollama when
`prompt_eval_count`/`eval_count` are missing (`ollama.py:36-38`). A provider or response shape
that omits usage silently no-ops the entire budget, with no log and no metric to notice. Treat
a zero or absent usage report as an anomaly: log it and charge a configured fallback estimate.

### 8.3 AI-16 (medium) — a multi-minute synchronous call on the request path

`router.py:26-27` and `:35-36` run the provider inline. Per-attempt timeouts are 60 s
(`gemini.py:36`) and 120 s (`ollama.py:31`); up to three attempts (`service.py:46`) gives a
180 s / 360 s worst case on one synchronous HTTP request — beyond typical proxy and
platform-rewrite limits. ADR-0002 explicitly lists **"AI calls"** among the work that belongs
off the request path (`docs/adr/0002-async-task-queue-arq.md:6`), and `apps/api/app/worker.py`
has no AI job (§2). The frontend has no `AbortController` or timeout
(`apps/web/src/lib/api/client.ts:116-126`), so `backtest-results.tsx:154-170` can spin on
"Asking AI…" (`:256`) indefinitely.

Either enqueue and poll per ADR-0002, or enforce a total wall-clock budget well under the proxy
timeout — and add a client-side abort either way.

---

## 9. AI-11 (high) — token, latency, and cost measurement: none

There is **no per-run record of any AI call** — no persisted row, no metric, no success or
failure log, no latency, no cost, no model, no provider, no prompt version.

| Expected signal | Actual |
|---|---|
| Success log | None. Both success paths (`service.py:54`, `service.py:70`) are silent. |
| Failure log | None. Gemini quota/HTTP/blocked-content errors (`gemini.py:39,41,46`) and the exhausted-repair `BadRequestError` (`service.py:59`) are all `AppError` subclasses, and the `_app_error` handler (`core/errors.py:84-85`) returns a problem response **without logging**. Only truly unhandled exceptions log (`errors.py:105`). A total provider outage is visible only as status codes in the access log. |
| Any log at all | Exactly one line in the module: `logger.info("ai_strategy_repair", attempt=...)` (`service.py:58`). |
| Token detail | `LLMResponse` already carries `tokens_in`/`tokens_out`/`model`/`provider` (`base.py:11-21`), but `service.py:51,69` consume only `resp.total_tokens` and discard the rest. |
| Latency | Never measured — no timing wraps `provider.generate` (`service.py:48-50`, `:64-68`). The only instrumentation is route-level HTTP timing (`main.py:91`, stock `Instrumentator`, no model-specific collectors). |
| Cost | Not computable — no price data exists anywhere in the codebase. |
| Durable usage history | Two day-keyed Redis counters with a 48 h TTL (`budget.py:13-15,37-42`). No per-call granularity. |
| Audit trail | `app.modules.audit.service` is never imported by the AI module; its only callers are in the auth router (`modules/auth/router.py:66,93,117,146,172,222`). No `ai_runs` table exists in any migration. |

One precision in the module's favour: the single `ai_strategy_repair` line does automatically
carry `request_id` and `user_id`, injected by the structlog processor at
`apps/api/app/core/logging.py:21-26`. User attribution is not the missing piece — model,
provider, tokens, latency, cost, prompt version, and outcome are.

Practical effect: you cannot answer "which model answered this?", "what did it cost?", "how
often does the repair loop fire?", or "did quality regress after we changed the prompt?" — and
there is no data from which an eval set could be built.

---

## 10. AI-12 (high) — evaluation coverage

`apps/api/tests/test_ai.py` is 96 lines run against a test-local `FakeProvider`
(`tests/test_ai.py:21-33`). What it covers: happy path, one repair, give-up, fence stripping,
the per-user budget, one explain call, and auth on `/ai/strategy`.

**Zero execution:**

| Surface | Evidence |
|---|---|
| `providers/gemini.py:24-56` | Never invoked by any test, including the 429 branch (`:38-39`), the non-200 branch (`:40-41`), and the blocked/empty-candidates branch (`:43-46`). No `respx`, `httpx.MockTransport`, or `pytest-httpx` exists anywhere in the repo. |
| `providers/ollama.py:19-41` | Never invoked. |
| `providers/factory.py:12-18` | The body never executes. Its only production call sites are `router.py:26,35`, and the single endpoint test monkeypatches the name on the router module (`tests/test_ai.py:90`), bypassing the real factory including its `AppError` branch. |
| `POST /ai/explain` (`router.py:31-37`) | No test at all; `test_ai_requires_auth` (`tests/test_ai.py:83-84`) covers `/ai/strategy` only. |
| `DAILY_GLOBAL_TOKENS` (`budget.py:33-34`) | Never enforced in a test — `test_budget_blocks_when_exceeded` (`tests/test_ai.py:62-67`) records `DAILY_USER_TOKENS`, which trips the per-user guard at `budget.py:31` first, making the global raise unreachable in the suite. |

**No eval assets.** `git ls-files | grep -iE 'eval|golden|fixture|corpus|dataset'` returns only
`apps/api/app/modules/backtesting/snapshot.py`. There is no NL→spec corpus, no golden files, no
adversarial narration cases, no rubric, and no CI job that would notice a prompt change making
the model worse. CI runs `pytest --cov=app --cov-report=term-missing`
(`.github/workflows/ci.yml:58-59`) with **no `--cov-fail-under`**, so coverage is reported but
never gated; `pip-audit` is `continue-on-error: true` (`ci.yml:60-62`).

**The passing tests are weaker than they look.** `_VALID` (`tests/test_ai.py:18`) is
`example_composite_spec()` serialized, and `test_generate_strategy_valid`
(`tests/test_ai.py:36-39`) asserts `spec.name == example_composite_spec().name` — it confirms
only that the fake echoed the fixture back, verifying no NL→spec behaviour whatsoever.
Likewise `test_explain_returns_grounded_text` (`tests/test_ai.py:70-75`) asserts a disclaimer
string that `FakeProvider` was hardcoded to return (`:71`), so disclaimer compliance is
asserted against a constant, not against a model or a guardrail.

*Correction carried from verification:* both prompt builders **do** have line coverage —
`build_strategy_prompt` (`prompts.py:58-68`) runs on every `generate_strategy` test and its
repair branch (`prompts.py:63-67`) is exercised by `test_generate_strategy_repairs`
(`tests/test_ai.py:42-45`); `build_explain_prompt` (`prompts.py:71-72`) runs via
`service.py:66`. What is missing is any **assertion on their output** — that `DSL_GUIDE`, the
worked example, or the previous-output/validation-error block actually appear in the emitted
prompt. A guarded assertion of exactly that kind would have caught AI-22.

Blast radius is bounded by the design — every generated spec is hard-validated at
`service.py:54`, and the AI path never persists or executes — so the concrete risk is an
undetected response-parsing or error-handling regression in `gemini.py`/`ollama.py`, an
entirely unexercised `/ai/explain`, and prompt/schema drift that only users discover.

---

## 11. Resolved in the working tree while this audit was being written

Two AI-adjacent copy defects were fixed by concurrent v2 work between the first and second
reading passes. They are recorded here rather than as open findings, because the fix is already
in the tree (uncommitted) and because the underlying server behaviour did not change.

| Was | Now | Note |
|---|---|---|
| The dashboard card advertised a capability that does not exist: "Ask the assistant to draft a strategy, explain a backtest, or **summarize a market** — grounded in your data". The AI router exposes exactly two endpoints (`router.py:22,31`); there is no market-summary path and no assistant/chat UI anywhere in `apps/web`. | `dashboard-view.tsx:134-142` — retitled "AI copilot", now describes only drafting a spec and narrating a finished simulation, and states "it never places an order, and it is not financial advice". | Correct, and it matches the code. The in-file comment at `:132-133` states the reasoning. |
| The landing page asserted "Grounded explanations of every result". | `apps/web/src/app/page.tsx:44-45` now describes only spec drafting and validation ("the AI proposes, the engine decides"). | The unconditional grounding claim is gone from the marketing surface. |

Neither change affects §6.1: the server still cannot verify what it narrates. What changed is
that the product no longer *claims* it can.

---

## 12. Findings index

Severity reflects the verified impact in the current working tree, not the worst imaginable
reading. Anchors are repo-relative `file:line`.

| ID | Finding | Severity | Status | Anchor |
|---|---|---|---|---|
| AI-22 | `DSL_GUIDE` instructs the model to emit constructs the validator now rejects (short entries, multi-symbol universe, `max_open_positions>1`, `risk_per_trade` without a stop) | High | bug | `apps/api/app/modules/ai/prompts.py:29` |
| AI-03 | Token budget is a non-reserving pre-check: no reservation, no per-request cap, no `/ai/*` rate limit, limits not configurable | High | bug | `apps/api/app/modules/ai/budget.py:30` |
| AI-11 | No per-run record: no latency, cost, model, provider, prompt version, or outcome; `AppError` failures are never logged | High | missing | `apps/api/app/modules/ai/service.py:58` |
| AI-12 | No eval harness or dataset; providers, factory, `/ai/explain`, and the global cap are entirely unexecuted; passing tests are circular | High | missing | `apps/api/tests/test_ai.py:21` |
| AI-01 | `/ai/explain` narrates an unconstrained client dict; grounding is a prompt instruction, unverifiable server-side; primary concrete impact is cost/availability | Medium | insecure | `apps/api/app/modules/ai/schemas.py:22` |
| AI-04 | A zero or absent usage report silently bypasses the budget entirely | Medium | bug | `apps/api/app/modules/ai/budget.py:38` |
| AI-05 | Provider abstraction has no capabilities, health, retry, fallback, or circuit breaker; a new `httpx` client per call | Medium | partial | `apps/api/app/modules/ai/providers/factory.py:12` |
| AI-06 | Ollama model hardcoded and never passed by the factory; no `OLLAMA_MODEL` setting | Medium | partial | `apps/api/app/modules/ai/providers/ollama.py:15` |
| AI-07 | Every shipped deployment pins the remote provider; the local path is unreachable in containers | Medium | misleading | `Dockerfile:27` |
| AI-08 | Third-party egress disclosed in operator docs but nowhere in the product surface; the free-tier data-usage caveat is disclosed nowhere | Medium | missing | `apps/api/app/core/config.py:79` |
| AI-09 | The non-advice note is unenforced and absent from `/ai/strategy` entirely; still overclaimed in `router.py:5` and `README.md:91` (the methodology page has been corrected — §11) | Medium | misleading | `apps/api/app/modules/ai/router.py:5` |
| AI-10 | No prompt registry or versioning; `DSL_GUIDE` hand-duplicates the catalog with no drift guard and omits every numeric constraint | Medium | duplicated | `apps/api/app/modules/ai/prompts.py:20` |
| AI-13 | No fake/echo provider in application code — CI and keyless dev cannot exercise the real path | Medium | missing | `apps/api/app/modules/ai/providers/factory.py:12` |
| AI-14 | No semantic validation of the generated spec against user intent, the instrument catalog, or economic sanity | Medium | partial | `apps/api/app/modules/ai/service.py:54` |
| AI-15 | Provider transport and configuration errors surface as opaque 500s; `finishReason` never inspected; no `maxOutputTokens` | Medium | bug | `apps/api/app/modules/ai/providers/ollama.py:33` |
| AI-16 | Multi-minute synchronous AI call on the request path contradicts ADR-0002; no client timeout | Medium | bug | `apps/api/app/modules/ai/router.py:26` |
| AI-18 | `ai_default_provider` is an untyped `str`; misconfiguration fails at request time, not at boot | Low | bug | `apps/api/app/core/config.py:79` |
| AI-19 | `_strip_fences` handles only a fence at the exact string boundaries | Low | partial | `apps/api/app/modules/ai/service.py:23` |
| AI-20 | `@runtime_checkable` on `LLMProvider` is unused decoration (and would raise on `issubclass`) | Low | unused | `apps/api/app/modules/ai/providers/base.py:24` |
| AI-21 | Stale `ANTHROPIC_API_KEY` in the untracked local `.env`, silently swallowed by `Settings` | Info | stale | `.env:21` |

AI-02 is absent by design (refuted — §14). AI-17 (the dashboard advertising a "summarize a
market" capability) is absent because it was fixed in the working tree during this audit —
§11.

---

## 13. Gap table against the v2 brief §10–14 and §22

Rows follow the capability list in the brief (agentic graph, compiler stages, RAG, provider
router, circuit breaker, prompt registry, evals) plus the adjacent AI-layer requirements; exact
sub-section numbering is not reproduced here.

| # | Brief capability | Today | Evidence | Gap | Smallest first step |
|---|---|---|---|---|---|
| 1 | **Agentic graph** (typed nodes, explicit state, per-node retry/timeout) | **Absent** | One linear coroutine with a `for` loop (`service.py:39-59`); no state object, no node boundaries, no tool use | Entire | Extract the loop into an explicit `plan → generate → validate → repair` state machine before adding nodes |
| 2 | **Compiler stages** (NL → IR → spec → schema validation → semantic validation → capability check) | **Partial** | Two stages exist: JSON parse plus `StrategySpec.model_validate` (`service.py:53-54`), and the capability gate (`spec.py:206-245`). No IR, no lowering, no semantic pass | Stages 1, 2, 5 | Add the semantic pass of §5.3 as a separate, testable function returning warnings |
| 3 | **RAG / retrieval grounding** (corpus, retriever, citations) | **Absent** | Prompt is a static guide plus one hardcoded example (`prompts.py:61-62`); no vector store, no retriever, no citation channel | Entire | Substrate exists — `docs/v2/BASELINE_VERIFICATION.md` §5 records `pgvector 0.8.1` available on the native PostgreSQL; start with the DSL/indicator corpus, which also attacks AI-10 |
| 4 | **Provider router** (capability- and cost-aware selection) | **Absent** | Two-branch dispatch on a string (`providers/factory.py:12-18`); the protocol has no capabilities (`base.py:24-30`) | Entire | Add capability and cost fields to the protocol and route on them |
| 5 | **Circuit breaker / health / retry / fallback** | **Absent** | No breaker, retry, backoff, or health probe anywhere in `apps/api`; `providers/__init__.py:1` and `ollama.py:1` call Ollama a "fallback" that does not exist | Entire | Ordered fallback chain (Gemini → Ollama) with retry-and-jitter; Redis-backed breaker keyed by provider |
| 6 | **Prompt registry** (ids, semantic versions, changelog, version recorded per run) | **Absent** | No version constant or id in `prompts.py`; nothing records which prompt ran (§9) | Entire | Introduce `strategy.v1` / `narration.v1` ids, record them on every run, then generate the catalog/constraint block of `DSL_GUIDE` from `indicators/catalog.py` and `spec.py` with a CI equality test — this closes AI-22 permanently |
| 7 | **Evals** (versioned corpus scored in CI: validity rate, repair rate, semantic match, disclaimer compliance) | **Absent** | No corpus, no rubric, no scoring, no gate; existing assertions are circular (§10) | Entire | Ship `providers/fake.py` (AI-13) first — it is a hard prerequisite, since this machine has no local LLM runtime |
| 8 | **Structured output from the generated schema / tool use** (ADR-0008) | **Not met** | ADR-0008 (`docs/adr/0008-one-canonical-strategyspec.md:9`) claims the AI target consumes the generated artifact; it consumes a prose guide, and no provider uses tool calling | Entire | Either wire JSON-Schema-constrained decoding or tool use, or amend the ADR to record the prose-guide decision |
| 9 | **Per-run telemetry** (tokens in/out, latency, cost, model, prompt version, repair count, outcome) | **Absent** | §9 in full | Entire | `latency_ms` and `cost_usd` on `LLMResponse`, then an `ai_runs` row and a Prometheus histogram |
| 10 | **Budget/quota with teeth** | **Partial** | Two Redis counters, checked before and recorded after (`budget.py:30-42`); no reservation, no per-request cap, no `/ai/*` limit | Reservation, caps, configurability | Reserve-then-settle, plus `maxOutputTokens` on the provider |
| 11 | **Grounded narration from server-side state** | **Not met** | `/ai/explain` takes a free-form dict and holds no DB session (`schemas.py:22`, `service.py:34-37`) | Entire | Replace `context` with `backtest_id` under owner scoping |
| 12 | **Local-first / offline-capable inference** | **Nominal** | Provider exists but has a hardcoded model, no setting, and no reachable deployment (§3.2) | Config and deployment | `OLLAMA_MODEL` setting passed by the factory; an `ollama` service in `infra/compose.prod.yaml` |
| 13 | **Egress control and disclosure** | **Partial** | Operator docs disclose the provider; the product surface does not; no flag disables remote providers (§7) | Product disclosure and kill switch | One line in the methodology AI block and at both AI affordances; a `factory.py` deny-remote flag |
| 14 | **Off-request-path execution** (ADR-0002) | **Not met** | Inline provider call, 180–360 s worst case (`router.py:26-27`) | Entire | Total wall-clock budget now; ARQ job plus poll for v2 |
| 15 | **Safety invariant: no order placement, no code execution** | **Met** | §2 in full, plus the import-linter contract (`pyproject.toml:112-133`) | None | Preserve; add a test asserting the AI module imports no execution module |

---

## 14. Refuted in verification — not carried forward

Listed for traceability only. This is **not** asserted anywhere above, and no remediation is
proposed for it.

| Proposed finding | Disposition |
|---|---|
| A separate high-severity finding that the absence of delimiters/escaping around interpolated untrusted input is itself an exploitable prompt-injection defect | **Refuted — dropped.** The interpolation is described factually in §6.3 with its verified blast-radius limits, and the structural fix is carried under AI-01. |

Severity corrections applied from verification, in place of the originally proposed ratings:
**AI-01** high → medium (auth-gated, ephemeral, caller-only; the concrete impact is cost and
availability, and `methodology/page.tsx:86` is correctly hedged); **AI-05** high → medium (an
architectural gap, not a live defect; the per-call cost is the HTTP client, not provider
construction); **AI-08** high → medium (the provider *is* named in `README.md:37` and
`.env.example`, so "undisclosed anywhere" was wrong — the gap is the product surface and the
free-tier caveat).

---

## 15. Prioritized remediation

| Priority | Action | Closes | Size |
|---|---|---|---|
| P0 | Update `DSL_GUIDE` for the four capability rules at `spec.py:206-245`, and add a test asserting the emitted prompt contains them | AI-22 | ~10 lines |
| P0 | Replace `/ai/explain`'s free-form `context` with an owner-scoped `backtest_id`; cap and allowlist if a free-form path must remain | AI-01, part of AI-03 | small |
| P0 | Reserve-then-settle budgeting, per-request token cap, `maxOutputTokens`, a dedicated `/ai/*` rate limit, limits into `Settings` | AI-03, AI-04 | small |
| P1 | `providers/fake.py` selectable via config; `Literal` type on `ai_default_provider`; factory and provider tests against `httpx.MockTransport` | AI-13, AI-18, part of AI-12 | small |
| P1 | Per-run telemetry: `latency_ms`/`cost_usd` on `LLMResponse`, an `ai_runs` record, a repair counter, and logging of `AppError` >= 500 in `core/errors.py:84-85` | AI-11 | medium |
| P1 | Append the disclaimer server-side and label AI output in the UI | AI-09 | small |
| P1 | Egress disclosure at the point of submission, provider logged at startup, deny-remote flag | AI-08 | small |
| P2 | Prompt registry with ids/versions, and a CI test that regenerates the catalog/constraint block of `DSL_GUIDE` from `indicators/catalog.py` and `spec.py` | AI-10, and AI-22 permanently | medium |
| P2 | Ordered fallback chain, retry-with-jitter, Redis circuit breaker, shared `httpx` client, typed error mapping | AI-05, AI-15 | medium |
| P2 | Semantic constraint checker (symbol resolution, intent diff, sanity bounds) returning warnings alongside the spec | AI-14 | medium |
| P2 | Eval corpus (NL→spec pairs plus adversarial narration cases) scored in CI on validity, repair rate, semantic match, disclaimer compliance | AI-12 | large |
| P2 | Move the AI call off the request path per ADR-0002, or cap total wall time; add a client `AbortController` | AI-16 | medium |
| P3 | `OLLAMA_MODEL` setting plus an `ollama` service (or a documented `host.docker.internal`) | AI-06, AI-07 | small |
| P3 | Balanced-JSON extraction in place of boundary fence-stripping; drop or use `@runtime_checkable`; clean the stale `.env` key | AI-19, AI-20, AI-21 | trivial |

---

## Baseline Verification (see BASELINE_VERIFICATION.md)

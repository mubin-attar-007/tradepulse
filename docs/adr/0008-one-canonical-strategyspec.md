# 0008 — One canonical `StrategySpec` (generated downstream)

Date: 2026-06-03 · Status: Accepted (forward-looking; implemented in Phase 4)

## Context
The adversarial design review found the strategy object specified four incompatible ways (AI, engine, DB, frontend) with no owner — the #1 integration risk. It is the contract that backtesting, paper trading, AI, and UI all depend on.

## Decision
A single versioned **Pydantic v2 `StrategySpec`** in `app/modules/strategies` is the source of truth, owned by Quant Core (it compiles and executes the spec). The JSON Schema is generated from it; the AI tool-use target, the zod/TypeScript types (via OpenAPI→TS), and the DB JSONB validation all consume the generated artifact. No free-form string-expression DSL. `spec_version` is required; a CI drift-guard fails if the generated artifacts diverge. Mandatory exit logic + position sizing + risk limits are baked into the schema (fixing the legacy's optimistic, entry-only strategies).

## Consequences
- One schema, many generated consumers — no silent divergence.
- A spec migration policy is required so saved versions backtest identically forever (reproducibility).

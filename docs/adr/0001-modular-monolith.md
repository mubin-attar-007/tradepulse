# 0001 — Modular monolith (not microservices)

Date: 2026-06-03 · Status: Accepted

## Context
Solo, low-budget, personal-first build deploying to a single VPS. Microservices add operational and cognitive overhead disproportionate to current scale, while we still want clean bounded contexts that could split out later.

## Decision
One FastAPI app + one ARQ worker sharing a codebase and image. Bounded modules under `app/modules/*` with a uniform shape and a layered dependency DAG enforced in CI by import-linter (`core < audit < auth < domain < ai`). The kernel (`app/core`) never imports a domain module.

## Consequences
- Single deploy unit; simple local dev (`docker compose up`).
- Module boundaries + the import-linter contract keep a future service extraction cheap.
- Collapse to ~7 modules for MVP; re-expand as domains come online.

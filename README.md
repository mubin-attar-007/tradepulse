# AI-Powered Algorithmic Trading Platform

A production-grade, personal-first (SaaS-ready) platform for **US equities + crypto**: market data, charting, a strategy builder, an honest event-driven backtester, paper trading, and an AI copilot. Live real-money trading is a gated, deferred phase.

> Greenfield rebuild. The legacy college-era bot lives in `_archived/` (untracked) as an ideas-only reference. Full architecture & roadmap: see the approved plan file.

## Stack
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic, ARQ
- **Data:** PostgreSQL + TimescaleDB, Redis
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui (TanStack Query + Zustand)
- **AI:** Claude (Haiku/Sonnet) + local Ollama
- **Tooling:** `uv` (Python), `npm` (web), `just` (tasks), Docker Compose, Caddy (prod)

## Quick start
```bash
cp .env.example .env          # then fill secrets (see comments in the file)
just bootstrap                # uv sync + docker up + migrate
just api                      # FastAPI at http://localhost:8080  (/docs, /health)
just web                      # Next.js at http://localhost:3000   (later phases)
```

## Layout
```
apps/api      FastAPI app + ARQ worker (modular monolith: core kernel + domain modules)
apps/web      Next.js frontend
packages/     shared contracts (generated OpenAPI -> TS client + zod)
infra/        Docker, Caddy, deploy/backup scripts
docs/adr/     Architecture Decision Records
_archived/    legacy reference (untracked)
```

## Guiding invariants
1. Every domain row is `owner_id`-scoped (SaaS-ready tenancy).
2. Money is `Decimal`/`NUMERIC` server-side; it crosses the API as decimal strings.
3. One bar lifecycle (`forming → is_final`); decisions only ever act on closed bars.

# 0002 — ARQ for background jobs

Date: 2026-06-03 · Status: Accepted

## Context
We need async background work (backtests, ingestion, alert evaluation, AI calls) without blocking the request path. The app is async (FastAPI/asyncio) and already runs Redis.

## Decision
Use **ARQ** (asyncio-native, Redis-backed). The worker shares the app package; the market-data ingestion supervisor and cron jobs will live in the worker process — never in the API lifespan, so web deploys never drop the live feed.

## Consequences
- No extra broker beyond Redis; minimal moving parts for a solo operator.
- Rejected Celery (heavier, sync-first) and RQ (no native async).
- ProcessPoolExecutor for CPU-bound backtests is deferred until a single job measurably starves the worker.

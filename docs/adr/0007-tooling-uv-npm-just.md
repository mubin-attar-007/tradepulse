# 0007 — Tooling: uv + npm + just + Docker Compose

Date: 2026-06-03 · Status: Accepted

## Context
Need fast, reproducible local dev for a solo builder on Windows, deployable to a single Linux VPS.

## Decision
- **uv** for Python (project-local `.venv`, pinned Python 3.12 — the machine's system 3.14 is too new for the data/quant stack).
- **npm** for the frontend (pnpm was unavailable: `corepack enable` hit an EPERM under Program Files; npm is functionally equivalent for one app).
- **just** as the task runner (`set windows-shell := pwsh`).
- **Docker Compose** for TimescaleDB + Redis, locally and in prod. Containers are mapped to high host ports (DB 55432, Redis 56379) to avoid a native PostgreSQL already on 5432.

## Consequences
- `just bootstrap` takes a clean clone to a running, migrated stack.
- Revisit pnpm if/when a JS workspace with multiple packages appears.

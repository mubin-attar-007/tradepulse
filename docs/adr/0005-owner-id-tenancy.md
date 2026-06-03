# 0005 — `owner_id` on every domain row (invariant #1)

Date: 2026-06-03 · Status: Accepted

## Context
Personal-first but SaaS-ready. Retrofitting tenancy later is a painful migration, so the seam must exist from day one without the machinery (no billing/org/RBAC yet).

## Decision
Every user-owned row carries `owner_id` (via `OwnerMixin`/`OwnedEntity`). The `OwnedRepository` base is the single data-access path: it filters every query by owner and stamps `owner_id` from the repository's owner on insert (never from caller input). A `nullable org_id` and a dormant RLS GUC seam exist for the SaaS path.

## Consequences
- Cross-tenant access is impossible by construction; guarded by an integration test.
- Postgres row-level security can be switched on later without schema change.

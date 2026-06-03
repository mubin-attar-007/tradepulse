# 0006 — `Decimal`/`NUMERIC` money; decimal strings over the wire (invariant #2)

Date: 2026-06-03 · Status: Accepted

## Context
Float arithmetic silently corrupts P&L and accounting. JavaScript has no decimal type (all numbers are IEEE-754 doubles), so the serialization boundary must be explicit.

## Decision
All money/quantity/price are `Decimal` server-side and `NUMERIC` in Postgres. They cross the API as **decimal strings** (a `Money` type in the OpenAPI schema); the frontend renders them via a decimal-aware formatter and never does arithmetic on them. Floats are allowed only inside indicator math; equity-curve points for charting are explicitly display-only downsampled floats.

## Consequences
- No precision drift in ledgers or the AI "no-invented-numbers" check.
- Frontend formatting helpers required; documented as a shared contract.

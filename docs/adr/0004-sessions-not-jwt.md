# 0004 — Opaque Redis sessions, not JWT

Date: 2026-06-03 · Status: Accepted

## Context
A Next.js SPA + FastAPI API needs auth. For a trading app, immediate server-side revocation matters (logout, compromise, kill-switch), and JWTs are hard to revoke before expiry.

## Decision
Opaque random session tokens stored in Redis under a TTL, carried in an `httpOnly`, `SameSite=Lax` cookie (`__Host-` prefix in production). Passwords hashed with **argon2id**. CSRF via double-submit cookie + header on unsafe methods (defense-in-depth alongside SameSite). OAuth and TOTP MFA are deferred to the live-trading gate.

## Consequences
- Logout/revocation is a single Redis key delete.
- No token-leakage blast radius; no client-side token storage.
- Sessions require Redis availability (already a hard dependency).

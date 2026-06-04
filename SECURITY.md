# Security Policy

This is a personal-first, security-sensitive project (it stores broker API keys
and, behind a gate, can place real-money orders). Security issues are taken
seriously.

## Reporting a vulnerability

**Do not open a public issue for security problems.** Instead use GitHub's
private reporting: the repository's **Security → Report a vulnerability** tab
(Private Vulnerability Reporting). You'll get a response as soon as possible.

## Handling secrets

- Real secrets never live in the repo. Only `*.example` templates are committed;
  `.env`, `.env.*`, `*.pem`, `*.key`, and `secrets/` are git-ignored.
- A **gitleaks** scan runs in pre-commit and in CI (full git history) — a
  committed secret fails the build.
- If a key is ever exposed, **rotate it immediately** (it must be assumed
  compromised) and force-purge it from history.

## Safety invariants (do not regress)

- Real-money live trading is **disabled by default** (`LIVE_TRADING_ENABLED=false`)
  and structurally gated (feature flag + opt-in + 2FA + step-up + kill-switch +
  enforced risk + per-order confirmation). No AI/agent path can mint a live order.
- Broker credentials are encrypted at rest (libsodium) and never logged or
  returned by the API.
- Every domain row is `owner_id`-scoped; cross-tenant reads are tested.

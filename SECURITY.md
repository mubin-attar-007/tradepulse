# Security Policy

This is a personal-first, security-sensitive project (it stores broker API keys
and, behind a gate, is intended to one day place real-money orders). Security
issues are taken seriously.

The repository is **proprietary** (see `LICENSE`) — it is not open source.

## Reporting a vulnerability

**Do not open a public issue for security problems.** Instead use GitHub's
private reporting: the repository's **Security → Report a vulnerability** tab
(Private Vulnerability Reporting). You'll get a response as soon as possible.

## Handling secrets

- Real secrets never live in the repo. Only `*.example` templates are committed;
  `.env`, `.env.*`, `*.pem`, `*.key`, and `secrets/` are git-ignored.
- A **gitleaks** scan runs in pre-commit and in CI (full git history) — a
  committed secret fails the build.
- **Generate every key yourself.** A key pasted from a document, a chat, a
  tutorial or another deployment is not a secret: everyone who has seen it can
  decrypt everything it protects. This applies above all to `BROKER_CRED_KEY`,
  which is the key for broker credentials at rest.
- If a key is ever exposed, **rotate it immediately** (it must be assumed
  compromised) and force-purge it from history. Note that rotating
  `BROKER_CRED_KEY` makes existing stored broker credentials undecryptable —
  they must be re-entered.
- Prefer secrets in **headers**, not URLs. `/internal/tick` and
  `/internal/backfill` accept `Authorization: Bearer <TICK_SECRET>`; the
  `?key=` form still works but is copied verbatim into proxy and host access logs.

## Safety invariants (do not regress)

- **Every domain row is `owner_id`-scoped**; cross-tenant reads are tested
  (`apps/api/tests/test_tenancy.py`).
- **CSRF is enforced for every cookie-authenticated unsafe request**, in one
  place: `get_current_user` (`apps/api/app/modules/auth/deps.py`) runs the
  double-submit check before any Redis or database work. Do not add an
  authenticated mutating route that bypasses that dependency, and do not
  "temporarily" skip the check for a client that finds it inconvenient — the
  browser client already echoes the `csrf_token` cookie into `X-CSRF-Token`.
  Covered by `apps/api/tests/test_security.py`.
- **A credential change ends every session it authorized.** Changing a password
  or completing a reset revokes all of that user's sessions (the change-password
  path immediately re-mints one for the caller). Sessions are indexed per user in
  Redis specifically so this is possible; keep that index in step with any change
  to session storage. Covered by `apps/api/tests/test_auth.py`.
- **Password-reset tokens are stored only as SHA-256 digests, consumed
  atomically (`GETDEL`), expire in 30 minutes, and supersede one another** — a
  Redis dump yields no usable reset link, and a token cannot be redeemed twice.
- **Secrets are compared on bytes, in constant time** (`constant_time_compare`).
  `hmac.compare_digest` raises on a non-ASCII `str`, which turns a rejected
  credential into a 500 — and a 500-vs-404 difference tells a prober that the
  endpoint is armed.
- **`X-Forwarded-For` is believed only when a proxy of ours produced it**
  (`TRUST_PROXY_HEADERS` / `TRUSTED_PROXY_HOPS`, default off). The client IP is
  the Nth-from-the-right hop, never the attacker-writable leftmost one, and it is
  validated as an IP before it becomes part of a Redis key.
- **Credential endpoints are budgeted per account as well as per IP.** Per-IP
  alone is one shared bucket behind a proxy (any visitor can lock out login for
  everyone) and no bucket at all against a botnet.
- Broker credentials are encrypted at rest (libsodium) and never logged or
  returned by the API.

## Live trading (what is actually true today)

Real-money live trading is **disabled by default** (`LIVE_TRADING_ENABLED=false`)
and cannot be turned on by flipping that flag: `POST /live/orders` evaluates
`LiveTradingGate` and then unconditionally raises 403 as a terminal guard, so no
code path — including any AI/agent path — can place a real order.

The control stack the gate names (2FA, explicit opt-in, step-up confirmation,
kill-switch, enforced risk limits, per-order confirmation) is a **specification
the gate checks against, not a set of implemented controls**. Do not describe it
as shipped, and do not remove the terminal 403 before every one of those controls
exists and is tested.

Known gap, tracked: `POST /brokers/connections` accepts `env="live"` and persists
the credentials without consulting the live gate and without an audit row, and
there is no delete/revoke endpoint. Until that is fixed, treat the endpoint as
capable of taking custody of live-account API secrets.

## Operating a deployment safely

- In production the API logs an `insecure_production_config` warning at startup
  for each of: `FRONTEND_URL` still pointing at localhost, SMTP unconfigured,
  `COOKIE_SECURE=false`, and metrics enabled with no `METRICS_TOKEN`. Treat a
  non-empty list as an unfinished deploy — each one silently breaks a
  user-facing flow rather than the process. See `docs/DEPLOY.md` §2a.
- `/metrics` is fail-closed: without a matching `METRICS_TOKEN` it returns 404,
  not 401, so it is not advertised. Prometheus reads the token from a mounted
  file — see the wiring notes in `infra/prometheus.yml`.

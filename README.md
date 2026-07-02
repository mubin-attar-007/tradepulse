<div align="center">

# 📈 TradePulse

### AI-powered algorithmic trading intelligence — US equities + crypto.

Live market data, interactive charts, a strategy builder, an **honest event-driven backtester**,
paper trading, and an **AI copilot** (NL → strategy) — a production-grade, SaaS-ready platform.
*(Live real-money trading is a gated, deferred phase.)*

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-online-3b82f6?style=for-the-badge)](https://tradepulse.vercel.app)
&nbsp;
[![Methodology](https://img.shields.io/badge/Methodology-transparency-009688?style=for-the-badge)](https://tradepulse.vercel.app/methodology)

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-000000?logo=next.js&logoColor=white)
![TimescaleDB](https://img.shields.io/badge/TimescaleDB-Postgres-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis_+_ARQ-DC382D?logo=redis&logoColor=white)

<br/>

<img src="docs/assets/screenshot.png" alt="TradePulse — AI-powered trading intelligence" width="100%"/>

</div>

---

A production-grade, personal-first (SaaS-ready) platform for **US equities + crypto**: market data,
charting, a strategy builder, an honest event-driven backtester, paper trading, and an AI copilot.

## Stack
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Alembic, ARQ
- **Data:** PostgreSQL + TimescaleDB, Redis
- **Market data (free):** CCXT (crypto OHLCV) + yfinance (equities) out of the box; Alpaca optional (free paper keys)
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui (TanStack Query + Zustand)
- **AI (free):** Google Gemini (free tier) by default, or a local Ollama model — both no-cost
- **Tooling:** `uv` (Python), `npm` (web), `just` (tasks), Docker Compose, Caddy (prod)

## Quick start
```bash
cp .env.example .env          # then fill secrets (see comments in the file)
just bootstrap                # uv sync + docker up + migrate
just seed                     # register the equity + crypto instrument universe
just backfill BTC/USD 2       # pull 2 days of REAL 1m bars (free, via CCXT) — repeat per symbol
just api                      # FastAPI at http://localhost:8080  (/docs, /health)
just worker                   # ARQ worker: live ingestion + paper-trading cron
just web                      # Next.js at http://localhost:3000
```

## Layout
```
apps/
  api/                  FastAPI app + ARQ worker (modular monolith)
    app/
      core/             kernel: config, db, redis, security, errors, events, observability
      modules/
        auth/           users, sessions, credentials, broker_connections (encrypted)
        market_data/    instruments, OHLCV store, providers (ccxt/yfinance/alpaca), realtime
        strategies/     canonical StrategySpec DSL, CRUD, versioning
        backtesting/    event-driven engine, metrics, async orchestration
        trading/        paper engine, portfolio, brokers + gated live seam
        ai/             LLM copilot (Gemini/Ollama): NL->spec, narration
        audit/          append-only event log
      cli/              seed, backfill, export_openapi
    alembic/            migrations (single linear head)
    tests/              unit + integration + financial-correctness
  web/                  Next.js frontend (app router, generated typed API client)
packages/contracts/     OpenAPI spec -> generated TS client + zod
infra/                  Dockerfiles, compose.prod.yaml, Caddyfile, deploy/backup scripts, observability
docs/                   DEPLOY runbook + Architecture Decision Records (docs/adr/)
```

## Guiding invariants
1. Every domain row is `owner_id`-scoped (SaaS-ready tenancy).
2. Money is `Decimal`/`NUMERIC` server-side; it crosses the API as decimal strings.
3. One bar lifecycle (`forming → is_final`); decisions only ever act on closed bars.

## Methodology & honest limits
Credibility comes from transparency, not cherry-picked numbers. What's genuinely real today:
- **Backtests are look-ahead-free** — event-driven bar replay; orders fill at the *next* bar's open,
  never the signal bar's close. Every run is reproducible (spec hash + engine version + data fingerprint).
- **Costs modeled by default** — commission 2 bps/side + 1 bps slippage on every fill; reported returns
  are net of costs, and total commission is shown alongside each result.
- **Risk controls are enforced** — position caps, max-daily-loss halt, consecutive-loss limits; each
  risk event is recorded on the result.
- **Honest reporting** — drawdown always shown; Sharpe/Sortino annualized with a risk-free rate of 0
  (stated wherever they appear); every backtest/paper result carries a hypothetical-performance notice.
- **Data provenance** — prices are polled (~30s) and labeled `DELAYED`; no real-time SIP claim.
- **Grounded AI copilot** — generates a validated spec, never auto-executes, instructed to use only the
  numbers present (refuses rather than invents), and always closes with a not-investment-advice note.

**Deliberately *not* claimed (roadmap, not faked in the UI):** a real-time consolidated (SIP) feed;
survivorship-free / point-in-time fundamentals; an automatic in-sample/out-of-sample split;
Deflated-Sharpe / multiple-testing correction; a buy-and-hold benchmark overlay (the price series
isn't yet exposed to the client). See the in-app
[Methodology page](https://tradepulse.vercel.app/methodology).

## Security & ops
- `/metrics` is gated by `METRICS_TOKEN` (404 without it); request bodies capped at `MAX_REQUEST_BYTES`;
  market-data provider calls bounded by `MARKET_DATA_TIMEOUT_SECONDS`.
- DSN-gated **Sentry** on the API (`SENTRY_DSN`) and web (`NEXT_PUBLIC_SENTRY_DSN`); CSP + React error
  boundaries on the frontend.
- CI adds informational `pip-audit` / `npm audit` + a coverage report alongside the existing
  mypy / import-linter / migration / OpenAPI-drift gates. Backups: `infra/backup.sh` (nightly) +
  `infra/restore.sh` (monthly restore-verify). See [docs/](docs/).

## License
Proprietary — © 2026 Mubin Attar. All rights reserved. Personal and commercial
use is reserved to the owner; no third-party use without written permission.
See [LICENSE](LICENSE).

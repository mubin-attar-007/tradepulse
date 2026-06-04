# Free Cloud Deploy — no card, no server

Managed free-tier deploy: **Neon** (Postgres) + **Upstash** (Redis) + **Render**
(API) + **Vercel** (web) + **cron-job.org** (drives live updates). **$0, no card.**

> Trade-offs (free tiers): the API **sleeps when idle** (~30–60s to wake; the cron
> keeps it warm), live data is **~5-min** cadence (not 30s), and **Vercel Hobby is
> non-commercial**. For an always-on, full-fidelity deploy, use a VM instead
> (`docs/DEPLOY_FREE_WALKTHROUGH.md`) — the code supports both.

## Part A — Publish to GitHub (done)
Already at `github.com/mubin-attar-007/AI-Powered-Trading-System`. Just **Sync** the
latest commits so Render/Vercel build the current code.

## Part B — Rotate your Gemini key (before deploy)
It was shared in chat, so treat it as compromised: **aistudio.google.com/apikey**
→ delete the old key → **Create API key** → keep the new one for Part D.

## Part C — Create the free data services (~10 min, sign in with GitHub, no card)
1. **Neon (database)** — neon.tech → New Project (region near you) → copy the
   connection string. You'll use it as
   `DATABASE_URL = postgresql+asyncpg://USER:PASS@HOST/DB?sslmode=require`
   *(only change `postgresql://` → `postgresql+asyncpg://`; keep `?sslmode=require` —
   the app handles the SSL translation automatically).*
2. **Upstash (Redis)** — upstash.com → Create Database → **Regional**, free → copy
   the `rediss://default:PASS@HOST:6379` string → that's `REDIS_URL`.

## Part D — Backend on Render (Blueprint, ~10 min)
1. render.com → sign up with GitHub (no card).
2. **New → Blueprint** → pick this repo. Render reads `render.yaml` and creates the
   **`trading-api`** service (builds the Docker image, runs migrations on deploy).
3. On `trading-api → Environment`, set the secrets (the ones marked `sync: false`):
   - `DATABASE_URL` = your Neon URL (the `+asyncpg…?sslmode=require` form above)
   - `REDIS_URL` = your Upstash `rediss://…`
   - `BROKER_CRED_KEY` = `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`
   - `GEMINI_API_KEY` = your rotated key
   - `CORS_ALLOW_ORIGINS` = your Vercel URL (set a placeholder now; update after Part E)
   - *(`APP_SECRET_KEY` + `TICK_SECRET` are auto-generated — no action.)*
4. Deploy → it serves at `https://trading-api-XXXX.onrender.com`. Check `/health`.
5. Copy the generated **`TICK_SECRET`** value (Environment tab) — needed in Part F.

## Part E — Frontend on Vercel (~5 min)
1. vercel.com → sign up with GitHub (no card).
2. **Add New → Project** → import this repo → **Root Directory = `apps/web`**
   (Next.js auto-detected).
3. Environment variables:
   - `API_PROXY_TARGET` = `https://trading-api-XXXX.onrender.com`
     *(server-side proxy → keeps your login cookies first-party on the Vercel domain)*
   - `NEXT_PUBLIC_API_BASE` = `/api`
   - `NEXT_PUBLIC_WS_URL` = `wss://trading-api-XXXX.onrender.com/market/ws`
4. Deploy → you get `https://your-app.vercel.app`.
5. Back on **Render**, set `CORS_ALLOW_ORIGINS = https://your-app.vercel.app` → it
   redeploys. *(Live charts stream best-effort; chart history + periodic refresh
   always work even if the websocket can't connect.)*

## Part F — Live updates via free cron (~3 min)
1. cron-job.org → free sign up (no card).
2. New cronjob:
   - **URL:** `https://trading-api-XXXX.onrender.com/internal/tick?key=<TICK_SECRET>`
   - **Method:** POST
   - **Schedule:** every 5 minutes
3. Each call polls the latest bars + advances paper sessions, and keeps the API warm.

## First run — seed real data (Render → trading-api → Shell)
```bash
python -m app.cli.seed
python -m app.cli.backfill BTC/USD --days 2
python -m app.cli.backfill ETH/USD --days 2
```
Open your Vercel URL → register → dashboard. (First load after idle may take
~30–60s while Render wakes.)

## Notes
- **Upstash free** = 500K Redis commands/month — comfortable at a 5-min cadence.
- **Neon free** autosuspends; the first query after idle adds ~1s.
- Real-money live trading stays **off** (`LIVE_TRADING_ENABLED=false`).
- Don't paste any connection string/secret into chat — set them directly in the
  Render/Vercel dashboards.

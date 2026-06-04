# Free Cloud Deploy — no card, no server

Managed free-tier deploy: **Neon** (Postgres) + **Upstash** (Redis) +
**Hugging Face Spaces** (API + AI, Docker) + **Vercel** (web) + **cron-job.org**
(drives live updates). **$0, no credit card.**

> Trade-offs (free tiers): the HF Space **sleeps after ~48h idle** (the cron keeps
> it warm; first wake takes ~30–60s), live data is **~5-min** cadence (not 30s),
> and **Vercel Hobby is non-commercial**. A public HF Space means its copy of the
> **code is public** (your GitHub repo stays private; secrets live in HF Settings,
> not the code). For an always-on, private, full-fidelity deploy, use a VM instead
> (`docs/DEPLOY_FREE_WALKTHROUGH.md`) — the code supports both.
> *(A `render.yaml` is also included if you ever use Render with a card.)*

## Part A — Publish to GitHub (done)
At `github.com/mubin-attar-007/AI-Powered-Trading-System`. **Sync** the latest
commits so the code you push to HF is current.

## Part B — Rotate your Gemini key (before deploy)
**aistudio.google.com/apikey** → delete the old key → **Create API key** → keep it
for the HF secrets below.

## Part C — Create the data services (~10 min, GitHub login, no card)
1. **Neon (database)** — neon.tech → create the `tradepulse` database (SQL Editor:
   `CREATE DATABASE tradepulse;`) → `Connect` → copy the string. Use it as
   `DATABASE_URL = postgresql+asyncpg://USER:PASS@HOST/tradepulse?sslmode=require`
   *(only swap `postgresql://` → `postgresql+asyncpg://`; the app handles SSL).*
2. **Upstash (Redis)** — upstash.com → Create Database → **Regional**, free → copy
   the **`rediss://default:PASS@HOST:6379`** URL (the TLS one, not the REST URL).

## Part D — Backend + AI on Hugging Face Spaces (~10 min)
1. **huggingface.co** → sign up (no card).
2. **Settings → Access Tokens → New token** (role **Write**) → copy it (used as the
   git push password).
3. **huggingface.co/new-space** → name `tradepulse`, **SDK = Docker** (Blank),
   Hardware **CPU basic (free)**, **Public** *(needed for a reachable URL — the code
   becomes public; secrets stay in Settings)* → Create.
4. **Space → Settings → Variables and secrets** → add these as **Secrets**:
   - `DATABASE_URL` = your Neon `+asyncpg…/tradepulse?sslmode=require`
   - `REDIS_URL` = your Upstash `rediss://…`
   - `BROKER_CRED_KEY` = `879AbT3ObZztEDuN6J+D7NKSZMk2PMvoOCvGfv4VWmk=` *(test key)*
   - `GEMINI_API_KEY` = your rotated key
   - `APP_SECRET_KEY` = a long random string (`secrets.token_urlsafe(48)`)
   - `TICK_SECRET` = a random string (used by the cron in Part F)
   - `CORS_ALLOW_ORIGINS` = your Vercel URL (placeholder now; update after Part E)
5. Push the code to the Space (from the repo root):
   ```bash
   git remote add space https://huggingface.co/spaces/mubin-attar-007/tradepulse
   git push space main --force      # username = your HF user, password = the Write token
   ```
6. The Space builds from the root `Dockerfile` (watch **Logs**). On start it runs
   migrations + seeds the instruments, then serves. When it shows **Running**, the
   API is at `https://mubin-attar-007-tradepulse.hf.space`.
   Check `…hf.space/health` → `{"status":"ok"}` and `…hf.space/ready` → db+redis.

## Part E — Frontend on Vercel (~5 min)
1. vercel.com → sign up with GitHub (no card).
2. **Add New → Project** → import the repo → **Root Directory = `apps/web`**.
3. Environment variables:
   - `API_PROXY_TARGET` = `https://mubin-attar-007-tradepulse.hf.space`
     *(server-side proxy → login cookies stay first-party on the Vercel domain)*
   - `NEXT_PUBLIC_API_BASE` = `/api`
   - `NEXT_PUBLIC_WS_URL` = `wss://mubin-attar-007-tradepulse.hf.space/market/ws`
4. Deploy → you get `https://your-app.vercel.app`.
5. Back on **HF → Settings → secrets**, set `CORS_ALLOW_ORIGINS = https://your-app.vercel.app`
   (the Space restarts). *(Live charts are best-effort; history + periodic refresh
   always work.)*

## Part F — Live updates + history (no shell needed)
**Cron** (cron-job.org → free, no card): create a job →
`POST https://mubin-attar-007-tradepulse.hf.space/internal/tick?key=<TICK_SECRET>`
every **5 minutes** (polls bars + advances paper sessions, and keeps the Space awake).

**Load history once** (run locally, or as a one-off cron job):
```bash
curl -X POST "https://mubin-attar-007-tradepulse.hf.space/internal/backfill?symbol=BTC/USD&days=2&key=<TICK_SECRET>"
curl -X POST "https://mubin-attar-007-tradepulse.hf.space/internal/backfill?symbol=ETH/USD&days=2&key=<TICK_SECRET>"
```

Open your Vercel URL → register → dashboard. (First load after idle may take
~30–60s while the Space wakes.)

## Notes
- **Upstash free** = 500K Redis commands/month — fine at a 5-min cadence.
- **Neon free** autosuspends; first query after idle adds ~1s.
- Real-money live trading stays **off** (`LIVE_TRADING_ENABLED=false`).
- Secrets live in **HF Space Settings**, never in the code/repo.

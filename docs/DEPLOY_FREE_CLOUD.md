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
At `github.com/mubin-attar-007/tradepulse`. **Sync** the latest
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
4. **Generate your own secrets first** (on your machine — each command prints one
   value; never reuse a key you found in a document, including this one):
   ```bash
   python -c "import base64,nacl.utils;print(base64.b64encode(nacl.utils.random(32)).decode())"  # BROKER_CRED_KEY
   python -c "import secrets;print(secrets.token_urlsafe(48))"                                   # APP_SECRET_KEY
   python -c "import secrets;print(secrets.token_urlsafe(32))"                                   # TICK_SECRET
   python -c "import secrets;print(secrets.token_urlsafe(32))"                                   # METRICS_TOKEN
   ```
   > ⚠️ **A shared key is not a key.** `BROKER_CRED_KEY` is what encrypts broker API
   > credentials at rest. If two people paste the same value, either can decrypt the
   > other's credentials — the encryption becomes decoration. The same applies to
   > `APP_SECRET_KEY` and `TICK_SECRET`. Generate each one yourself, keep it only in
   > the Space's secret store, and rotate it if it is ever pasted anywhere else.
   > (Rotating `BROKER_CRED_KEY` makes already-stored broker credentials
   > undecryptable — you have to re-enter them.)
5. **Space → Settings → Variables and secrets** → add these as **Secrets**:
   - `DATABASE_URL` = your Neon `+asyncpg…/tradepulse?sslmode=require`
   - `REDIS_URL` = your Upstash `rediss://…`
   - `BROKER_CRED_KEY` = the value you generated above
   - `GEMINI_API_KEY` = your rotated key
   - `APP_SECRET_KEY` = the value you generated above
   - `TICK_SECRET` = the value you generated above (used by the cron in Part F)
   - `TRUST_PROXY_HEADERS` = `true` and `TRUSTED_PROXY_HOPS` = `1` — **required here.**
     HF Spaces terminates TLS upstream, so without these every visitor is seen as the
     same proxy IP and shares a single rate-limit bucket. Leave them unset anywhere the
     API is reachable directly: trusting a forwarded header from an untrusted peer lets
     anyone spoof their way past the limits entirely.
   - `NEXT_PUBLIC_SITE_URL` (set on Vercel in Part E, not here) = your public URL. It is
     inlined at BUILD time, and without it the site is served `noindex` with an empty
     sitemap by design, rather than claiming a domain it cannot verify.
   - `CORS_ALLOW_ORIGINS` = your Vercel URL (placeholder now; update after Part E)
   - `FRONTEND_URL` = the same Vercel URL — **password-reset links are built from
     this**. Leave it unset and every reset email points at `http://localhost:3000`,
     which is a dead link for everyone but you.
   - `SMTP_USER` / `SMTP_PASSWORD` = a Gmail address + a Google **App Password**
     (Account → Security → 2-Step Verification → App passwords). Leave them unset
     and no reset email is ever sent — the link is written to the Space logs instead,
     so password reset silently does not work for your users.
6. Push the code to the Space (from the repo root):
   ```bash
   git remote add space https://huggingface.co/spaces/mubin-attar-007/tradepulse
   git push space main --force      # username = your HF user, password = the Write token
   ```
7. The Space builds from the root `Dockerfile` (watch **Logs**). On start it runs
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
5. Back on **HF → Settings → secrets**, set **both** to your real Vercel URL
   (the Space restarts):
   - `CORS_ALLOW_ORIGINS = https://your-app.vercel.app`
   - `FRONTEND_URL = https://your-app.vercel.app` — password-reset emails are built
     from this; left at the default they link to `localhost` and nobody can reset.

   *(Live charts are best-effort; history + periodic refresh always work.)*

## Part F — Live updates + history (no shell needed)
**Cron** (cron-job.org → free, no card): create a job →
`POST https://mubin-attar-007-tradepulse.hf.space/internal/tick`, and in the job's
**Headers** tab add `Authorization: Bearer <TICK_SECRET>`. Run it every **5 minutes**
(polls bars + advances paper sessions, and keeps the Space awake).

> Put the secret in the **header**, not in the URL. `?key=<TICK_SECRET>` is still
> accepted for schedulers that cannot set headers, but URLs are recorded verbatim in
> proxy and host access logs, so a secret in a query string is a secret you have
> published to every log reader.

**Load history once** (run locally, or as a one-off cron job):
```bash
H="Authorization: Bearer <TICK_SECRET>"
curl -X POST -H "$H" "https://mubin-attar-007-tradepulse.hf.space/internal/backfill?symbol=BTC/USD&days=2"
curl -X POST -H "$H" "https://mubin-attar-007-tradepulse.hf.space/internal/backfill?symbol=ETH/USD&days=2"
```

Open your Vercel URL → register → dashboard. (First load after idle may take
~30–60s while the Space wakes.)

## Notes
- **Check the startup log after the first boot.** In production the API logs an
  `insecure_production_config` warning for each of: `FRONTEND_URL` still pointing at
  localhost, SMTP unconfigured, `COOKIE_SECURE=false`, and metrics enabled with no
  `METRICS_TOKEN`. An empty warning list is the signal that this part is done.
- **Upstash free** = 500K Redis commands/month — fine at a 5-min cadence.
- **Neon free** autosuspends; first query after idle adds ~1s.
- Real-money live trading stays **off** (`LIVE_TRADING_ENABLED=false`).
- Secrets live in **HF Space Settings**, never in the code/repo.

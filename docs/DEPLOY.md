# Production Deployment Runbook

Single-VPS deployment (modular monolith) behind Caddy with auto-TLS. All commands
run from the repo root on the VPS unless noted.

## 0. Free-tier deployment (zero purchase)

You do **not** need to buy a server, a database, or a domain. The whole stack
(Postgres + TimescaleDB, Redis, API, worker, web, Caddy) runs on a single
**always-free** cloud VM with no recurring charge.

**Recommended: Oracle Cloud "Always Free" VM.** Free *forever* (not a trial):
an Ampere ARM `VM.Standard.A1.Flex` with up to **4 OCPU / 24 GB RAM** + 200 GB
storage + a public IPv4. That is far more than this stack needs.
1. Create an Oracle Cloud account (a card is required for identity check; Always
   Free resources never bill). Launch an `A1.Flex` Ubuntu 22.04 instance.
   *If ARM capacity is "out of host capacity" in your region, use the Always-Free
   AMD `E2.1.Micro` (1 GB RAM) instead and add swap — see the 1 GB note below.*
2. In the instance's **VCN → Security List**, add ingress rules for TCP **80** and
   **443** from `0.0.0.0/0`. Then on the box: `sudo iptables -I INPUT 6 -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT` (and `:80`), `sudo netfilter-persistent save` (Oracle images ship a restrictive iptables).
3. Install Docker + Compose v2: `curl -fsSL https://get.docker.com | sh`.
4. Get a **free domain + TLS** (pick one):
   - **DuckDNS** (simplest): register a free `yourname.duckdns.org` subdomain,
     point it at the VM's public IP. Caddy then gets a real Let's Encrypt cert
     automatically over port 80/443. Set `DOMAIN=yourname.duckdns.org`.
   - **Cloudflare Tunnel** (works even with no public IP / behind NAT): run
     `cloudflared` on the VM; Cloudflare terminates TLS at its edge. Use this if
     you can't open ports 80/443. (Then Caddy can serve plain HTTP internally.)
5. Deploy exactly as in §2–§3 below — the same `infra/deploy.sh`. **Total cost: $0.**

**Other always-free VMs (fallbacks):** Google Cloud `e2-micro` (always free in
`us-west1/us-central1/us-east1`, 1 GB RAM, 30 GB disk); AWS/Azure micro tiers are
free for **12 months only**, then they bill — prefer Oracle/GCP for "free forever".

**1 GB RAM note:** the full stack is comfortable in ~1.5–2 GB. On a 1 GB box, add
swap first: `sudo fallocate -l 3G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile && echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab`. The Oracle ARM box (24 GB) needs none of this.

**Alternative — split across managed free tiers (more moving parts):** host the
Next.js web on **Vercel** (Hobby, free) and Redis on **Upstash** (free). The catch
is the database: this app uses TimescaleDB (hypertables + `time_bucket`), which the
free Postgres tiers (Neon/Supabase) do **not** provide, so the schema migration
fails there. Free managed *Timescale* is trial-only. → For a no-purchase deploy,
the single Always-Free VM above is strictly simpler and keeps real TimescaleDB.

> Finish building/testing locally first (`just bootstrap` …). Deploy when ready —
> the steps below are identical on a paid VPS or a free Oracle/GCP VM.

## 1. Provision
- A small Linux VPS (2 vCPU / 4 GB is plenty to start), Docker + Compose v2 installed.
- A domain (e.g. `trade.example.com`) with an **A record → the VPS IP**.
- Open ports **80** and **443** only.

## 2. Configure
```bash
git clone <repo> && cd "AI Powered Trading System"
cp infra/.env.prod.example infra/.env.prod
# Fill in: DOMAIN, APP_SECRET_KEY, BROKER_CRED_KEY, POSTGRES_PASSWORD,
# DATABASE_URL (use that password), CORS_ALLOW_ORIGINS=https://DOMAIN, GEMINI_API_KEY.
```
Generate secrets:
```bash
python -c "import secrets;print(secrets.token_urlsafe(48))"                      # APP_SECRET_KEY
python -c "import base64,nacl.utils;print(base64.b64encode(nacl.utils.random(32)).decode())"  # BROKER_CRED_KEY
```

## 3. First deploy
```bash
./infra/deploy.sh        # builds images, runs migrations, starts the stack
docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod run --rm api python -m app.cli.seed
```
Caddy obtains TLS automatically; the app is live at `https://DOMAIN`.

## 4. Observability (opt-in)
```bash
docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod --profile observability up -d
```
Prometheus scrapes `api:/metrics`; Promtail ships container logs to Loki; Grafana
(behind your own tunnel/VPN — not exposed by Caddy) has both datasources provisioned.
Retention is capped (Prometheus 15d, Loki 7d) to bound the VPS disk.
*Follow-up:* add OpenTelemetry traces (Tempo) + the trading SLI alerts.

## 5. Backups & recovery
- Nightly: `infra/backup.sh` via cron → `pg_dump` to a restic repo (B2/R2/S3).
- **RPO/RTO:** nightly dumps alone risk up to 24h loss. For the trade/audit ledger,
  also enable **Postgres WAL archiving / PITR** (archive WAL to object storage) to get
  RPO ≈ 0. Target RTO ≤ 1h via the re-provision steps below.
- **Restore drill (do this before you rely on it):**
  ```bash
  restic restore latest --target /tmp/restore
  docker compose ... exec -T db pg_restore -U trading -d trading --clean /tmp/restore/<dump>
  ```

## 6. Rollback
```bash
git checkout <previous-sha> && ./infra/deploy.sh   # SHA-pinned images + expand-contract migrations
```

## 7. Re-provision (VPS lost)
1. New VPS + Docker; restore DNS A record.
2. `git clone`, restore `infra/.env.prod` (from your secrets store) and the **age/restic keys**.
3. `./infra/deploy.sh`; restore Postgres from restic (step 5); verify `/health` + `/ready`.

## Notes
- Live (real-money) trading is **disabled** (`LIVE_TRADING_ENABLED=false`) and gated in
  code; do not enable without the 2FA/kill-switch/audit control stack.
- Scale-out (PgBouncer, a dedicated worker host, blue/green) is deferred until load warrants it.

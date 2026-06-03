# Production Deployment Runbook

Single-VPS deployment (modular monolith) behind Caddy with auto-TLS. All commands
run from the repo root on the VPS unless noted.

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

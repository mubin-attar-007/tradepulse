#!/usr/bin/env bash
# Nightly Postgres backup -> restic (Backblaze B2 / Cloudflare R2 / S3).
# Cron (on the VPS):  0 3 * * *  /path/to/repo/infra/backup.sh >> /var/log/tp-backup.log 2>&1
# For near-zero RPO on the trade/audit ledger, ALSO enable Postgres WAL archiving /
# PITR (see docs/DEPLOY.md) — a nightly dump alone risks up to 24h of loss.
set -euo pipefail
cd "$(dirname "$0")"

# shellcheck disable=SC1091
set -a; [ -f .env.prod ] && . ./.env.prod; set +a

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP="/tmp/trading-${STAMP}.dump"

docker compose -f compose.prod.yaml --env-file .env.prod exec -T db \
	pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc >"${DUMP}"

restic backup "${DUMP}" --tag postgres
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
rm -f "${DUMP}"
echo "Backup ${STAMP} complete."

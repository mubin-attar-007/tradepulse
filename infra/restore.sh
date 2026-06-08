#!/usr/bin/env bash
# Restore VERIFICATION: prove the latest backup is actually usable.
# Restores the most recent restic snapshot into a THROWAWAY database, runs a smoke check,
# then drops it. A backup you've never restored is a hope, not a backup.
# Run monthly (and after any change to backup.sh):  /path/to/repo/infra/restore.sh
set -euo pipefail
cd "$(dirname "$0")"

# shellcheck disable=SC1091
set -a; [ -f .env.prod ] && . ./.env.prod; set +a

VERIFY_DB="restore_verify_$(date -u +%Y%m%d%H%M%S)"
RESTORE_DIR="/tmp/tp-restore-$$"
mkdir -p "${RESTORE_DIR}"

compose() { docker compose -f compose.prod.yaml --env-file .env.prod "$@"; }

cleanup() {
	compose exec -T db dropdb -U "${POSTGRES_USER}" --if-exists "${VERIFY_DB}" || true
	rm -rf "${RESTORE_DIR}"
}
trap cleanup EXIT

echo "Restoring latest restic snapshot (tag postgres)..."
restic restore latest --tag postgres --target "${RESTORE_DIR}"
DUMP="$(find "${RESTORE_DIR}" -name 'trading-*.dump' | sort | tail -n1)"
[ -n "${DUMP}" ] || { echo "FAIL: no dump found in the restored snapshot"; exit 1; }

echo "Creating throwaway DB ${VERIFY_DB} and restoring ${DUMP}..."
compose exec -T db createdb -U "${POSTGRES_USER}" "${VERIFY_DB}"
compose exec -T db pg_restore -U "${POSTGRES_USER}" -d "${VERIFY_DB}" --no-owner <"${DUMP}"

echo "Smoke check: counting restored public tables..."
COUNT="$(compose exec -T db psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -tAc \
	"SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
COUNT="$(echo "${COUNT}" | tr -d '[:space:]')"
echo "Restored public tables: ${COUNT}"
[ "${COUNT}" -gt 0 ] || { echo "FAIL: restore produced no tables"; exit 1; }

echo "Restore verification OK — backup is restorable (${COUNT} tables)."

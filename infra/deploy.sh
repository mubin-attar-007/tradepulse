#!/usr/bin/env bash
# One-command deploy on the VPS: pull, build, migrate, restart, prune.
# Migrations use expand-contract (additive) so a rolling restart is safe.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod)

git pull --ff-only
"${COMPOSE[@]}" build
"${COMPOSE[@]}" run --rm api alembic upgrade head
"${COMPOSE[@]}" up -d
docker image prune -f

echo "Deployed $(git rev-parse --short HEAD)."
echo "Roll back: git checkout <prev-sha> && infra/deploy.sh"

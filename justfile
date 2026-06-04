# Trading Platform task runner. Run `just` to list recipes.
# On Windows, recipes run under PowerShell 7 (pwsh). The app reads `.env` itself
# (pydantic-settings), so we deliberately do NOT dotenv-load here — that would
# leak the dev DATABASE_URL into the test process.
set windows-shell := ["pwsh.exe", "-NoLogo", "-Command"]

# List available recipes
default:
    @just --list

# One command: clone -> running stack with REAL seeded + backfilled data
bootstrap:
    uv sync && just up && just migrate && just seed-demo
    @echo "Bootstrap complete. Run 'just api', 'just worker', and 'just web'."

# Seed the universe + pull real recent bars (best-effort: crypto via CCXT needs no
# key; equities via yfinance. A failing provider is tolerated so bootstrap still succeeds).
seed-demo:
    just seed
    -just backfill BTC/USD 2
    -just backfill ETH/USD 2
    -just backfill SPY 5

# --- Infra ---
up:
    docker compose up -d --wait
down:
    docker compose down
logs:
    docker compose logs -f

# --- Backend ---
api:
    uv run uvicorn app.main:app --reload --app-dir apps/api --host 0.0.0.0 --port 8080
worker:
    uv run arq app.worker.WorkerSettings
migrate:
    uv run alembic upgrade head
makemigration message:
    uv run alembic revision --autogenerate -m "{{message}}"
seed:
    uv run python -m app.cli.seed
backfill symbol days="2":
    uv run python -m app.cli.backfill {{symbol}} --days {{days}}
openapi:
    uv run python -m app.cli.export_openapi

# --- Frontend ---
web:
    npm --prefix apps/web run dev
gen-api:
    npm --prefix apps/web run gen:api

# --- Quality ---
fmt:
    uv run ruff format apps/api && uv run ruff check --fix apps/api
lint:
    uv run ruff check apps/api && uv run ruff format --check apps/api
typecheck:
    uv run mypy apps/api/app && uv run lint-imports
test:
    uv run pytest
check: lint typecheck test

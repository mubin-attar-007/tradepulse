# Trading Platform task runner. Run `just` to list recipes.
# On Windows, recipes run under PowerShell 7 (pwsh). The app reads `.env` itself
# (pydantic-settings), so we deliberately do NOT dotenv-load here — that would
# leak the dev DATABASE_URL into the test process.
set windows-shell := ["pwsh.exe", "-NoLogo", "-Command"]

# List available recipes
default:
    @just --list

# One command: clone -> running stack (deps, containers, migrations)
bootstrap:
    uv sync && just up && just migrate
    @echo "Bootstrap complete. Run 'just api' and 'just web'."

# --- Infra ---
up:
    docker compose up -d --wait
down:
    docker compose down
logs:
    docker compose logs -f

# --- Backend ---
api:
    uv run uvicorn app.main:app --reload --app-dir apps/api --host 0.0.0.0 --port 8000
worker:
    uv run arq app.worker.WorkerSettings
migrate:
    uv run alembic upgrade head
makemigration message:
    uv run alembic revision --autogenerate -m "{{message}}"
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

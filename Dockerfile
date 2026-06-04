# Hugging Face Spaces (Docker SDK) image — runs the API + AI in one container.
# HF builds this from the repo root and routes HTTPS to app_port 7860 (see the
# README frontmatter). The database (Neon) and Redis (Upstash) are external;
# secrets go in the Space's Settings -> Variables and secrets. Migrations run on
# start. The VM/Compose deploy uses infra/Dockerfile.api instead — this file is
# HF-specific (HF requires a Dockerfile named `Dockerfile` at the repo root).
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock alembic.ini README.md ./
COPY apps/api ./apps/api
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/apps/api" \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser \
    APP_ENV=production \
    LOG_JSON=true \
    COOKIE_SECURE=true \
    METRICS_ENABLED=false \
    AI_DEFAULT_PROVIDER=gemini \
    GEMINI_MODEL=gemini-2.0-flash \
    LIVE_TRADING_ENABLED=false
USER appuser
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:7860/health').status==200 else 1)"
# Migrate (Neon), seed the instrument universe (idempotent — HF has no shell),
# then serve on the HF Spaces port.
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli.seed && uvicorn app.main:app --host 0.0.0.0 --port 7860"]

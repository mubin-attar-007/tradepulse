"""Test fixtures: isolated test DB (`trading_test`) + Redis db 1, per-test reset.

Env is pointed at isolated resources BEFORE importing app code. The global
engine/redis are disposed after each test so the next test rebinds to its own
event loop (avoids cross-loop asyncpg errors with function-scoped loops).
"""

from __future__ import annotations

import asyncio
import base64
import os
from collections.abc import AsyncIterator, Iterator

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://trading:trading@localhost:55432/trading_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:56379/1")
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000000"  # don't throttle tests
os.environ["METRICS_ENABLED"] = "false"  # avoid duplicate Prometheus collectors per app
# Dev-only 32-byte key (base64) for broker-credential encryption tests.
os.environ.setdefault("BROKER_CRED_KEY", base64.b64encode(b"0" * 32).decode())

import asyncpg
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

get_settings.cache_clear()

# Every domain table, truncated between tests. Listing them explicitly (rather than
# reflecting) makes a forgotten table a visible omission in review: a table missing
# here leaks rows across tests and produces order-dependent failures that are
# miserable to diagnose.
_TABLES = (
    "users, user_credentials, broker_connections, audit_log, ohlcv, "
    "instrument_sources, instruments, paper_sessions, alerts, backtests, experiments, "
    "strategy_versions, strategies"
)


async def _create_test_db_and_schema() -> None:
    settings = get_settings()
    admin_dsn = settings.database_url.replace("+asyncpg", "").replace("/trading_test", "/trading")
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'trading_test'")
        if not exists:
            await conn.execute("CREATE DATABASE trading_test")
    finally:
        await conn.close()

    import app.models  # noqa: F401  (register models)
    from app.core.db import Base

    engine = create_async_engine(settings.database_url)
    async with engine.begin() as connection:
        # time_bucket / first / last used by the bar reads require the extension.
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _prepare_db() -> Iterator[None]:
    asyncio.run(_create_test_db_and_schema())
    yield


@pytest_asyncio.fixture(autouse=True)
async def _reset_state(_prepare_db: None) -> AsyncIterator[None]:
    from app.core.db import dispose_engine, get_sessionmaker
    from app.core.redis import close_redis, get_redis_client

    async with get_sessionmaker()() as session:
        await session.execute(text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
        await session.commit()
    await get_redis_client().flushdb()
    yield
    await dispose_engine()
    await close_redis()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[object]:
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def authenticate(
    client: AsyncClient,
    email: str = "test@example.com",
    password: str = "password123",
) -> Response:
    """Register (or log in) and arm the client for state-changing requests.

    Cookie-authenticated unsafe requests must carry the double-submit CSRF header,
    so a test client that only holds the session cookie is not actually a signed-in
    browser — it is exactly the shape of request the protection exists to reject.
    This helper mirrors what the frontend does: read the JS-readable ``csrf_token``
    cookie and echo it in ``X-CSRF-Token`` on every later call.
    """
    from app.core.security import CSRF_COOKIE, CSRF_HEADER

    response = await client.post("/auth/register", json={"email": email, "password": password})
    if response.status_code >= 400:
        response = await client.post("/auth/login", json={"email": email, "password": password})
    token = client.cookies.get(CSRF_COOKIE)
    if token:
        client.headers[CSRF_HEADER] = token
    return response

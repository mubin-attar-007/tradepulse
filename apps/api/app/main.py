"""FastAPI application factory (API process entrypoint).

Boots the platform kernel (logging, error handlers, middleware) and mounts
domain routers. The same package is reused by the ARQ worker (:mod:`app.worker`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import dispose_engine, get_sessionmaker
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.observability import init_sentry
from app.core.ratelimit import RateLimitMiddleware
from app.core.redis import close_redis, get_redis_client
from app.core.security import SecurityHeadersMiddleware
from app.modules.ai.router import router as ai_router
from app.modules.auth.router import router as auth_router
from app.modules.market_data.realtime import close_hub
from app.modules.market_data.router import router as market_router
from app.modules.strategies.router import router as strategies_router
from app.modules.trading.router import router as trading_router

logger = get_logger("app")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info("startup", env=get_settings().app_env)
    yield
    await close_hub()
    await close_redis()
    await dispose_engine()
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    init_sentry()

    app = FastAPI(
        title="Trading Platform API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    install_error_handlers(app)

    # Added inner->outer; execution order becomes CORS -> RequestContext -> RateLimit -> Security.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.get("/health", tags=["system"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env}

    @app.get("/ready", tags=["system"], summary="Readiness probe (DB + Redis)")
    async def ready() -> JSONResponse:
        checks = {"db": False, "redis": False}
        try:
            async with get_sessionmaker()() as session:
                await session.execute(text("SELECT 1"))
            checks["db"] = True
        except Exception:
            logger.warning("ready_db_failed")
        try:
            await get_redis_client().ping()
            checks["redis"] = True
        except Exception:
            logger.warning("ready_redis_failed")
        ok = all(checks.values())
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ready" if ok else "degraded", "checks": checks},
        )

    app.include_router(auth_router)
    app.include_router(market_router)
    app.include_router(strategies_router)
    app.include_router(ai_router)
    app.include_router(trading_router)
    return app


app = create_app()

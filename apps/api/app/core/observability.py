"""Error tracking (Sentry). Full OTel/Prometheus/Grafana stack is Phase 9.

Seeded now so later phases inherit error capture for free; no-op without a DSN.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("observability")


def init_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
    logger.info("sentry_initialized", environment=settings.app_env)

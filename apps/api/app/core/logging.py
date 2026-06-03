"""Structured logging (structlog) — JSON in prod, pretty console locally.

Every line is enriched with ``request_id`` / ``user_id`` from the context vars
so logs are correlatable; this is the seam Phase 9 hardens into full OTel.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings
from app.core.context import request_id_var, user_id_var

EventDict = dict[str, Any]


def _add_request_context(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    if (rid := request_id_var.get()) is not None:
        event_dict["request_id"] = rid
    if (uid := user_id_var.get()) is not None:
        event_dict["user_id"] = uid
    return event_dict


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_request_context,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)

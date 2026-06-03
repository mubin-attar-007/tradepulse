"""Alembic environment (async). URL + metadata come from the app itself.

Importing ``app.models`` registers every ORM model on ``Base.metadata`` so
autogenerate sees the full schema. TimescaleDB internal schemas are excluded so
autogenerate never tries to drop Timescale-managed objects (Phase 2 relevance).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  (side effect: register models on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.core.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_TIMESCALE_SCHEMAS = {
    "_timescaledb_internal",
    "_timescaledb_catalog",
    "_timescaledb_config",
    "timescaledb_information",
    "timescaledb_experimental",
}


def include_object(obj: Any, _name: str, type_: str, _reflected: bool, _compare_to: Any) -> bool:
    return not (type_ == "table" and getattr(obj, "schema", None) in _TIMESCALE_SCHEMAS)


def _do_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_async_engine(get_settings().database_url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

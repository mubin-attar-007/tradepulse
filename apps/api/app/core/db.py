"""Async SQLAlchemy 2.0 engine, session, declarative base, and shared mixins.

The ``get_session`` dependency provides a request-scoped unit of work that
commits on success and rolls back on error. ``Base`` carries a naming
convention so Alembic produces stable, explicit constraint names.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import ForeignKey, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Fetch server-generated defaults (created_at/updated_at) via RETURNING on
    # INSERT so they're populated without a sync lazy-load (avoids MissingGreenlet).
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012  (SQLAlchemy config dunder)


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class OwnerMixin:
    """Tenancy seam: every user-owned row carries ``owner_id`` (invariant #1)."""

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


class OwnedEntity(Base, UUIDPrimaryKey, TimestampMixin, OwnerMixin):
    """Abstract base for owner-scoped domain entities (used by OwnedRepository)."""

    __abstract__ = True


# --- Engine / session (lazily created singletons) ---------------------------
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# libpq URL params that managed providers (Neon/Supabase) append but the asyncpg
# driver does not accept as connect kwargs.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "target_session_attrs"}


def _async_engine_args(raw_url: str) -> tuple[str, dict[str, object]]:
    """Normalize a Postgres URL for asyncpg: ensure the ``+asyncpg`` scheme and
    translate libpq-only query params (``sslmode``/``channel_binding``) — which
    asyncpg rejects — into an SSL connect arg. A plain local URL is unchanged, so
    this lets a Neon/Supabase connection string work by only swapping the scheme."""
    parts = urlsplit(raw_url)
    scheme = "postgresql+asyncpg" if parts.scheme in {"postgres", "postgresql"} else parts.scheme
    connect_args: dict[str, object] = {}
    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() == "sslmode":
            if value.lower() in {"require", "verify-ca", "verify-full", "prefer", "allow"}:
                connect_args["ssl"] = True
        elif key.lower() not in _LIBPQ_ONLY_PARAMS:
            kept.append((key, value))
    url = urlunsplit((scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))
    return url, connect_args


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url, connect_args = _async_engine_args(get_settings().database_url)
        _engine = create_async_engine(
            url, pool_pre_ping=True, future=True, connect_args=connect_args
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped unit of work (commit on success, rollback on error)."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None

"""Paper-trading ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import OwnedEntity


class PaperSession(OwnedEntity):
    __tablename__ = "paper_sessions"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    strategy_version: Mapped[int]
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    initial_cash: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | stopped
    session_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)  # StrategySpec snapshot at deploy
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, default=None
    )  # latest run result


class Alert(OwnedEntity):
    """A queryable record of a fired paper-trading alert.

    Today fills/RiskEvents live only inside the paper-session JSONB snapshot; this
    promotes each NEW event to a durable row so it can be listed in the feed and,
    critically, so the snapshot-diff dispatcher is IDEMPOTENT: the cron runs every
    ~30s cross-owner, so before emailing we check whether an Alert with the same
    ``dedup_key`` already exists. The unique constraint on (session_id, dedup_key)
    is the hard guarantee against double-firing even under a race.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("session_id", "dedup_key", name="uq_alerts_session_id_dedup_key"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_sessions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))  # entry | exit | risk_event
    symbol: Mapped[str] = mapped_column(String(32))
    # Stable identity of the underlying event (e.g. "entry:<iso-ts>", "exit:<iso-ts>",
    # "risk:<kind>:<iso-ts>") — the dedup handle the cron keys off of.
    dedup_key: Mapped[str] = mapped_column(String(128))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)  # event specifics (price/qty/reason/...)

"""Persisted backtest runs (owner-scoped). Result stored as a JSONB snapshot."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import OwnedEntity


class Backtest(OwnedEntity):
    __tablename__ = "backtests"

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    strategy_version: Mapped[int]
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="done")  # done | failed
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    error: Mapped[str | None] = mapped_column(String(500), default=None)

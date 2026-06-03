"""Paper-trading ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String
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

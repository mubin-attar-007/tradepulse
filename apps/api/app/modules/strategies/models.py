"""Strategy ORM models. Versions are immutable + append-only (reproducibility):
each saved spec change creates a new version stamped with spec_hash + engine_version.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import OwnedEntity


class Strategy(OwnedEntity):
    __tablename__ = "strategies"

    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|backtested|paper
    latest_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class StrategyVersion(OwnedEntity):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strategy_versions_strategy_version"),
    )

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)  # validated against StrategySpec
    spec_hash: Mapped[str] = mapped_column(String(64), index=True)
    engine_version: Mapped[str] = mapped_column(String(16))

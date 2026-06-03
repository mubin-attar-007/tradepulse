"""Append-only audit log model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKey


class AuditLog(Base, UUIDPrimaryKey):
    __tablename__ = "audit_log"

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), default=None)
    entity_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip: Mapped[str | None] = mapped_column(String(64), default=None)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

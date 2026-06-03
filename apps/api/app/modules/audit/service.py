"""Audit recording. Append-only: rows are inserted, never updated/deleted."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


async def record(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ip: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            action=action,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            ip=ip,
            payload=payload,
        )
    )
    await session.flush()

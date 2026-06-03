"""Owner-scoped base repository — the single data-access path for tenancy.

Every query is filtered by ``owner_id`` and every insert stamps it from the
repository's owner (never from caller input), so cross-tenant access is
impossible by construction (invariant #1). A cross-tenant test guards this.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import OwnedEntity


class OwnedRepository[ModelT: OwnedEntity]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id

    def _owned(self):  # type: ignore[no-untyped-def]
        return select(self.model).where(self.model.owner_id == self.owner_id)

    async def get(self, id_: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(self._owned().where(self.model.id == id_))
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        result = await self.session.execute(self._owned().limit(limit).offset(offset))
        return result.scalars().all()

    async def add(self, obj: ModelT) -> ModelT:
        obj.owner_id = self.owner_id  # authoritative: derive ownership from the repo, not input
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)

"""Owner-scoped experiment access."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.core.repository import OwnedRepository
from app.modules.experiments.models import Experiment


class ExperimentRepository(OwnedRepository[Experiment]):
    model = Experiment

    async def list_for_owner(
        self, *, kind: str | None = None, strategy_id: uuid.UUID | None = None, limit: int = 50
    ) -> Sequence[Experiment]:
        stmt = self._owned().order_by(Experiment.created_at.desc()).limit(limit)
        if kind is not None:
            stmt = stmt.where(Experiment.kind == kind)
        if strategy_id is not None:
            stmt = stmt.where(Experiment.strategy_id == strategy_id)
        return (await self.session.execute(stmt)).scalars().all()

    async def lineage(self, experiment_id: uuid.UUID) -> Sequence[Experiment]:
        """Every experiment that names this one as its parent (reruns, follow-ups)."""
        stmt = (
            self._owned()
            .where(Experiment.parent_id == experiment_id)
            .order_by(Experiment.created_at)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def by_fingerprint(self, data_fingerprint: str, spec_hash: str) -> Sequence[Experiment]:
        """Prior runs of the SAME spec over the SAME data.

        Used to answer "has this exact question already been asked?" before spending
        compute, and to make repeated identical runs visible as repeated trials
        rather than independent confirmations.
        """
        stmt = self._owned().where(
            Experiment.data_fingerprint == data_fingerprint,
            Experiment.spec_hash == spec_hash,
            Experiment.status == "done",
        )
        return (await self.session.execute(stmt)).scalars().all()


async def count_trials(session, owner_id: uuid.UUID, spec_hash: str) -> int:  # type: ignore[no-untyped-def]
    """How many completed experiments this owner has run against a given spec hash.

    Feeds the multiple-testing correction: the number of trials that matters is not
    just the size of one grid, but how many times the researcher has been back to
    the same question.
    """
    stmt = select(Experiment.id).where(
        Experiment.owner_id == owner_id,
        Experiment.spec_hash == spec_hash,
        Experiment.status == "done",
    )
    return len((await session.execute(stmt)).scalars().all())

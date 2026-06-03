"""Owner-scoped backtest repository."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.repository import OwnedRepository
from app.modules.backtesting.models import Backtest


class BacktestRepository(OwnedRepository[Backtest]):
    model = Backtest

    async def list_for_owner(self, *, limit: int = 50) -> Sequence[Backtest]:
        result = await self.session.execute(
            self._owned().order_by(Backtest.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

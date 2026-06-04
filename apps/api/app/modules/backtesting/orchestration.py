"""Create + run + persist a backtest for a saved strategy.

Synchronous for MVP (backtests over our data sizes run sub-second). The seam to
move long runs / parameter sweeps onto an ARQ job is the same pattern paper
trading already uses; deferred until a run is measurably slow.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.modules.backtesting.models import Backtest
from app.modules.backtesting.repository import BacktestRepository
from app.modules.backtesting.service import run_backtest
from app.modules.backtesting.snapshot import result_to_dict
from app.modules.backtesting.types import ExecutionConfig
from app.modules.strategies.repository import StrategyRepository, StrategyVersionRepository
from app.modules.strategies.spec import StrategySpec

logger = get_logger("backtesting")


class BacktestService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self.repo = BacktestRepository(session, owner_id)

    async def run(
        self,
        strategy_id: uuid.UUID,
        start: datetime,
        end: datetime,
        config: ExecutionConfig | None = None,
    ) -> Backtest:
        strategy = await StrategyRepository(self.session, self.owner_id).get(strategy_id)
        if strategy is None:
            raise NotFoundError()
        version = await StrategyVersionRepository(self.session, self.owner_id).latest(strategy_id)
        if version is None:
            raise BadRequestError("Strategy has no version to backtest.")
        spec = StrategySpec.model_validate(version.spec)

        backtest = Backtest(
            strategy_id=strategy_id,
            strategy_version=version.version,
            spec=version.spec,
            symbol=spec.universe[0],
            timeframe=spec.timeframe,
            start_ts=start,
            end_ts=end,
            status="done",
        )
        try:
            result = await run_backtest(
                self.session, spec, start=start, end=end, config=config or ExecutionConfig()
            )
            backtest.result = result_to_dict(result)
        except (NotFoundError, BadRequestError) as exc:
            backtest.status = "failed"
            backtest.error = str(exc.detail)[:500]
        except Exception as exc:
            # Persist the failure (status='failed') instead of surfacing a 500.
            logger.exception("backtest_run_failed", strategy_id=str(strategy_id))
            backtest.status = "failed"
            backtest.error = str(exc)[:500]
        await self.repo.add(backtest)
        await self.session.flush()
        return backtest

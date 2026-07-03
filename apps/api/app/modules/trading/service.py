"""Paper-trading service. Deploy a strategy, then periodically re-run the SAME
engine over the session window (close_at_end=False) and snapshot the result.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.modules.auth.models import User
from app.modules.backtesting import engine
from app.modules.backtesting.snapshot import result_to_dict
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data import repository as md_repo
from app.modules.market_data.models import Instrument
from app.modules.strategies.repository import StrategyRepository, StrategyVersionRepository
from app.modules.strategies.spec import StrategySpec
from app.modules.trading.alerts import dispatch_snapshot_alerts
from app.modules.trading.models import PaperSession
from app.modules.trading.repository import AlertRepository, PaperSessionRepository

logger = get_logger("paper")
DEFAULT_CASH = Decimal("100000")


class PaperService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self.sessions = PaperSessionRepository(session, owner_id)
        self.alerts = AlertRepository(session, owner_id)

    async def deploy(self, strategy_id: uuid.UUID) -> PaperSession:
        strategy = await StrategyRepository(self.session, self.owner_id).get(strategy_id)
        if strategy is None:
            raise NotFoundError()
        version = await StrategyVersionRepository(self.session, self.owner_id).latest(strategy_id)
        if version is None:
            raise BadRequestError("Strategy has no version to deploy.")
        spec = StrategySpec.model_validate(version.spec)
        paper = PaperSession(
            strategy_id=strategy_id,
            strategy_version=version.version,
            symbol=spec.universe[0],
            timeframe=spec.timeframe,
            initial_cash=DEFAULT_CASH,
            status="running",
            session_start=datetime.now(UTC),
            spec=version.spec,
            snapshot=None,
        )
        await self.sessions.add(paper)
        strategy.status = "paper"
        await self.session.flush()
        return paper

    async def run_session(
        self, paper: PaperSession, *, start: datetime | None = None, end: datetime | None = None
    ) -> PaperSession:
        if paper.status != "running":
            return paper
        spec = StrategySpec.model_validate(paper.spec)
        instrument = await self.session.scalar(
            select(Instrument).where(Instrument.symbol == paper.symbol)
        )
        if instrument is None:
            return paper
        end = end or datetime.now(UTC)
        start = start or paper.session_start
        bars = await md_repo.get_bars(
            self.session, instrument.id, timeframe=spec.timeframe, start=start, end=end
        )
        if len(bars) >= 2:
            result = engine.run(
                spec,
                bars,
                ExecutionConfig(initial_cash=Decimal(paper.initial_cash)),
                close_at_end=False,
            )
            snapshot = result_to_dict(result, as_of=end)
            paper.snapshot = snapshot
            # Idempotent snapshot-diff: persist an Alert + email for each NEW fill /
            # RiskEvent (no-op when nothing changed; never double-fires — see alerts.py).
            email_to = await self.session.scalar(select(User.email).where(User.id == self.owner_id))
            await dispatch_snapshot_alerts(self.alerts, paper, snapshot, email_to=email_to)
        paper.last_run_at = end
        await self.session.flush()
        return paper

    async def stop(self, session_id: uuid.UUID) -> PaperSession:
        paper = await self.sessions.get(session_id)
        if paper is None:
            raise NotFoundError()
        paper.status = "stopped"
        await self.session.flush()
        return paper

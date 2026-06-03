"""Paper-trading service. Deploy a strategy, then periodically re-run the SAME
engine over the session window (close_at_end=False) and snapshot the result.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.modules.backtesting import engine
from app.modules.backtesting.types import BacktestResult, ExecutionConfig
from app.modules.market_data import repository as md_repo
from app.modules.market_data.models import Instrument
from app.modules.strategies.repository import StrategyRepository, StrategyVersionRepository
from app.modules.strategies.spec import StrategySpec
from app.modules.trading.models import PaperSession
from app.modules.trading.repository import PaperSessionRepository

logger = get_logger("paper")
DEFAULT_CASH = Decimal("100000")


def build_snapshot(result: BacktestResult, as_of: datetime) -> dict[str, Any]:
    return {
        "as_of": as_of.isoformat(),
        "initial_cash": str(result.initial_cash),
        "final_equity": str(result.final_equity),
        "open_position": result.open_position,
        "num_trades": len(result.trades),
        "total_commission": str(result.total_commission),
        "metrics": result.metrics,
        "risk_events": [
            {"ts": e.ts.isoformat(), "kind": e.kind, "detail": e.detail} for e in result.risk_events
        ],
        "trades": [
            {
                "entry_ts": t.entry_ts.isoformat(),
                "exit_ts": t.exit_ts.isoformat(),
                "side": t.side,
                "qty": str(t.qty),
                "entry_price": str(t.entry_price),
                "exit_price": str(t.exit_price),
                "pnl": str(t.pnl),
                "return_pct": t.return_pct,
                "exit_reason": t.exit_reason,
            }
            for t in result.trades[-50:]
        ],
        "equity_curve": [
            {"ts": p.ts.isoformat(), "equity": str(p.equity)} for p in result.equity_curve[-300:]
        ],
        "bars": result.bars,
    }


class PaperService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self.sessions = PaperSessionRepository(session, owner_id)

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
            paper.snapshot = build_snapshot(result, end)
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

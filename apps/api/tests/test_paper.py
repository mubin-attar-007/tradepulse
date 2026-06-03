"""Paper trading: deploy, backtest<->paper parity, stop, tenancy, endpoints."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient

from app.core.db import get_sessionmaker
from app.modules.auth.models import User
from app.modules.backtesting import engine
from app.modules.backtesting.types import ExecutionConfig
from app.modules.market_data import repository as md_repo
from app.modules.market_data.models import Instrument
from app.modules.market_data.providers.base import CanonicalBar
from app.modules.strategies.service import StrategyService
from app.modules.strategies.spec import (
    Comparison,
    ExitRule,
    IndicatorSpec,
    Operand,
    PositionSizing,
    RiskLimits,
    StrategySpec,
)
from app.modules.trading.service import PaperService

BASE = datetime(2024, 1, 2, 0, 0, tzinfo=UTC)


def _spec(symbol: str) -> StrategySpec:
    return StrategySpec(
        name="paper-sma",
        universe=[symbol],
        timeframe="1m",
        indicators=[IndicatorSpec(id="sma", type="SMA", params={"period": 3})],
        entry_long=Comparison(
            left=Operand(kind="price", field="close"),
            op=">",
            right=Operand(kind="indicator", ref="sma"),
        ),
        exit=ExitRule(stop_loss_pct=0.05, take_profit_pct=0.05, time_exit_bars=5),
        sizing=PositionSizing(method="percent_equity", value=0.5),
        risk=RiskLimits(max_position_pct=1.0, max_open_positions=1),
    )


async def _seed_bars(session: object, symbol: str, n: int = 40) -> Instrument:
    inst = await md_repo.get_or_create_instrument(
        session,
        symbol=symbol,
        asset_class="crypto",
        calendar="24x7",  # type: ignore[arg-type]
    )
    bars = []
    for i in range(n):
        close = 100 + 10 * math.sin(i / 5) + i * 0.1
        open_ = 100 + 10 * math.sin((i - 1) / 5) + (i - 1) * 0.1 if i > 0 else close
        bars.append(
            CanonicalBar(
                ts=BASE + timedelta(minutes=i),
                open=Decimal(str(round(open_, 4))),
                high=Decimal(str(round(max(open_, close) * 1.001, 4))),
                low=Decimal(str(round(min(open_, close) * 0.999, 4))),
                close=Decimal(str(round(close, 4))),
                volume=Decimal("100"),
                is_final=True,
                source="test",
            )
        )
    await md_repo.upsert_bars(session, inst.id, bars)  # type: ignore[arg-type]
    await session.commit()  # type: ignore[attr-defined]
    return inst


async def test_deploy_and_backtest_paper_parity() -> None:
    async with get_sessionmaker()() as s:
        user = User(email="paper@example.com")
        s.add(user)
        await s.flush()
        inst = await _seed_bars(s, "BTC/USD")
        spec = _spec("BTC/USD")
        strategy, _ = await StrategyService(s, user.id).create(spec)
        await s.commit()

        service = PaperService(s, user.id)
        paper = await service.deploy(strategy.id)
        assert strategy.status == "paper"

        end = BASE + timedelta(minutes=40)
        await service.run_session(paper, start=BASE, end=end)
        await s.commit()
        assert paper.snapshot is not None

        # Parity: the desk's equity equals a direct engine run over the same bars.
        bars = await md_repo.get_bars(s, inst.id, timeframe="1m", start=BASE, end=end)
        direct = engine.run(
            spec,
            bars,
            ExecutionConfig(initial_cash=Decimal(paper.initial_cash)),
            close_at_end=False,
        )
        assert paper.snapshot["final_equity"] == str(direct.final_equity)


async def test_owner_scoping() -> None:
    async with get_sessionmaker()() as s:
        a = User(email="a@example.com")
        b = User(email="b@example.com")
        s.add_all([a, b])
        await s.flush()
        await _seed_bars(s, "BTC/USD")
        strategy, _ = await StrategyService(s, a.id).create(_spec("BTC/USD"))
        await s.commit()
        paper = await PaperService(s, a.id).deploy(strategy.id)
        await s.commit()
        assert await PaperService(s, b.id).sessions.get(paper.id) is None


async def test_stop() -> None:
    async with get_sessionmaker()() as s:
        user = User(email="u@example.com")
        s.add(user)
        await s.flush()
        await _seed_bars(s, "BTC/USD")
        strategy, _ = await StrategyService(s, user.id).create(_spec("BTC/USD"))
        await s.commit()
        service = PaperService(s, user.id)
        paper = await service.deploy(strategy.id)
        await s.commit()
        assert (await service.stop(paper.id)).status == "stopped"


async def _login(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": "p@example.com", "password": "password123"})


async def test_paper_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/paper/sessions")).status_code == 401


async def test_deploy_endpoint(client: AsyncClient) -> None:
    async with get_sessionmaker()() as s:
        await _seed_bars(s, "BTC/USD")
    await _login(client)
    created = await client.post("/strategies", json=_spec("BTC/USD").model_dump(mode="json"))
    assert created.status_code == 201
    strategy_id = created.json()["strategy"]["id"]
    resp = await client.post("/paper/deploy", json={"strategy_id": strategy_id})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "running" and body["symbol"] == "BTC/USD"

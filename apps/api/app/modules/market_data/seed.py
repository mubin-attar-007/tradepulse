"""Seed a small starter universe of instruments + their vendor symbol mappings.

Idempotent. Crypto canonical symbols use USD; the Binance source maps to USDT
(its USD proxy). Equities map to yfinance (no-key) primary + Alpaca (keyed).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market_data import repository as repo
from app.modules.market_data.models import InstrumentSource

# (source, source_symbol, is_primary)
_SEED: list[dict[str, Any]] = [
    {
        "symbol": "AAPL",
        "asset_class": "equity",
        "name": "Apple Inc.",
        "exchange": "XNAS",
        "calendar": "XNYS",
        "sources": [("yfinance", "AAPL", True), ("alpaca", "AAPL", False)],
    },
    {
        "symbol": "MSFT",
        "asset_class": "equity",
        "name": "Microsoft Corp.",
        "exchange": "XNAS",
        "calendar": "XNYS",
        "sources": [("yfinance", "MSFT", True), ("alpaca", "MSFT", False)],
    },
    {
        "symbol": "SPY",
        "asset_class": "equity",
        "name": "SPDR S&P 500 ETF",
        "exchange": "XNYS",
        "calendar": "XNYS",
        "sources": [("yfinance", "SPY", True), ("alpaca", "SPY", False)],
    },
    {
        "symbol": "BTC/USD",
        "asset_class": "crypto",
        "name": "Bitcoin",
        "calendar": "24x7",
        "quote_currency": "USD",
        "sources": [("binance", "BTC/USDT", True)],
    },
    {
        "symbol": "ETH/USD",
        "asset_class": "crypto",
        "name": "Ethereum",
        "calendar": "24x7",
        "quote_currency": "USD",
        "sources": [("binance", "ETH/USDT", True)],
    },
]


async def seed_instruments(session: AsyncSession) -> int:
    for spec in _SEED:
        fields = {k: v for k, v in spec.items() if k != "sources"}
        instrument = await repo.get_or_create_instrument(session, **fields)
        for source, source_symbol, is_primary in spec["sources"]:
            exists = await session.scalar(
                select(InstrumentSource).where(
                    InstrumentSource.instrument_id == instrument.id,
                    InstrumentSource.source == source,
                )
            )
            if exists is None:
                session.add(
                    InstrumentSource(
                        instrument_id=instrument.id,
                        source=source,
                        source_symbol=source_symbol,
                        is_primary=is_primary,
                    )
                )
    await session.flush()
    return len(_SEED)

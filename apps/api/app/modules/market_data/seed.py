"""Seed a small starter universe of instruments + their vendor symbol mappings.

Idempotent and self-healing: each run reconciles every instrument's sources to
match the catalog below (upserting listed sources, dropping ones no longer
listed), so a provider switch (e.g. Binance -> Coinbase) is applied on the next
run with no manual DB edits. Crypto uses Coinbase (US-accessible — Binance's API
geo-blocks US-hosted servers); equities use yfinance (no-key) + Alpaca (keyed).
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
        "sources": [("coinbase", "BTC/USD", True)],
    },
    {
        "symbol": "ETH/USD",
        "asset_class": "crypto",
        "name": "Ethereum",
        "calendar": "24x7",
        "quote_currency": "USD",
        "sources": [("coinbase", "ETH/USD", True)],
    },
]


async def seed_instruments(session: AsyncSession) -> int:
    for spec in _SEED:
        fields = {k: v for k, v in spec.items() if k != "sources"}
        instrument = await repo.get_or_create_instrument(session, **fields)
        wanted: list[tuple[str, str, bool]] = spec["sources"]
        wanted_names = {source for source, _, _ in wanted}
        existing = list(
            await session.scalars(
                select(InstrumentSource).where(InstrumentSource.instrument_id == instrument.id)
            )
        )
        by_name = {row.source: row for row in existing}
        # Drop sources no longer in the catalog (e.g. a venue we moved off), so the
        # primary source stays correct after a provider switch.
        for row in existing:
            if row.source not in wanted_names:
                await session.delete(row)
        # Upsert the catalog's sources (idempotent + self-healing).
        for source, source_symbol, is_primary in wanted:
            current = by_name.get(source)
            if current is None:
                session.add(
                    InstrumentSource(
                        instrument_id=instrument.id,
                        source=source,
                        source_symbol=source_symbol,
                        is_primary=is_primary,
                    )
                )
            else:
                current.source_symbol = source_symbol
                current.is_primary = is_primary
    await session.flush()
    return len(_SEED)

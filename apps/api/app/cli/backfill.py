"""Backfill historical 1-minute bars for a seeded instrument.

Usage: ``uv run python -m app.cli.backfill BTC/USD --days 2``
(or ``just backfill BTC/USD``). Uses the instrument's primary source.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.logging import configure_logging
from app.modules.market_data import ingestion
from app.modules.market_data.models import Instrument, InstrumentSource
from app.modules.market_data.providers.factory import make_provider


async def _run(symbol: str, days: int) -> None:
    configure_logging()
    settings = get_settings()
    async with get_sessionmaker()() as session:
        instrument = await session.scalar(select(Instrument).where(Instrument.symbol == symbol))
        if instrument is None:
            raise SystemExit(f"Unknown instrument {symbol!r}. Run 'just seed' first.")
        source = await session.scalar(
            select(InstrumentSource).where(
                InstrumentSource.instrument_id == instrument.id,
                InstrumentSource.is_primary.is_(True),
            )
        )
        if source is None:
            raise SystemExit(f"No primary source configured for {symbol!r}.")

        provider = make_provider(source.source, settings)
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        try:
            result = await ingestion.backfill_instrument(
                session,
                instrument_id=instrument.id,
                source=source.source,
                provider=provider,
                source_symbol=source.source_symbol,
                start=start,
                end=end,
            )
        finally:
            close = getattr(provider, "close", None)
            if close is not None:
                await close()
    print(
        f"Backfilled {result.bars_written} bars for {symbol} "
        f"via {result.source} [{result.first_ts} .. {result.last_ts}]"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill 1-minute bars.")
    parser.add_argument("symbol", help="Canonical symbol, e.g. BTC/USD or AAPL")
    parser.add_argument("--days", type=int, default=2, help="Days of history to fetch")
    args = parser.parse_args()
    asyncio.run(_run(args.symbol, args.days))


if __name__ == "__main__":
    main()

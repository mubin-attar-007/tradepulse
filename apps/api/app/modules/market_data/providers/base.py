"""The normalized bar value object and the vendor-adapter contract.

Every venue (Alpaca equities, CCXT crypto, yfinance backfill) normalizes its
payloads into :class:`CanonicalBar` at the boundary: Decimal prices, tz-aware
UTC timestamps at bar OPEN, an explicit ``is_final`` flag, and provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CanonicalBar:
    ts: datetime  # bar OPEN time, tz-aware UTC (half-open [ts, ts + timeframe))
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_final: bool  # closed bars only ever drive decisions (invariant #3)
    source: str
    timeframe: str = "1m"


@runtime_checkable
class MarketDataProvider(Protocol):
    """Common interface for all market-data venues."""

    source: str

    async def fetch_bars(
        self, source_symbol: str, start: datetime, end: datetime
    ) -> list[CanonicalBar]:
        """Return closed 1-minute bars in ``[start, end)``, oldest first."""
        ...

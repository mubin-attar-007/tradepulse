"""Equity market data via yfinance (no API key).

Note the free-tier limit: 1-minute history is only available for ~the last 7
days. Good enough for a demo backfill; Alpaca (IEX) is the keyed path for deep history.
yfinance is synchronous, so calls run in a worker thread.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.modules.market_data.providers.base import CanonicalBar

SOURCE = "yfinance"
_MINUTE = 60


def frame_to_bars(df: Any, now: datetime) -> list[CanonicalBar]:
    """Normalize a yfinance OHLCV DataFrame (tz-aware index) to CanonicalBars."""
    bars: list[CanonicalBar] = []
    for idx, row in df.iterrows():
        ts = idx.to_pydatetime().astimezone(UTC)
        bars.append(
            CanonicalBar(
                ts=ts,
                open=Decimal(str(row["Open"])),
                high=Decimal(str(row["High"])),
                low=Decimal(str(row["Low"])),
                close=Decimal(str(row["Close"])),
                volume=Decimal(str(int(row["Volume"]))),
                is_final=(ts.timestamp() + _MINUTE) <= now.timestamp(),
                source=SOURCE,
            )
        )
    return bars


class YFinanceProvider:
    source = SOURCE

    def _download(self, symbol: str, start: datetime, end: datetime) -> Any:
        import yfinance as yf

        return yf.Ticker(symbol).history(start=start, end=end, interval="1m", auto_adjust=False)

    async def fetch_bars(
        self, source_symbol: str, start: datetime, end: datetime
    ) -> list[CanonicalBar]:
        df = await asyncio.to_thread(self._download, source_symbol, start, end)
        if df is None or df.empty:
            return []
        return frame_to_bars(df, datetime.now(UTC))

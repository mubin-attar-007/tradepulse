"""Equity market data via Alpaca (free IEX feed; requires API keys).

Historical bars are returned closed; the most recent may be the forming minute,
so ``is_final`` is derived from the close time. The keys live in settings and
are only required to instantiate this provider.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.market_data.providers.base import CanonicalBar

SOURCE = "alpaca"
_MINUTE = 60


def _to_bar(bar: Any, now: datetime) -> CanonicalBar:
    ts = bar.timestamp.astimezone(UTC)
    return CanonicalBar(
        ts=ts,
        open=Decimal(str(bar.open)),
        high=Decimal(str(bar.high)),
        low=Decimal(str(bar.low)),
        close=Decimal(str(bar.close)),
        volume=Decimal(str(bar.volume)),
        is_final=(ts.timestamp() + _MINUTE) <= now.timestamp(),
        source=SOURCE,
    )


class AlpacaProvider:
    source = SOURCE

    def __init__(self, api_key: str, api_secret: str) -> None:
        if not api_key or not api_secret:
            raise AppError("Alpaca API keys are not configured (ALPACA_API_KEY/SECRET).")
        from alpaca.data.historical import StockHistoricalDataClient

        self._client = StockHistoricalDataClient(api_key, api_secret)

    def _fetch(self, source_symbol: str, start: datetime, end: datetime) -> Any:
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        request = StockBarsRequest(
            symbol_or_symbols=source_symbol,
            timeframe=TimeFrame.Minute,
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
        return self._client.get_stock_bars(request)

    async def fetch_bars(
        self, source_symbol: str, start: datetime, end: datetime
    ) -> list[CanonicalBar]:
        timeout = get_settings().market_data_timeout_seconds
        barset = await asyncio.wait_for(
            asyncio.to_thread(self._fetch, source_symbol, start, end), timeout=timeout
        )
        rows = barset.data.get(source_symbol, [])
        now = datetime.now(UTC)
        return [_to_bar(bar, now) for bar in rows]

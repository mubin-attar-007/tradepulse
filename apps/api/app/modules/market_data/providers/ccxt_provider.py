"""Crypto market data via CCXT (public OHLCV — no API key needed).

Binance/Coinbase/etc. expose public 1-minute candles. The most recent candle a
venue returns may be the still-forming minute, so we set ``is_final`` from the
bar's close time vs. now (the bar-lifecycle contract).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import ccxt.async_support as ccxt

from app.modules.market_data.providers.base import CanonicalBar

_MINUTE_MS = 60_000


def row_to_bar(row: list[Any], source: str, now_ms: int) -> CanonicalBar:
    """Normalize a CCXT OHLCV row ``[ts_ms, o, h, l, c, v]`` to a CanonicalBar."""
    ts_ms, open_, high, low, close, volume = row
    return CanonicalBar(
        ts=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
        is_final=(ts_ms + _MINUTE_MS) <= now_ms,
        source=source,
    )


class CcxtProvider:
    def __init__(self, exchange_id: str = "binance", *, client: Any | None = None) -> None:
        self.source = exchange_id
        self._client = (
            client if client is not None else getattr(ccxt, exchange_id)({"enableRateLimit": True})
        )

    async def fetch_bars(
        self, source_symbol: str, start: datetime, end: datetime
    ) -> list[CanonicalBar]:
        since = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        bars: list[CanonicalBar] = []
        while since < end_ms:
            rows = await self._client.fetch_ohlcv(
                source_symbol, timeframe="1m", since=since, limit=1000
            )
            if not rows:
                break
            for row in rows:
                if row[0] >= end_ms:
                    break
                bars.append(row_to_bar(row, self.source, now_ms))
            last_ts = rows[-1][0]
            if last_ts < since:  # no forward progress
                break
            since = last_ts + _MINUTE_MS
        return bars

    async def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()

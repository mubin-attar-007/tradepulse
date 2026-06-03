"""Vendor adapter normalization (hermetic — no network)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from app.modules.market_data.providers.ccxt_provider import CcxtProvider, row_to_bar
from app.modules.market_data.providers.yfinance_provider import frame_to_bars

# 2024-01-02 15:00:00 UTC in epoch ms.
TS_MS = int(datetime(2024, 1, 2, 15, 0, tzinfo=UTC).timestamp() * 1000)


def test_ccxt_row_to_bar_normalizes() -> None:
    bar = row_to_bar([TS_MS, 100.0, 101.5, 99.0, 100.5, 12.3], "binance", TS_MS + 120_000)
    assert bar.ts == datetime(2024, 1, 2, 15, 0, tzinfo=UTC)
    assert bar.open == Decimal("100.0")
    assert bar.high == Decimal("101.5")
    assert bar.close == Decimal("100.5")
    assert bar.volume == Decimal("12.3")
    assert bar.source == "binance"
    assert bar.is_final is True  # closed: now is 2 min past the bar open


def test_ccxt_row_marks_unclosed_bar_forming() -> None:
    bar = row_to_bar([TS_MS, 1, 1, 1, 1, 1], "binance", TS_MS + 30_000)  # only 30s in
    assert bar.is_final is False


class _FakeCcxtClient:
    def __init__(self, rows: list[list[Any]]) -> None:
        self._rows = rows

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int, limit: int
    ) -> list[list[Any]]:
        return [r for r in self._rows if r[0] >= since][:limit]


async def test_ccxt_provider_fetches_and_normalizes() -> None:
    rows = [[TS_MS + i * 60_000, 100 + i, 101 + i, 99 + i, 100 + i, 5] for i in range(5)]
    provider = CcxtProvider("binance", client=_FakeCcxtClient(rows))
    start = datetime.fromtimestamp(TS_MS / 1000, tz=UTC)
    end = datetime.fromtimestamp((TS_MS + 5 * 60_000) / 1000, tz=UTC)
    bars = await provider.fetch_bars("BTC/USDT", start, end)
    assert len(bars) == 5
    assert [b.ts for b in bars] == [
        datetime.fromtimestamp((TS_MS + i * 60_000) / 1000, tz=UTC) for i in range(5)
    ]
    assert all(b.is_final for b in bars)


def test_yfinance_frame_to_bars() -> None:
    index = pd.to_datetime(["2024-01-02 15:00:00+00:00", "2024-01-02 15:01:00+00:00"])
    df = pd.DataFrame(
        {
            "Open": [100, 101],
            "High": [102, 103],
            "Low": [99, 100],
            "Close": [101, 102],
            "Volume": [1000, 2000],
        },
        index=index,
    )
    bars = frame_to_bars(df, datetime(2024, 1, 2, 16, 0, tzinfo=UTC))
    assert len(bars) == 2
    assert bars[0].open == Decimal("100")
    assert bars[0].close == Decimal("101")
    assert bars[0].volume == Decimal("1000")
    assert all(b.is_final for b in bars)

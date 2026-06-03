"""Async token-bucket rate limiter."""

from __future__ import annotations

import time

import pytest

from app.modules.market_data.throttle import AsyncTokenBucket


async def test_bucket_throttles_beyond_capacity() -> None:
    bucket = AsyncTokenBucket(rate_per_sec=100, capacity=1)
    await bucket.acquire()  # uses the initial token (instant)
    start = time.monotonic()
    await bucket.acquire()  # must wait ~1/100s for a refill
    assert time.monotonic() - start >= 0.005


def test_rejects_nonpositive_rate() -> None:
    with pytest.raises(ValueError):
        AsyncTokenBucket(rate_per_sec=0)

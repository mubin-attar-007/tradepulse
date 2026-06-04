"""Internal cron-tick endpoint must stay disabled (404) unless TICK_SECRET is set,
so it is never an open, unauthenticated trigger."""

from __future__ import annotations

from httpx import AsyncClient


async def test_tick_disabled_without_secret(client: AsyncClient) -> None:
    # TICK_SECRET is unset in tests -> the endpoint is invisible / inert.
    resp = await client.post("/internal/tick?key=anything")
    assert resp.status_code == 404

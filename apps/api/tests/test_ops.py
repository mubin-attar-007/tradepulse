"""Internal cron-tick endpoint must stay disabled (404) unless TICK_SECRET is set,
so it is never an open, unauthenticated trigger — and must answer 404 for a WRONG
secret too, since any other status is an oracle telling a prober it is armed."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from starlette.requests import Request

from app.core.config import Settings
from app.ops_router import _require_secret

_SECRET = "tick-secret-value"


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/internal/tick",
            "headers": raw,
            "query_string": b"",
            "client": ("127.0.0.1", 4321),
        }
    )


@pytest.fixture
def armed(monkeypatch: pytest.MonkeyPatch) -> None:
    """TICK_SECRET configured, so requests reach the comparison instead of short-circuiting."""
    monkeypatch.setattr("app.ops_router.get_settings", lambda: Settings(tick_secret=_SECRET))


async def test_tick_disabled_without_secret(client: AsyncClient) -> None:
    # TICK_SECRET is unset in tests -> the endpoint is invisible / inert.
    resp = await client.post("/internal/tick?key=anything")
    assert resp.status_code == 404


async def test_backfill_disabled_without_secret(client: AsyncClient) -> None:
    resp = await client.post("/internal/backfill?symbol=BTC/USD&key=anything")
    assert resp.status_code == 404


def test_non_ascii_key_is_rejected_not_a_500(armed: None) -> None:
    """`hmac.compare_digest` raises TypeError on a non-ASCII str.

    With the secret set, `?key=é` used to blow up into a 500 while every other
    wrong key gave 404 — the difference alone reveals that the endpoint is armed.
    """
    with pytest.raises(HTTPException) as excinfo:
        _require_secret(_request(), "ééé")
    assert excinfo.value.status_code == 404


def test_wrong_and_empty_secrets_are_404(armed: None) -> None:
    for presented in ("", "not-the-secret", _SECRET + "x"):
        with pytest.raises(HTTPException) as excinfo:
            _require_secret(_request(), presented)
        assert excinfo.value.status_code == 404


def test_secret_accepted_from_header_or_query(armed: None) -> None:
    # The header is the documented form (a secret in a URL lands in access logs);
    # the query parameter stays supported for schedulers that cannot set headers.
    _require_secret(_request({"authorization": f"Bearer {_SECRET}"}), "")
    _require_secret(_request(), _SECRET)


def test_wrong_bearer_is_not_rescued_by_a_correct_query_key(armed: None) -> None:
    """A presented header is the credential; it does not fall back on failure."""
    with pytest.raises(HTTPException) as excinfo:
        _require_secret(_request({"authorization": "Bearer wrong"}), _SECRET)
    assert excinfo.value.status_code == 404

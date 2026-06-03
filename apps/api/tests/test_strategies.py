"""StrategySpec validation + strategy CRUD/versioning + endpoints + tenancy."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.db import get_sessionmaker
from app.modules.auth.models import User
from app.modules.strategies.service import StrategyService
from app.modules.strategies.spec import StrategySpec, example_composite_spec

_MISSING_EXIT = {
    "name": "no exit",
    "universe": ["BTC/USD"],
    "timeframe": "1m",
    "entry_long": {
        "type": "compare",
        "left": {"kind": "price", "field": "close"},
        "op": ">",
        "right": {"kind": "const", "value": 1},
    },
    "sizing": {"method": "fixed_units", "value": 1},
}


# --- spec-level ---
def test_example_spec_is_valid() -> None:
    assert len(example_composite_spec().spec_hash()) == 64


def test_spec_requires_exit() -> None:
    with pytest.raises(ValidationError):
        StrategySpec.model_validate(_MISSING_EXIT)


# --- service-level ---
async def test_create_then_dedup_then_new_version() -> None:
    async with get_sessionmaker()() as s:
        user = User(email="owner@example.com")
        s.add(user)
        await s.flush()
        service = StrategyService(s, user.id)

        spec = example_composite_spec()
        strategy, v1 = await service.create(spec)
        assert v1.version == 1 and strategy.latest_version == 1

        again = await service.save_version(strategy.id, spec)
        assert again.version == 1  # unchanged spec -> dedup

        renamed = spec.model_copy(update={"name": "Renamed"})
        v2 = await service.save_version(strategy.id, renamed)
        assert v2.version == 2 and v2.spec_hash != v1.spec_hash
        await s.commit()


async def test_owner_scoping() -> None:
    async with get_sessionmaker()() as s:
        a = User(email="a@example.com")
        b = User(email="b@example.com")
        s.add_all([a, b])
        await s.flush()
        strategy, _ = await StrategyService(s, a.id).create(example_composite_spec())
        await s.commit()
        assert await StrategyService(s, b.id).strategies.get(strategy.id) is None


# --- endpoints ---
async def _login(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "trader@example.com", "password": "password123"}
    )


async def test_strategies_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/strategies")).status_code == 401


async def test_create_strategy_endpoint(client: AsyncClient) -> None:
    await _login(client)
    spec = example_composite_spec().model_dump(mode="json")
    resp = await client.post("/strategies", json=spec)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["strategy"]["latest_version"] == 1
    assert body["latest"]["spec"]["name"] == spec["name"]
    assert len(body["latest"]["spec_hash"]) == 64


async def test_create_invalid_strategy_is_422(client: AsyncClient) -> None:
    await _login(client)
    resp = await client.post("/strategies", json=_MISSING_EXIT)
    assert resp.status_code == 422  # exit is mandatory

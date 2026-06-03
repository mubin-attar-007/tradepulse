"""Invariant #1: the owner-scoped repository isolates tenants.

This is the guard the architecture calls for — a cross-tenant read must return
nothing, and ownership is derived from the repo (not caller input).
"""

from __future__ import annotations

from app.core.db import get_sessionmaker
from app.core.repository import OwnedRepository
from app.modules.auth.models import BrokerConnection, User


class _BrokerRepo(OwnedRepository[BrokerConnection]):
    model = BrokerConnection


async def test_owner_scoping_isolates_tenants() -> None:
    async with get_sessionmaker()() as session:
        user_a = User(email="ua@example.com")
        user_b = User(email="ub@example.com")
        session.add_all([user_a, user_b])
        await session.flush()

        conn = BrokerConnection(broker="alpaca", env="paper", encrypted_credentials=b"secret")
        await _BrokerRepo(session, user_a.id).add(conn)
        await session.commit()
        conn_id = conn.id

        # User B sees nothing belonging to user A.
        repo_b = _BrokerRepo(session, user_b.id)
        assert await repo_b.get(conn_id) is None
        assert list(await repo_b.list()) == []

        # User A sees their own row, with ownership stamped by the repository.
        fetched = await _BrokerRepo(session, user_a.id).get(conn_id)
        assert fetched is not None
        assert fetched.owner_id == user_a.id


async def test_add_overrides_caller_supplied_owner() -> None:
    """Even if a caller pre-sets owner_id, the repository stamps its own owner."""
    async with get_sessionmaker()() as session:
        attacker = User(email="attacker@example.com")
        victim = User(email="victim@example.com")
        session.add_all([attacker, victim])
        await session.flush()

        conn = BrokerConnection(
            broker="alpaca", env="paper", encrypted_credentials=b"x", owner_id=victim.id
        )
        await _BrokerRepo(session, attacker.id).add(conn)
        await session.commit()

        assert conn.owner_id == attacker.id  # repo owner wins, not the spoofed victim id

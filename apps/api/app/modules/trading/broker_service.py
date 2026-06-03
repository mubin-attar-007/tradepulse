"""Broker connections: store BYO API keys encrypted at rest (libsodium), decrypt
only at point of use, never log/return secrets."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import get_cipher
from app.core.repository import OwnedRepository
from app.modules.auth.models import BrokerConnection

_SEP = "\x1f"  # unit separator between key and secret in the ciphertext blob


class BrokerConnectionRepository(OwnedRepository[BrokerConnection]):
    model = BrokerConnection


class BrokerConnectionService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self.session = session
        self.owner_id = owner_id
        self.repo = BrokerConnectionRepository(session, owner_id)

    async def add(
        self, *, broker: str, env: str, label: str | None, api_key: str, api_secret: str
    ) -> BrokerConnection:
        blob = get_cipher().encrypt(f"{api_key}{_SEP}{api_secret}")
        connection = BrokerConnection(
            broker=broker, env=env, label=label, encrypted_credentials=blob, is_active=True
        )
        await self.repo.add(connection)
        await self.session.flush()
        return connection

    async def list(self) -> Sequence[BrokerConnection]:
        return await self.repo.list()

    @staticmethod
    def decrypt(connection: BrokerConnection) -> tuple[str, str]:
        """Decrypt at point of use only (never expose over the API)."""
        plaintext = get_cipher().decrypt(connection.encrypted_credentials)
        api_key, _, api_secret = plaintext.partition(_SEP)
        return api_key, api_secret

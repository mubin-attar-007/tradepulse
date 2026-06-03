"""Auth domain logic: registration and credential verification.

Uses a constant-time dummy verify on the no-user path to avoid leaking account
existence via response timing.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationError, ConflictError
from app.core.security import hash_password, needs_rehash, verify_password
from app.modules.auth.models import User, UserCredential

# Pre-computed argon2 hash of a random string; used to equalize timing.
_DUMMY_HASH = hash_password("timing-equalizer-not-a-real-password")


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(self, email: str, password: str, display_name: str | None) -> User:
        normalized = email.strip().lower()
        existing = await self.session.scalar(select(User).where(User.email == normalized))
        if existing is not None:
            raise ConflictError("Email is already registered.")
        user = User(email=normalized, display_name=display_name, is_active=True)
        self.session.add(user)
        await self.session.flush()
        self.session.add(UserCredential(user_id=user.id, password_hash=hash_password(password)))
        await self.session.flush()
        return user

    async def authenticate(self, email: str, password: str) -> User:
        normalized = email.strip().lower()
        user = await self.session.scalar(select(User).where(User.email == normalized))
        cred = (
            await self.session.scalar(
                select(UserCredential).where(UserCredential.user_id == user.id)
            )
            if user is not None
            else None
        )
        if user is None or cred is None or not user.is_active:
            verify_password(_DUMMY_HASH, password)  # equalize timing
            raise AuthenticationError("Invalid email or password.")
        if not verify_password(cred.password_hash, password):
            raise AuthenticationError("Invalid email or password.")
        if needs_rehash(cred.password_hash):
            cred.password_hash = hash_password(password)
        return user

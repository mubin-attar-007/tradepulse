"""Auth ORM models: User, UserCredential, BrokerConnection.

``User`` is the tenancy root (it *is* the owner). ``BrokerConnection`` is the
first owner-scoped entity and demonstrates encrypted-at-rest credentials; it is
dormant (schema only) until the gated live-trading phase.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, OwnedEntity, TimestampMixin, UUIDPrimaryKey


class User(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Dormant seams: 2FA lands with live trading; org_id makes the SaaS path a non-migration.
    totp_secret: Mapped[str | None] = mapped_column(String(64), default=None)
    org_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    credential: Mapped[UserCredential] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserCredential(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="credential")


class BrokerConnection(OwnedEntity):
    __tablename__ = "broker_connections"

    broker: Mapped[str] = mapped_column(String(32))  # 'alpaca' | 'binance' | ...
    env: Mapped[str] = mapped_column(String(8))  # 'paper' | 'live'
    label: Mapped[str | None] = mapped_column(String(120), default=None)
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

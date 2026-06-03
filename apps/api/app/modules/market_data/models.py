"""Market-data ORM models: instruments, vendor symbol mappings, and the OHLCV
TimescaleDB hypertable.

Market data is global (shared, not owner-scoped). The OHLCV table stores ONLY
1-minute, fully-closed (`is_final`) bars timestamped at bar OPEN (half-open
``[ts, ts+1m)``); higher timeframes are derived on the fly via ``time_bucket``.
The hypertable itself is created in the migration (a TimescaleDB operation).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKey

# Money/price precision. Crypto needs many decimals; equities far fewer.
PRICE = Numeric(20, 8)
VOLUME = Numeric(28, 8)


class Instrument(Base, UUIDPrimaryKey, TimestampMixin):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("symbol", "asset_class", name="uq_instruments_symbol_class"),
    )

    symbol: Mapped[str] = mapped_column(String(32), index=True)  # canonical, e.g. AAPL, BTC/USD
    asset_class: Mapped[str] = mapped_column(String(16))  # 'equity' | 'crypto'
    name: Mapped[str | None] = mapped_column(String(120), default=None)
    exchange: Mapped[str | None] = mapped_column(String(32), default=None)  # e.g. XNAS
    quote_currency: Mapped[str] = mapped_column(String(8), default="USD")
    calendar: Mapped[str] = mapped_column(String(16), default="XNYS")  # 'XNYS' | '24x7'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class InstrumentSource(Base, UUIDPrimaryKey):
    __tablename__ = "instrument_sources"
    __table_args__ = (
        UniqueConstraint("instrument_id", "source", name="uq_instrument_sources_instrument_source"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(32))  # 'alpaca' | 'binance' | 'yfinance'
    source_symbol: Mapped[str] = mapped_column(String(64))  # vendor-specific symbol
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class OHLCV(Base):
    """One row = one fully-closed 1-minute bar. PK includes ``ts`` (Timescale
    requires the partition column in any unique key)."""

    __tablename__ = "ohlcv"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)  # bar OPEN, UTC
    open: Mapped[Decimal] = mapped_column(PRICE)
    high: Mapped[Decimal] = mapped_column(PRICE)
    low: Mapped[Decimal] = mapped_column(PRICE)
    close: Mapped[Decimal] = mapped_column(PRICE)
    volume: Mapped[Decimal] = mapped_column(VOLUME)
    is_final: Mapped[bool] = mapped_column(Boolean, server_default="true")
    source: Mapped[str] = mapped_column(String(32))

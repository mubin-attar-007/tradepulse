"""Instrument queries for the charting API."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.market_data.models import Instrument


async def list_instruments(
    session: AsyncSession, *, asset_class: str | None = None
) -> Sequence[Instrument]:
    stmt = select(Instrument).where(Instrument.is_active.is_(True)).order_by(Instrument.symbol)
    if asset_class is not None:
        stmt = stmt.where(Instrument.asset_class == asset_class)
    return (await session.execute(stmt)).scalars().all()


async def get_instrument(session: AsyncSession, instrument_id: uuid.UUID) -> Instrument | None:
    return await session.get(Instrument, instrument_id)

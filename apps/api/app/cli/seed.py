"""Seed the starter instrument universe. Run via ``just seed``."""

from __future__ import annotations

import asyncio

from app.core.db import get_sessionmaker
from app.modules.market_data.seed import seed_instruments


async def _run() -> None:
    async with get_sessionmaker()() as session:
        count = await seed_instruments(session)
        await session.commit()
    print(f"Seeded {count} instruments.")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

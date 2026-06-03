"""The broker adapter contract. Paper trading and (gated) live trading both
implement it, so flipping to live is a config + gate-lift, not a core change."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    client_order_id: str  # idempotency key (end-to-end dedupe)
    symbol: str
    side: Literal["buy", "sell"]
    qty: Decimal
    type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OrderResult:
    broker_order_id: str
    client_order_id: str
    status: str  # accepted | filled | rejected | ...
    filled_qty: Decimal
    filled_avg_price: Decimal | None


@runtime_checkable
class BrokerAdapter(Protocol):
    name: str
    env: Literal["paper", "live"]

    async def get_account(self) -> dict[str, Any]: ...
    async def get_positions(self) -> list[dict[str, Any]]: ...
    async def submit_order(self, order: BrokerOrder) -> OrderResult: ...
    async def cancel_order(self, broker_order_id: str) -> None: ...

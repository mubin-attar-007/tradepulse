"""Alpaca broker adapter (paper or live by base URL). Instantiated only when
credentials are supplied; live submits are still blocked by the LiveTradingGate."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Literal

from app.core.errors import AppError
from app.modules.trading.brokers.base import BrokerOrder, OrderResult


class AlpacaBrokerAdapter:
    name = "alpaca"

    def __init__(
        self, api_key: str, api_secret: str, *, env: Literal["paper", "live"] = "paper"
    ) -> None:
        if not api_key or not api_secret:
            raise AppError("Alpaca credentials are required.")
        self.env: Literal["paper", "live"] = env
        from alpaca.trading.client import TradingClient

        self._client = TradingClient(api_key, api_secret, paper=(env == "paper"))

    async def get_account(self) -> dict[str, Any]:
        account: Any = await asyncio.to_thread(self._client.get_account)
        return {
            "cash": str(account.cash),
            "equity": str(account.equity),
            "status": str(account.status),
        }

    async def get_positions(self) -> list[dict[str, Any]]:
        positions: Any = await asyncio.to_thread(self._client.get_all_positions)
        return [
            {"symbol": p.symbol, "qty": str(p.qty), "avg_entry_price": str(p.avg_entry_price)}
            for p in positions
        ]

    async def submit_order(self, order: BrokerOrder) -> OrderResult:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        side = OrderSide.BUY if order.side == "buy" else OrderSide.SELL
        request: Any
        if order.type == "limit":
            request = LimitOrderRequest(
                symbol=order.symbol,
                qty=float(order.qty),
                side=side,
                time_in_force=TimeInForce.DAY,
                limit_price=float(order.limit_price or 0),
                client_order_id=order.client_order_id,
            )
        else:
            request = MarketOrderRequest(
                symbol=order.symbol,
                qty=float(order.qty),
                side=side,
                time_in_force=TimeInForce.DAY,
                client_order_id=order.client_order_id,
            )
        result: Any = await asyncio.to_thread(self._client.submit_order, request)
        return OrderResult(
            broker_order_id=str(result.id),
            client_order_id=order.client_order_id,
            status=str(result.status),
            filled_qty=Decimal(str(result.filled_qty or 0)),
            filled_avg_price=Decimal(str(result.filled_avg_price))
            if result.filled_avg_price
            else None,
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        await asyncio.to_thread(self._client.cancel_order_by_id, broker_order_id)

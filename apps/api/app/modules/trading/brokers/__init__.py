"""Broker adapters. The same contract backs paper and (gated) live execution."""

from app.modules.trading.brokers.base import BrokerAdapter, BrokerOrder, OrderResult

__all__ = ["BrokerAdapter", "BrokerOrder", "OrderResult"]

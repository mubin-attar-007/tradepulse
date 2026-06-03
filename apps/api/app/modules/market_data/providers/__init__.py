"""Market-data vendor adapters. The concrete Alpaca / CCXT / yfinance providers
land in the next Phase-2 slice; this package defines the shared contract."""

from app.modules.market_data.providers.base import CanonicalBar, MarketDataProvider

__all__ = ["CanonicalBar", "MarketDataProvider"]

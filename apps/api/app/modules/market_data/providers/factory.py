"""Resolve a ``source`` string (from instrument_sources) to a provider."""

from __future__ import annotations

from app.core.config import Settings
from app.modules.market_data.providers.alpaca_provider import AlpacaProvider
from app.modules.market_data.providers.base import MarketDataProvider
from app.modules.market_data.providers.ccxt_provider import CcxtProvider
from app.modules.market_data.providers.yfinance_provider import YFinanceProvider

_CCXT_EXCHANGES = {"binance", "coinbase", "kraken", "coinbasepro"}


def make_provider(source: str, settings: Settings) -> MarketDataProvider:
    if source in _CCXT_EXCHANGES:
        return CcxtProvider(source)
    if source == "yfinance":
        return YFinanceProvider()
    if source == "alpaca":
        return AlpacaProvider(settings.alpaca_api_key, settings.alpaca_api_secret)
    raise ValueError(f"Unknown market-data source: {source!r}")

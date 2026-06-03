"""market_data module (shell). Fleshed out in Phase 2:
instruments registry, calendars, TimescaleDB OHLCV store, vendor adapters
(Alpaca/CCXT), rate-limited ingestion supervisor (runs in the worker), and
realtime fan-out. The ingestion supervisor must NOT run in the API lifespan."""

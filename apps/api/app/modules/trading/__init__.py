"""trading module: paper trading (MVP) and the gated live seam (deferred).

Paper trading reuses the EXACT backtest engine — a session re-evaluates its
strategy over [deploy, now] against a virtual ledger (close_at_end=False so it
holds positions). Parity with backtesting is therefore guaranteed by
construction; the desk shows engine truth."""

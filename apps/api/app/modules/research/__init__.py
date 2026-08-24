"""Research surfaces composed from the layers below.

Everything here READS from market data, the strategy DSL, and the backtest engine and
composes them into a product surface — the public per-ticker illustration, the
reference backtest, point-in-time signal evaluation. It owns no persistence of its
own and sits ABOVE backtesting in the layering, which is why these modules live here
rather than inside market_data (where they were an upward import).
"""

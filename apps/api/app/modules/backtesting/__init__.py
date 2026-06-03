"""backtesting module: the event-driven, look-ahead-safe, cost-aware engine —
the product's moat. Shared with paper trading (Phase 7) via the same core.

Look-ahead is structurally prevented: indicators are causal, decisions are made
on a closed bar, and orders fill on the NEXT bar's open (verified by an
adversarial canary test that perturbs future bars and asserts past decisions
are byte-identical)."""

"""ai module (edge layer — nothing depends on it, so it can fail/degrade without
taking the platform down).

AI is a copilot, never an oracle: it translates NL into a validated StrategySpec
(never auto-executed) and narrates deterministic results (never invents numbers).
No AI code path can place an order."""

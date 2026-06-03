"""Platform kernel (L0): config, DB, Redis, logging, errors, security, events.

Nothing in :mod:`app.core` may import from :mod:`app.modules` — the dependency
arrow points inward only (enforced by import-linter).
"""

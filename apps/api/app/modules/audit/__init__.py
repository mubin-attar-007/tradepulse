"""Audit module: append-only log of security/trade-relevant events.

MVP is a plain append-only table (INSERT/SELECT only). Hash-chaining + a
verifier are deferred to the real-money phase where non-repudiation matters.
"""

"""Quantitative-correctness suite.

These tests are the ones that make the platform's claims checkable. They are split
by the kind of evidence they provide:

* ``fixtures``     — hand-derived golden numbers: exact fills, commissions, exit
                     prices and equity, computed by hand from the documented
                     formulas and pinned. A change in execution semantics has to be
                     an explicit decision, not a silent drift.
* ``lookahead``    — canaries that fail if any future information reaches a
                     decision, including the INTRABAR case the original canary
                     could not see.
* ``differential`` — an independent reference implementation of the restricted
                     strategy class, driven by Hypothesis, asserted bar-for-bar
                     against the real engine.
* ``properties``   — invariants that must hold for every input (accounting
                     identity, determinism, risk-limit enforcement, ordering).
* ``indicators``   — indicator alignment, warm-up, and seeding parity.
* ``metrics``      — metric definitions against series with known answers.
"""

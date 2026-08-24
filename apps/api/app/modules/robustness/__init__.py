"""The robustness lab.

A single backtest is one draw from a distribution, run on one sample, with one set
of parameters and one cost assumption. Treating it as evidence is the central
failure mode of retail quant work, and no amount of engineering elsewhere in this
platform compensates for it.

This module turns one result into an argument, by attacking it from five
independent directions:

* **splits**          — did it work out of sample, and does it keep working as the
                        window rolls forward? (walk-forward, purged CV with embargo)
* **sensitivity**     — is the result a plateau or a spike? A parameter set that
                        only works at exactly (20, 50) is a curve fit.
* **cost_stress**     — does the edge survive 2x and 3x the assumed frictions?
* **monte_carlo**     — how much of the outcome was sequence luck? (trade
                        reshuffling, block bootstrap, per-trade cost perturbation;
                        start-date perturbation is not yet implemented)
* **multiple_testing** — how many things were tried before this one looked good?
                        A Sharpe of 1.5 found after 200 trials is not a Sharpe of 1.5.

The output is never collapsed into a single opaque score. Every conclusion carries
the evidence that produced it, because the point is to let a human disbelieve it.
"""

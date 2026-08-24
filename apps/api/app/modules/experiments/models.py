"""The experiment record — the platform's unit of evidence.

Every analysis that produces a number lands here, under one shape, with the full
provenance needed to reproduce it: which strategy version, over which data, with
which engine, cost model and metric definitions, under which seed.

Two rules give the table its value:

* **Results are append-only.** A rerun creates a NEW experiment linked to the old
  one by ``parent_id``; it never overwrites it. Overwriting is how a research log
  quietly becomes a record of only the results you liked.
* **Versions are recorded, not assumed.** ``engine_version``, ``metrics_version``
  and ``cost_model_version`` are stamped at run time, so a result produced before a
  metric definition changed stays interpretable instead of being silently
  re-read under the new meaning.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import OwnedEntity

# The analyses that can produce an experiment. Adding one here is a deliberate act:
# it means committing to a persisted result shape and a way to reproduce it.
EXPERIMENT_KINDS = (
    "backtest",
    "walk_forward",
    "sensitivity",
    "cost_stress",
    "monte_carlo",
    "robustness_suite",
    "ai_generation",
    "ai_evaluation",
)


class Experiment(OwnedEntity):
    __tablename__ = "experiments"

    kind: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|done|failed
    title: Mapped[str] = mapped_column(String(200))
    hypothesis: Mapped[str | None] = mapped_column(Text, default=None)

    # --- what was tested -----------------------------------------------------
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), index=True, default=None
    )
    strategy_version: Mapped[int | None] = mapped_column(Integer, default=None)
    spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    spec_hash: Mapped[str] = mapped_column(String(64), index=True, default="")

    # --- what it was tested on ----------------------------------------------
    symbol: Mapped[str | None] = mapped_column(String(32), default=None)
    timeframe: Mapped[str | None] = mapped_column(String(8), default=None)
    start_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    end_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # SHA-256 over every bar the run consumed. Two experiments claiming the same data
    # must carry the same fingerprint, or one of them is not reproducible.
    data_fingerprint: Mapped[str] = mapped_column(String(64), index=True, default="")
    bars: Mapped[int | None] = mapped_column(Integer, default=None)

    # --- how it was computed -------------------------------------------------
    engine_version: Mapped[str] = mapped_column(String(16), default="")
    metrics_version: Mapped[str] = mapped_column(String(16), default="")
    cost_model_version: Mapped[str] = mapped_column(String(16), default="")
    seed: Mapped[int | None] = mapped_column(Integer, default=None)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)

    # --- outcome -------------------------------------------------------------
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    error_category: Mapped[str | None] = mapped_column(String(64), default=None)

    # --- lineage and curation ------------------------------------------------
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), index=True, default=None
    )
    tags: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

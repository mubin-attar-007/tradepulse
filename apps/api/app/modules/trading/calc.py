"""Position-sizing calculator — a thin wrapper around the engine's ``_size()``.

This is DELIBERATELY not a reimplementation: it constructs a ``PositionSizing``
spec and delegates to ``app.modules.backtesting.engine._size`` (the exact math the
backtester and paper engine use), so the calculator can never drift from what the
engine would actually do. Money is computed here as ``Decimal`` and serialized to
strings by the schema (invariant #2) — the frontend never does money math.

The output is SIZING GUIDANCE, not an executable order (live trading stays gated).
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import ValidationError

from app.core.errors import BadRequestError
from app.modules.backtesting.engine import _size
from app.modules.strategies.spec import PositionSizing
from app.modules.trading.schemas import PositionSizeOut, PositionSizeRequest

_D0 = Decimal("0")


def compute_position_size(req: PositionSizeRequest) -> PositionSizeOut:
    equity = req.equity
    entry = req.entry

    # For risk_per_trade, the engine's _size() takes a stop PERCENT (fraction of the
    # fill). Derive it from the entry/stop prices; _size then reconstructs the exact
    # risk-per-share as fill * stop_pct == (entry - stop).
    stop_pct: float | None = None
    if req.stop is not None and entry > 0 and req.stop < entry:
        stop_pct = float((entry - req.stop) / entry)

    # PositionSizing enforces a method-specific range (percent/risk in (0, 1]) that the
    # request schema's bare ``gt=0`` does NOT — so an out-of-range value would raise a
    # raw pydantic ValidationError here (a 500, since it bypasses the request-body
    # handler). Convert it to an honest 4xx (B2).
    try:
        sizing = PositionSizing(
            method=req.method,
            value=req.value,
            atr_ref="calc" if req.method == "atr" else None,
        )
    except ValidationError as exc:
        raise BadRequestError(exc.errors()[0]["msg"]) from exc
    qty = _size(sizing, equity, entry, stop_pct, req.atr)
    if qty < 0:
        qty = _D0

    notional = qty * entry
    # Dollars at risk between entry and the protective stop (0 when no usable stop).
    risk_amount = qty * (entry - req.stop) if req.stop is not None and req.stop < entry else _D0
    pct_of_equity = notional / equity if equity > 0 else _D0

    return PositionSizeOut(
        qty=qty,
        notional=notional,
        risk_amount=risk_amount,
        pct_of_equity=pct_of_equity,
    )

"""Authenticated research endpoints composed from the layers below.

Currently: point-in-time signal evaluation for a StrategySpec against an
instrument's latest CLOSED bar.

The URL keeps its original ``/market/instruments/{id}/signal`` shape (existing
clients and the generated TS contract depend on it) even though the handler now
lives in the research module — the move was about layering, not about the API.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Query
from pydantic import ValidationError

from app.core.deps import SessionDep
from app.core.errors import BadRequestError
from app.modules.auth.deps import CurrentUser
from app.modules.research import signal
from app.modules.research.schemas import SignalOut
from app.modules.strategies.spec import StrategySpec

router = APIRouter(prefix="/market", tags=["market-data"])


@router.get("/instruments/{instrument_id}/signal", response_model=SignalOut)
async def get_instrument_signal(
    instrument_id: uuid.UUID,
    session: SessionDep,
    _user: CurrentUser,
    spec: str = Query(description="JSON-encoded StrategySpec"),
    equity: str | None = Query(
        default=None, description="Decimal buying power for absolute sizing"
    ),
) -> SignalOut:
    """Evaluate a StrategySpec's entry rule on the latest CLOSED bar.

    entry/stop/target/size are real engine math (invariant #4) via the shared engine
    helpers. The result is an INTENDED order, not executable — live trading is gated
    (invariant #3). Prices must render under a DELAYED DataBadge on the client."""
    try:
        parsed = StrategySpec.model_validate_json(spec)
    except ValidationError as exc:
        raise BadRequestError(f"Invalid strategy spec: {exc.errors()[0]['msg']}") from exc
    equity_dec: Decimal | None = None
    if equity is not None:
        try:
            equity_dec = Decimal(equity)
        except InvalidOperation as exc:
            raise BadRequestError("equity must be a decimal number.") from exc
        if equity_dec <= 0:
            raise BadRequestError("equity must be positive.")

    instrument = await signal.resolve_instrument(session, instrument_id)
    result = await signal.evaluate_signal(session, instrument, parsed, equity=equity_dec)
    return SignalOut(
        should_enter=result.should_enter,
        reference_price=result.reference_price,
        entry=result.entry,
        stop=result.stop,
        target=result.target,
        size=result.size,
        size_per_10k=result.size_per_10k,
        as_of=result.as_of,
        timeframe=result.timeframe,
    )

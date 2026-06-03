"""Broker connections + the gated live-trading endpoints.

`/live/orders` exists to PROVE the gate: it can never execute real money while
the control stack (2FA, opt-in, kill-switch, confirmation) and feature flag are
absent. There is no code path here that places a real order today."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.deps import SessionDep
from app.core.errors import PermissionDeniedError
from app.modules.auth.deps import CurrentUser
from app.modules.trading import broker_schemas as schemas
from app.modules.trading.broker_service import BrokerConnectionService
from app.modules.trading.live_gate import LiveTradingGate

router = APIRouter(tags=["live-trading"])


@router.post("/brokers/connections", status_code=201, response_model=schemas.BrokerConnectionOut)
async def add_connection(
    payload: schemas.BrokerConnectionCreate, session: SessionDep, user: CurrentUser
) -> schemas.BrokerConnectionOut:
    connection = await BrokerConnectionService(session, user.id).add(
        broker=payload.broker,
        env=payload.env,
        label=payload.label,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
    )
    return schemas.BrokerConnectionOut.model_validate(connection)


@router.get("/brokers/connections", response_model=list[schemas.BrokerConnectionOut])
async def list_connections(
    session: SessionDep, user: CurrentUser
) -> list[schemas.BrokerConnectionOut]:
    rows = await BrokerConnectionService(session, user.id).list()
    return [schemas.BrokerConnectionOut.model_validate(row) for row in rows]


@router.get("/live/preflight", response_model=schemas.LivePreflightOut)
async def live_preflight(_user: CurrentUser) -> schemas.LivePreflightOut:
    status = LiveTradingGate.evaluate(get_settings())
    return schemas.LivePreflightOut(
        allowed=status.allowed, blocked_reasons=status.blocked_reasons()
    )


@router.post("/live/orders", status_code=202)
async def submit_live_order(
    payload: schemas.LiveOrderRequest, _user: CurrentUser
) -> dict[str, str]:
    status = LiveTradingGate.evaluate(
        get_settings(), confirmation_valid=bool(payload.confirmation_token)
    )
    LiveTradingGate.assert_allowed(status)  # raises 403 with the blocking reasons
    # Unreachable until the full control stack + feature flag exist; final guard:
    raise PermissionDeniedError("Live execution is not enabled.")

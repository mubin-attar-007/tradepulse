"""Broker-connection + live-trading API schemas. Secrets are never returned."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrokerConnectionCreate(BaseModel):
    broker: str = Field(min_length=1, max_length=32)
    env: Literal["paper", "live"] = "paper"
    label: str | None = Field(default=None, max_length=120)
    api_key: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class BrokerConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    broker: str
    env: str
    label: str | None
    is_active: bool
    created_at: datetime
    # Deliberately NO api_key / api_secret — credentials never leave the server.


class LivePreflightOut(BaseModel):
    allowed: bool
    blocked_reasons: list[str]


class LiveOrderRequest(BaseModel):
    broker_connection_id: uuid.UUID
    symbol: str = Field(min_length=1, max_length=32)
    side: Literal["buy", "sell"]
    qty: float = Field(gt=0)
    confirmation_token: str | None = None

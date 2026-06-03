"""Model registry: importing this module registers every ORM model on
``Base.metadata`` so Alembic autogenerate sees the full schema.

Add new model modules here as domains come online.
"""

from __future__ import annotations

from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.auth.models import BrokerConnection, User, UserCredential  # noqa: F401
from app.modules.backtesting.models import Backtest  # noqa: F401
from app.modules.market_data.models import (  # noqa: F401
    OHLCV,
    Instrument,
    InstrumentSource,
)
from app.modules.strategies.models import Strategy, StrategyVersion  # noqa: F401
from app.modules.trading.models import PaperSession  # noqa: F401

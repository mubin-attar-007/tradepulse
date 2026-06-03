"""Model registry: importing this module registers every ORM model on
``Base.metadata`` so Alembic autogenerate sees the full schema.

Add new model modules here as domains come online.
"""

from __future__ import annotations

from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.auth.models import BrokerConnection, User, UserCredential  # noqa: F401

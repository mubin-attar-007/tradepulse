"""Generic FastAPI dependency aliases (DB session, Redis).

Auth-specific dependencies (current user, ``get_owned``) live in the auth
module to keep the kernel free of any knowledge of the user model (layering).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.redis import get_redis

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]

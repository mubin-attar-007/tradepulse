"""Request-scoped context variables (request id, current user id).

Populated by middleware / auth dependencies and consumed by the logging
processors so every log line is correlated without threading args through.
"""

from __future__ import annotations

from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

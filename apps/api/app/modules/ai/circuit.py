"""A per-profile circuit breaker.

Without one, a provider that is down turns every request into a full timeout. With
a 120-second local-model timeout that is not a degraded experience, it is an outage
in which each user waits two minutes to be told the same thing.

Three states, and the middle one is the one that matters:

* **closed** — normal. Failures accumulate.
* **open** — enough consecutive failures that the provider is presumed down. The
  router skips it entirely and says so, so the user gets an immediate answer from
  the next profile in the chain.
* **half-open** — after a cooldown, ONE probe request is allowed through. If it
  succeeds the breaker closes; if it fails the cooldown restarts. This is what
  makes recovery automatic without hammering a struggling provider.

A permanent failure (an invalid API key) opens the breaker immediately rather than
after N attempts, because N attempts will produce N identical rejections and, with
some providers, an abuse flag.

State is per process and in memory. That is the right scope for what it protects
against (a wedged upstream) and deliberately avoids making a resilience mechanism
depend on Redis, which is itself something that can be down.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum

from app.modules.ai.providers.base import ErrorKind


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _Entry:
    consecutive_failures: int = 0
    opened_at: float | None = None
    last_error: str = ""
    probes_in_flight: int = 0


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_seconds: float = 60.0
    _entries: dict[str, _Entry] = field(default_factory=dict)

    def _entry(self, key: str) -> _Entry:
        return self._entries.setdefault(key, _Entry())

    def state(self, key: str) -> CircuitState:
        entry = self._entry(key)
        if entry.opened_at is None:
            return CircuitState.CLOSED
        if time.monotonic() - entry.opened_at < self.cooldown_seconds:
            return CircuitState.OPEN
        # Cooldown elapsed: allow exactly one probe through.
        if entry.probes_in_flight == 0:
            entry.probes_in_flight = 1
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def record_success(self, key: str) -> None:
        self._entries[key] = _Entry()

    def record_failure(self, key: str, kind: ErrorKind = ErrorKind.UNKNOWN) -> None:
        entry = self._entry(key)
        entry.consecutive_failures += 1
        entry.last_error = str(kind)
        entry.probes_in_flight = 0
        if kind.is_permanent or entry.consecutive_failures >= self.failure_threshold:
            entry.opened_at = time.monotonic()

    def snapshot(self) -> dict[str, dict[str, object]]:
        """Current state per profile, for the readiness and trace surfaces."""
        return {
            key: {
                "state": self.state(key).value,
                "consecutive_failures": entry.consecutive_failures,
                "last_error": entry.last_error,
            }
            for key, entry in self._entries.items()
        }


# One breaker per process, shared by every request so failures actually accumulate.
_BREAKER = CircuitBreaker()


def get_breaker() -> CircuitBreaker:
    return _BREAKER

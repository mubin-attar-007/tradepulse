"""Human approval, bound to exactly what was approved.

An approval that is merely a boolean is not an approval — it is a checkbox that can
be carried over to a different strategy, a different dataset, or a different set of
risk limits without anyone noticing. So approval here is a signed token over the
CONTENT of the thing approved:

    strategy hash + dataset fingerprint + plan hash + risk-policy version + owner

Change any of those and the token no longer verifies, which is what makes "any
material edit invalidates the previous approval" a property of the system rather
than a promise in a document.

Deliberately stateless: an HMAC over the content, not a row in a table. That means
approval survives a restart, cannot be replayed against a different user, and
cannot drift out of sync with the thing it refers to — the token IS the record of
what was approved.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings
from app.core.errors import PermissionDeniedError

# The version of the risk rules in force. Bumping it invalidates every outstanding
# approval, which is the correct behaviour when the limits themselves change.
RISK_POLICY_VERSION = "1.0.0"

# Long enough to read a plan and decide; short enough that a token found later in a
# log or a browser history is useless.
APPROVAL_TTL_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class ApprovalSubject:
    """Everything an approval is *about*. All of it is signed."""

    owner_id: uuid.UUID
    spec_hash: str
    data_fingerprint: str
    plan_hash: str
    action: str  # run_experiment | deploy_paper | parameter_search

    def digest(self) -> str:
        payload = json.dumps(
            {
                "owner": str(self.owner_id),
                "spec": self.spec_hash,
                "data": self.data_fingerprint,
                "plan": self.plan_hash,
                "action": self.action,
                "risk_policy": RISK_POLICY_VERSION,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()


def plan_hash(plan: dict[str, Any]) -> str:
    """Canonical hash of an experiment plan, so a reordered plan is the same plan."""
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _key() -> bytes:
    return get_settings().app_secret_key.encode()


def mint(subject: ApprovalSubject, *, issued_at: float | None = None) -> str:
    """Issue an approval token for exactly this subject."""
    issued = int(issued_at if issued_at is not None else time.time())
    body = f"{subject.digest()}.{issued}"
    signature = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def verify(token: str, subject: ApprovalSubject, *, now: float | None = None) -> None:
    """Raise unless ``token`` approves exactly ``subject`` and is still fresh.

    The error messages distinguish "this approval was for something else" from
    "this approval expired", because those need different actions from the user and
    conflating them makes the gate feel arbitrary.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise PermissionDeniedError("Malformed approval token.")
    digest, issued_raw, signature = parts

    expected = hmac.new(_key(), f"{digest}.{issued_raw}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PermissionDeniedError("Approval token signature is invalid.")

    try:
        issued = int(issued_raw)
    except ValueError as exc:
        raise PermissionDeniedError("Malformed approval token.") from exc

    current = now if now is not None else time.time()
    if current - issued > APPROVAL_TTL_SECONDS:
        raise PermissionDeniedError(
            "This approval has expired. Review the plan and approve it again."
        )
    if not hmac.compare_digest(digest, subject.digest()):
        raise PermissionDeniedError(
            "This approval was issued for a different strategy, dataset, plan, or risk "
            "policy. Anything material changed since it was granted, so it no longer "
            "applies — review the new plan and approve that."
        )

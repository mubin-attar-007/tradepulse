"""Shared API types.

``Money`` keeps full ``Decimal`` precision server-side but serializes to a JSON
*string* (invariant #2), so no precision is lost across the JS boundary and the
frontend never does float arithmetic on prices.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]

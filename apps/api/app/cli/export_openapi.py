"""Export the OpenAPI schema to packages/contracts/openapi.json.

Run via ``just openapi``. CI regenerates and fails on drift, keeping the
generated TypeScript client in sync with the backend contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUTPUT = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "openapi.json"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    OUTPUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()

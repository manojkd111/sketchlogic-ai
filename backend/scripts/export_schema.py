"""Export the GraphDocument JSON Schema to shared/schemas/ for the frontend and ML packages.

Usage (from backend/):  python -m scripts.export_schema
"""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.graph import CURRENT_SCHEMA_VERSION, GraphDocument

OUT = Path(__file__).resolve().parents[2] / "shared" / "schemas"


def main() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    major = CURRENT_SCHEMA_VERSION.split(".")[0]
    path = OUT / f"graph.v{major}.json"
    schema = GraphDocument.model_json_schema()
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return path


if __name__ == "__main__":
    main()

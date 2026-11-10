"""GraphDocument validation against the shared contract (`shared/schemas/graph.v1.json`).

This package must not import the backend (see ADR 0001), so it validates plain JSON: the JSON
Schema covers shapes and enums, and `integrity_errors` repeats the cross-field rules that live in
the backend's Pydantic validators (unique ids, known references, inferred edges < 1.0).
A copy of this module lives in evaluations/; keep the two in sync.
"""

from __future__ import annotations

import json
from collections import Counter
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "shared" / "schemas" / "graph.v1.json"


@cache
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def integrity_errors(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    nodes = [n["id"] for n in doc.get("nodes", [])]
    edges = [e["id"] for e in doc.get("edges", [])]
    groups = [g["id"] for g in doc.get("groups", [])]
    for kind, ids in (("node", nodes), ("edge", edges), ("group", groups)):
        errors += [f"duplicate {kind} id '{i}'" for i, c in Counter(ids).items() if c > 1]
    node_set, group_set = set(nodes), set(groups)
    for e in doc.get("edges", []):
        for end in ("source", "target"):
            if e[end] not in node_set:
                errors.append(f"edge '{e['id']}' {end} '{e[end]}' is not a known node")
        if e.get("evidence") == "inferred" and e.get("confidence", 1.0) >= 1.0:
            errors.append(f"edge '{e['id']}': inferred edges must have confidence < 1.0")
    for n in doc.get("nodes", []):
        if n.get("group_id") is not None and n["group_id"] not in group_set:
            errors.append(f"node '{n['id']}' group_id '{n['group_id']}' is not a known group")
    parents = {g["id"]: g.get("parent_id") for g in doc.get("groups", [])}
    for g, p in parents.items():
        if p is not None and p not in group_set:
            errors.append(f"group '{g}' parent_id '{p}' is not a known group")
        seen = {g}
        while p is not None and p in parents:
            if p in seen:
                errors.append(f"group nesting cycle involving '{g}'")
                break
            seen.add(p)
            p = parents[p]
    return errors


def validation_errors(doc: Any) -> list[str]:
    """All problems with `doc` as a GraphDocument v1; empty means valid."""
    schema_errors = [
        f"{'/'.join(str(p) for p in err.absolute_path) or '<root>'}: {err.message}"
        for err in _validator().iter_errors(doc)
    ]
    if schema_errors:
        return schema_errors
    return integrity_errors(doc)

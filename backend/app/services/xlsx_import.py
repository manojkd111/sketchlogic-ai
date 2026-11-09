"""Deterministic XLSX -> GraphDocument import (no model involved).

Supported layouts, detected per sheet in workbook order (the first recognisable sheet wins):

* **Edge list**: a header row (within the first rows) with a source column and a target column,
  e.g. ``From | To | Label``. Optional ``Label``/``Relationship`` and ``Direction`` columns. A row
  with only a source (or only a target) adds an unconnected node.
* **Adjacency matrix**: node names across the first row and down the first column; any non-empty
  cell that is not a "no" value is an edge row -> column. Cell text other than a plain marker
  (1, x, yes, ✓ ...) becomes the edge label.

An optional sheet named ``Nodes`` (``Name``/``Id``, ``Label``, ``Type``/``Kind``, ``Group``) adds
kinds, display labels and groups.

Safety: the workbook was already validated (no macros, bounded decompression, no DOCTYPE).
It is opened with ``read_only=True, data_only=True``: formulas are never evaluated and formula
text is never imported (cells read as their cached value, or empty). Every value is treated as
plain text and the result is re-validated by Pydantic.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from openpyxl import load_workbook

from app.schemas.graph import (
    Edge,
    EdgeDirection,
    GraphDocument,
    GraphMetadata,
    Group,
    Node,
    NodeKind,
    Origin,
    Provenance,
    SourceInfo,
    SourceKind,
)

MAX_SCAN_ROWS = 20_000
MAX_SCAN_COLS = 200
HEADER_SEARCH_ROWS = 10
MAX_NODES = 2000  # schema limits (GraphDocument)
MAX_EDGES = 5000
MAX_LABEL = 200


class XlsxImportError(ValueError):
    """The workbook could not be turned into a graph (unrecognised or too large)."""


# --- header vocabulary ---------------------------------------------------------------------------

_SOURCE = {"from", "source", "src", "start", "origin", "fromnode", "sourcenode", "parent", "caller"}
_TARGET = {"to", "target", "dst", "dest", "destination", "end", "tonode", "targetnode", "child"}
_TARGET |= {"callee"}
_LABEL = {"label", "relationship", "relation", "description", "edge", "connection", "protocol"}
_LABEL |= {"via", "action", "edgelabel"}
_DIRECTION = {"direction", "dir", "arrow"}
_NODE_ID = {"name", "id", "node", "component", "nodename", "nodeid"}
_NODE_LABEL = {"label", "displayname", "title"}
_NODE_KIND = {"type", "kind", "category", "nodetype"}
_NODE_GROUP = {"group", "boundary", "zone", "subnet", "layer", "cluster", "container"}

# Order matters: first match wins ("User Service" is a service, "Customer DB" a database).
_KIND_WORDS: dict[NodeKind, tuple[str, ...]] = {
    NodeKind.DATABASE: ("database", "db", "sql", "postgres", "mysql", "datastore", "table"),
    NodeKind.QUEUE: ("queue", "topic", "stream", "kafka", "sqs", "bus"),
    NodeKind.STORAGE: ("storage", "bucket", "s3", "blob", "file", "cache", "redis"),
    NodeKind.SERVICE: ("service", "api", "server", "lambda", "function", "microservice"),
    NodeKind.EXTERNAL: ("external", "thirdparty", "3rdparty", "vendor", "saas"),
    NodeKind.ACTOR: ("actor", "user", "person", "customer", "client", "role"),
    NodeKind.PROCESS: ("process", "step", "task", "activity"),
    NodeKind.DECISION: ("decision", "condition", "gateway", "choice"),
    NodeKind.START_END: ("start", "end", "startend", "terminal", "begin", "finish"),
    NodeKind.NOTE: ("note", "comment", "annotation"),
    NodeKind.COMPONENT: ("component", "module", "system", "frontend", "web", "ui", "app", "mobile"),
}

_MATRIX_MARKERS = {"1", "x", "y", "yes", "true", "✓", "✔", "→", "->"}
_NO_VALUES = {"", "0", "no", "n", "false", "-", "—"}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _text(value).lower())


def _text(value: Any) -> str:
    """Cell value as display text. Integral floats lose their '.0'."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _kind_from(text: str) -> NodeKind:
    key = _norm(text)
    if not key:
        return NodeKind.COMPONENT
    for kind in NodeKind:
        if key == _norm(kind.value):
            return kind
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for kind, words in _KIND_WORDS.items():  # whole words first: "Customer DB" -> database
        if key in words or any(t in words for t in tokens):
            return kind
    for kind, words in _KIND_WORDS.items():  # then substrings: "PaymentsService" -> service
        if any(w in key for w in words if len(w) > 3):
            return kind
    return NodeKind.UNKNOWN


def _direction_from(text: str) -> EdgeDirection:
    key = text.strip().lower()
    if key in {"both", "bidirectional", "bi", "two-way", "twoway", "<->", "<>", "↔"}:
        return EdgeDirection.BIDIRECTIONAL
    if key in {"none", "undirected", "-", "—", "line"}:
        return EdgeDirection.NONE
    return EdgeDirection.FORWARD


# --- graph builder -------------------------------------------------------------------------------


def _slug(text: str, prefix: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.:\-]+", "-", text).strip("-.")[:48] or "x"
    return f"{prefix}{s}"


@dataclass
class _Builder:
    nodes: dict[str, Node] = field(default_factory=dict)  # key: normalised name
    edges: list[Edge] = field(default_factory=list)
    groups: dict[str, Group] = field(default_factory=dict)
    _ids: set[str] = field(default_factory=set)
    _edge_keys: set[tuple[str, str, str]] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)

    def _unique(self, base: str) -> str:
        candidate, i = base, 2
        while candidate in self._ids:
            candidate = f"{base[:58]}-{i}"
            i += 1
        self._ids.add(candidate)
        return candidate

    def node(self, name: str) -> Node:
        key = name.strip().casefold()
        existing = self.nodes.get(key)
        if existing:
            return existing
        if len(self.nodes) >= MAX_NODES:
            raise XlsxImportError(f"The spreadsheet has more than {MAX_NODES} nodes.")
        node = Node(
            id=self._unique(_slug(name, "n-")),
            label=name.strip()[:MAX_LABEL],
            kind=NodeKind.COMPONENT,
            confidence=1.0,
            provenance=Provenance(origin=Origin.IMPORTED),
        )
        self.nodes[key] = node
        return node

    def edge(self, src: str, dst: str, label: str, direction: EdgeDirection) -> None:
        a, b = self.node(src), self.node(dst)
        if a.id == b.id:
            if len(self.warnings) < 20:
                self.warnings.append(f"Skipped self-connection on '{a.label}'.")
            return
        key = (a.id, b.id, label.casefold())
        if key in self._edge_keys:
            return
        if len(self.edges) >= MAX_EDGES:
            raise XlsxImportError(f"The spreadsheet has more than {MAX_EDGES} connections.")
        self._edge_keys.add(key)
        self.edges.append(
            Edge(
                id=f"e{len(self.edges) + 1}",
                source=a.id,
                target=b.id,
                label=label[:MAX_LABEL] or None,
                direction=direction,
                confidence=1.0,
                provenance=Provenance(origin=Origin.IMPORTED),
            )
        )

    def group(self, name: str) -> Group:
        key = name.strip().casefold()
        if key not in self.groups:
            self.groups[key] = Group(
                id=self._unique(_slug(name, "g-")),
                label=name.strip()[:MAX_LABEL],
                confidence=1.0,
                provenance=Provenance(origin=Origin.IMPORTED),
            )
        return self.groups[key]


# --- layout detection ----------------------------------------------------------------------------

Rows = list[tuple[Any, ...]]


def _find_columns(header: Sequence[Any], vocab: set[str]) -> int | None:
    for i, cell in enumerate(header):
        if _norm(cell) in vocab:
            return i
    return None


def _parse_edge_list(rows: Rows, b: _Builder) -> bool:
    for h, header in enumerate(rows[:HEADER_SEARCH_ROWS]):
        src = _find_columns(header, _SOURCE)
        dst = _find_columns(header, _TARGET)
        if src is None or dst is None or src == dst:
            continue
        lbl = _find_columns(header, _LABEL)
        if lbl in (src, dst):
            lbl = None
        dirc = _find_columns(header, _DIRECTION)

        def cell(row: tuple[Any, ...], i: int | None) -> str:
            return _text(row[i]) if i is not None and i < len(row) else ""

        for row in rows[h + 1 :]:
            a, z = cell(row, src), cell(row, dst)
            if a and z:
                b.edge(a, z, cell(row, lbl), _direction_from(cell(row, dirc)))
            elif a or z:
                b.node(a or z)
        return True
    return False


def _parse_matrix(rows: Rows, b: _Builder) -> bool:
    if len(rows) < 3:
        return False
    top = [_text(c) for c in rows[0][1:]]
    left = [_text(r[0]) if r else "" for r in rows[1:]]
    top_names = {t.casefold() for t in top if t}
    left_names = {s.casefold() for s in left if s}
    if len(top_names) < 2 or len(left_names) < 2:
        return False
    overlap = len(top_names & left_names) / max(len(top_names), len(left_names))
    if overlap < 0.5:
        return False

    for name in [*left, *top]:
        if name:
            b.node(name)
    for r, row in enumerate(rows[1:]):
        src = left[r]
        if not src:
            continue
        for c, value in enumerate(row[1:]):
            dst = top[c] if c < len(top) else ""
            text = _text(value)
            if not dst or text.lower() in _NO_VALUES:
                continue
            label = "" if text.lower() in _MATRIX_MARKERS else text
            b.edge(src, dst, label, EdgeDirection.FORWARD)
    return True


def _apply_nodes_sheet(rows: Rows, b: _Builder) -> None:
    for h, header in enumerate(rows[:HEADER_SEARCH_ROWS]):
        name_col = _find_columns(header, _NODE_ID)
        if name_col is None:
            continue
        label_col = _find_columns(header, _NODE_LABEL)
        kind_col = _find_columns(header, _NODE_KIND)
        group_col = _find_columns(header, _NODE_GROUP)
        for row in rows[h + 1 :]:
            name = _text(row[name_col]) if name_col < len(row) else ""
            if not name:
                continue
            node = b.node(name)
            if label_col is not None and label_col < len(row) and _text(row[label_col]):
                node.label = _text(row[label_col])[:MAX_LABEL]
            if kind_col is not None and kind_col < len(row) and _text(row[kind_col]):
                node.kind = _kind_from(_text(row[kind_col]))
            if group_col is not None and group_col < len(row) and _text(row[group_col]):
                node.group_id = b.group(_text(row[group_col])).id
        return


def _read_rows(values: Iterable[tuple[Any, ...]]) -> Rows:
    rows: Rows = []
    for i, row in enumerate(values):
        if i >= MAX_SCAN_ROWS:
            raise XlsxImportError(f"A sheet has more than {MAX_SCAN_ROWS} rows.")
        trimmed = tuple(row[:MAX_SCAN_COLS])
        if any(v is not None and _text(v) for v in trimmed):
            rows.append(trimmed)
    return rows


# --- entry point ---------------------------------------------------------------------------------


def import_xlsx(
    content: bytes, *, graph_id: str, upload_id: str | None = None, filename: str | None = None
) -> GraphDocument:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises many types for malformed workbooks
        raise XlsxImportError("The workbook could not be read.") from exc

    try:
        sheets = {ws.title: _read_rows(ws.iter_rows(values_only=True)) for ws in wb.worksheets}
    finally:
        wb.close()

    b = _Builder()
    nodes_sheet = next((t for t in sheets if t.strip().casefold() == "nodes"), None)
    used: str | None = None
    for title, rows in sheets.items():
        if title == nodes_sheet:
            continue
        if _parse_edge_list(rows, b) or _parse_matrix(rows, b):
            used = title
            break
    if used is None:
        raise XlsxImportError(
            "No graph found. Use a sheet with From/To columns (an edge list) or an adjacency "
            "matrix with node names across the first row and down the first column."
        )
    if nodes_sheet:
        _apply_nodes_sheet(sheets[nodes_sheet], b)

    other = [t for t in sheets if t not in (used, nodes_sheet)]
    if other:
        b.warnings.append(f"Imported sheet '{used}'; ignored: {', '.join(other)}.")

    return GraphDocument.model_validate(
        {
            "id": graph_id,
            "title": (filename or used).rsplit(".", 1)[0][:MAX_LABEL],
            "nodes": [n.model_dump() for n in b.nodes.values()],
            "edges": [e.model_dump() for e in b.edges],
            "groups": [g.model_dump() for g in b.groups.values()],
            "metadata": GraphMetadata(
                source=SourceInfo(kind=SourceKind.XLSX, upload_id=upload_id, filename=filename),
                provider="xlsx-import",
                warnings=b.warnings,
            ).model_dump(),
        }
    )

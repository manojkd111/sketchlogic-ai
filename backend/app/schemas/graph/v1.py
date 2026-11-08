"""SketchLogic graph schema, version 1.0.

This is the single source of truth for diagram data exchanged between the
model, the backend and the frontend. AI providers must emit a document that
validates against `GraphDocument`; the model never emits executable code.

Design invariants (enforced by validators below):
  * Every id is unique within its collection.
  * Edges reference existing nodes; nodes/groups reference existing groups.
  * Group nesting is acyclic.
  * Edges are explicitly `observed` (visibly drawn in the source) or
    `inferred` (guessed by the model). Inferred edges must carry a confidence
    below 1.0 so the UI can surface them for review.
  * Elements with `provenance.locked = True` (manual user corrections) are
    protected: automated modifications must go through an approval step.

Breaking changes require a new module (`v2.py`) and a migration; never edit
the meaning of an existing field in place.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION: Literal["1.0"] = "1.0"

ElementId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:\-]+$"),
]
Label = Annotated[str, StringConstraints(max_length=200)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NodeKind(StrEnum):
    COMPONENT = "component"
    SERVICE = "service"
    DATABASE = "database"
    QUEUE = "queue"
    STORAGE = "storage"
    ACTOR = "actor"
    EXTERNAL = "external"
    PROCESS = "process"
    DECISION = "decision"
    START_END = "start_end"
    NOTE = "note"
    UNKNOWN = "unknown"


class EdgeDirection(StrEnum):
    FORWARD = "forward"  # source -> target
    BIDIRECTIONAL = "bidirectional"
    NONE = "none"  # undirected association


class EdgeEvidence(StrEnum):
    OBSERVED = "observed"  # an arrow/line is visible in the source
    INFERRED = "inferred"  # model guessed it from context (proximity, naming, layout)


class Origin(StrEnum):
    AI_EXTRACTED = "ai_extracted"
    AI_MODIFIED = "ai_modified"
    USER_CREATED = "user_created"
    USER_CORRECTED = "user_corrected"
    IMPORTED = "imported"


class SourceKind(StrEnum):
    IMAGE = "image"
    XLSX = "xlsx"
    SKETCH = "sketch"
    MANUAL = "manual"


class Provenance(_Strict):
    origin: Origin = Origin.AI_EXTRACTED
    locked: bool = Field(
        default=False,
        description="True when a user manually corrected this element. "
        "Automated changes require explicit approval.",
    )

    @model_validator(mode="after")
    def _user_corrections_are_locked(self) -> Provenance:
        if self.origin is Origin.USER_CORRECTED and not self.locked:
            self.locked = True
        return self


class Position(_Strict):
    x: float
    y: float


class BoundingBox(_Strict):
    """Location in the source image, normalised to [0, 1]."""

    x: Confidence
    y: Confidence
    width: Confidence
    height: Confidence


class Node(_Strict):
    id: ElementId
    label: Label
    kind: NodeKind = NodeKind.COMPONENT
    group_id: ElementId | None = None
    position: Position | None = None
    source_bbox: BoundingBox | None = None
    confidence: Confidence = 1.0
    provenance: Provenance = Field(default_factory=Provenance)
    attributes: dict[str, str] = Field(default_factory=dict)


class Edge(_Strict):
    id: ElementId
    source: ElementId
    target: ElementId
    label: Label | None = None
    direction: EdgeDirection = EdgeDirection.FORWARD
    evidence: EdgeEvidence = EdgeEvidence.OBSERVED
    confidence: Confidence = 1.0
    rationale: Annotated[str, StringConstraints(max_length=500)] | None = Field(
        default=None, description="Why the model inferred this edge (inferred edges only)."
    )
    provenance: Provenance = Field(default_factory=Provenance)

    @model_validator(mode="after")
    def _inferred_edges_are_uncertain(self) -> Edge:
        if self.evidence is EdgeEvidence.INFERRED and self.confidence >= 1.0:
            raise ValueError(
                f"edge '{self.id}': inferred edges must have confidence < 1.0 "
                "so they can be surfaced for review"
            )
        return self


class Group(_Strict):
    id: ElementId
    label: Label
    parent_id: ElementId | None = None
    confidence: Confidence = 1.0
    provenance: Provenance = Field(default_factory=Provenance)


class SourceInfo(_Strict):
    kind: SourceKind
    upload_id: str | None = None
    filename: Label | None = None
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)


class GraphMetadata(_Strict):
    source: SourceInfo | None = None
    provider: str | None = Field(default=None, description="Inference provider id, e.g. 'local'.")
    model: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    warnings: list[str] = Field(default_factory=list)


class GraphDocument(_Strict):
    """A complete, versioned diagram."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: ElementId
    title: Label = ""
    nodes: list[Node] = Field(default_factory=list, max_length=2000)
    edges: list[Edge] = Field(default_factory=list, max_length=5000)
    groups: list[Group] = Field(default_factory=list, max_length=500)
    metadata: GraphMetadata = Field(default_factory=GraphMetadata)

    @model_validator(mode="after")
    def _check_referential_integrity(self) -> GraphDocument:
        errors: list[str] = []

        def _dupes(ids: list[str]) -> list[str]:
            return [i for i, count in Counter(ids).items() if count > 1]

        node_ids = [n.id for n in self.nodes]
        edge_ids = [e.id for e in self.edges]
        group_ids = [g.id for g in self.groups]
        for name, ids in (("node", node_ids), ("edge", edge_ids), ("group", group_ids)):
            for d in sorted(_dupes(ids)):
                errors.append(f"duplicate {name} id '{d}'")

        nodes, groups = set(node_ids), set(group_ids)
        for e in self.edges:
            for end in ("source", "target"):
                ref = getattr(e, end)
                if ref not in nodes:
                    errors.append(f"edge '{e.id}' {end} '{ref}' is not a known node")
        for n in self.nodes:
            if n.group_id is not None and n.group_id not in groups:
                errors.append(f"node '{n.id}' group_id '{n.group_id}' is not a known group")
        parents = {g.id: g.parent_id for g in self.groups}
        for g in self.groups:
            if g.parent_id is not None and g.parent_id not in groups:
                errors.append(f"group '{g.id}' parent_id '{g.parent_id}' is not a known group")

        # Cycle detection in group nesting.
        for start in parents:
            seen_chain: set[str] = set()
            cur: str | None = start
            while cur is not None and cur in parents:
                if cur in seen_chain:
                    errors.append(f"group nesting cycle involving '{start}'")
                    break
                seen_chain.add(cur)
                cur = parents[cur]

        if errors:
            raise ValueError("; ".join(errors))
        return self

    # Convenience accessors -------------------------------------------------
    def inferred_edges(self) -> list[Edge]:
        return [e for e in self.edges if e.evidence is EdgeEvidence.INFERRED]

    def locked_element_ids(self) -> set[str]:
        items: list[Node | Edge | Group] = [*self.nodes, *self.edges, *self.groups]
        return {i.id for i in items if i.provenance.locked}

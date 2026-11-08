"""Versioned graph schema. Import the current version from here; pin a version module explicitly
(`app.schemas.graph.v1`) when you need stability across upgrades."""

from app.schemas.graph.v1 import (
    SCHEMA_VERSION,
    BoundingBox,
    Edge,
    EdgeDirection,
    EdgeEvidence,
    GraphDocument,
    GraphMetadata,
    Group,
    Node,
    NodeKind,
    Origin,
    Position,
    Provenance,
    SourceInfo,
    SourceKind,
)

SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("1.0",)
CURRENT_SCHEMA_VERSION = SCHEMA_VERSION

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "BoundingBox",
    "Edge",
    "EdgeDirection",
    "EdgeEvidence",
    "GraphDocument",
    "GraphMetadata",
    "Group",
    "Node",
    "NodeKind",
    "Origin",
    "Position",
    "Provenance",
    "SourceInfo",
    "SourceKind",
]

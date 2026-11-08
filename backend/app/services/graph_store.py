"""Graph persistence: every save appends an immutable version.

Saves through this service are *user* saves from the editor. Automated changes (AI
modifications, re-extraction) must not call `save_graph` directly on documents with
locked elements; they will go through a proposal/approval flow (Phase 3).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from app.db.repository import (
    Database,
    GraphExistsError,
    GraphNotFoundError,
    GraphRow,
    GraphVersionConflictError,
    GraphVersionInfo,
    utcnow,
)
from app.schemas.graph import GraphDocument


class GraphErrorCode(StrEnum):
    GRAPH_EXISTS = "graph_exists"
    GRAPH_NOT_FOUND = "graph_not_found"
    VERSION_NOT_FOUND = "graph_version_not_found"
    VERSION_CONFLICT = "graph_version_conflict"
    ID_MISMATCH = "graph_id_mismatch"


class GraphStoreError(Exception):
    def __init__(
        self,
        code: GraphErrorCode,
        message: str,
        *,
        status_code: int,
        current_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.current_version = current_version


class GraphRecord(BaseModel):
    id: str
    title: str
    version: int
    created_at: datetime
    updated_at: datetime
    document: GraphDocument


def _not_found(graph_id: str) -> GraphStoreError:
    return GraphStoreError(
        GraphErrorCode.GRAPH_NOT_FOUND, f"Graph '{graph_id}' not found.", status_code=404
    )


def _record(row: GraphRow, version: int, document_json: str) -> GraphRecord:
    return GraphRecord(
        id=row.id,
        title=row.title,
        version=version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        document=GraphDocument.model_validate_json(document_json),
    )


def create_graph(db: Database, doc: GraphDocument) -> GraphRecord:
    try:
        db.create_graph(doc.id, doc.title, doc.schema_version, doc.model_dump_json(), utcnow())
    except GraphExistsError as exc:
        raise GraphStoreError(
            GraphErrorCode.GRAPH_EXISTS,
            f"Graph '{doc.id}' already exists. Use PUT to save a new version.",
            status_code=409,
        ) from exc
    return get_graph(db, doc.id)


def save_graph(db: Database, graph_id: str, base_version: int, doc: GraphDocument) -> GraphRecord:
    if doc.id != graph_id:
        raise GraphStoreError(
            GraphErrorCode.ID_MISMATCH,
            f"Document id '{doc.id}' does not match graph '{graph_id}'.",
            status_code=422,
        )
    try:
        db.update_graph(
            graph_id, base_version, doc.title, doc.schema_version, doc.model_dump_json(), utcnow()
        )
    except GraphNotFoundError as exc:
        raise _not_found(graph_id) from exc
    except GraphVersionConflictError as exc:
        raise GraphStoreError(
            GraphErrorCode.VERSION_CONFLICT,
            f"Graph was changed elsewhere (now at version {exc.current_version}). "
            "Reload it before saving.",
            status_code=409,
            current_version=exc.current_version,
        ) from exc
    return get_graph(db, graph_id)


def get_graph(db: Database, graph_id: str, version: int | None = None) -> GraphRecord:
    row = db.get_graph(graph_id)
    if row is None:
        raise _not_found(graph_id)
    v = db.get_graph_version(graph_id, version or row.current_version)
    if v is None:
        raise GraphStoreError(
            GraphErrorCode.VERSION_NOT_FOUND,
            f"Graph '{graph_id}' has no version {version}.",
            status_code=404,
        )
    return _record(row, v.version, v.document)


def list_versions(db: Database, graph_id: str) -> list[GraphVersionInfo]:
    if db.get_graph(graph_id) is None:
        raise _not_found(graph_id)
    return db.list_graph_versions(graph_id)

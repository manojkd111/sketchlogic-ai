from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbDep
from app.db.repository import GraphVersionInfo
from app.schemas.graph import CURRENT_SCHEMA_VERSION, GraphDocument
from app.services import graph_store
from app.services.graph_ops import graph_summary
from app.services.graph_store import GraphRecord

router = APIRouter(tags=["graphs"])

GraphId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:\-]+$")]


class GraphValidationResponse(BaseModel):
    valid: bool
    schema_version: str
    summary: dict[str, Any]


class GraphListItem(BaseModel):
    id: str
    title: str
    version: int
    updated_at: datetime


class SaveGraphRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_version: int = Field(ge=1, description="The version this edit started from.")
    document: GraphDocument


@router.get("/schema/graph")
def graph_json_schema() -> dict[str, Any]:
    """JSON Schema for the current GraphDocument version (used by frontend & ML)."""
    return GraphDocument.model_json_schema()


@router.post("/graphs/validate", response_model=GraphValidationResponse)
def validate_graph(doc: GraphDocument) -> GraphValidationResponse:
    """Validate a GraphDocument. Invalid documents return 422 with field-level errors."""
    return GraphValidationResponse(
        valid=True, schema_version=CURRENT_SCHEMA_VERSION, summary=graph_summary(doc)
    )


@router.get("/graphs", response_model=list[GraphListItem])
def list_graphs(db: DbDep, limit: int = Query(100, ge=1, le=500)) -> list[GraphListItem]:
    return [
        GraphListItem(id=r.id, title=r.title, version=r.current_version, updated_at=r.updated_at)
        for r in db.list_graphs(limit)
    ]


@router.post("/graphs", response_model=GraphRecord, status_code=status.HTTP_201_CREATED)
def create_graph(doc: GraphDocument, db: DbDep) -> GraphRecord:
    """Store a new graph as version 1. The document id becomes the graph id."""
    return graph_store.create_graph(db, doc)


@router.get("/graphs/{graph_id}", response_model=GraphRecord)
def get_graph(graph_id: GraphId, db: DbDep) -> GraphRecord:
    return graph_store.get_graph(db, graph_id)


@router.put("/graphs/{graph_id}", response_model=GraphRecord)
def save_graph(graph_id: GraphId, body: SaveGraphRequest, db: DbDep) -> GraphRecord:
    """Save a user edit as a new version. Fails with 409 if `base_version` is stale."""
    return graph_store.save_graph(db, graph_id, body.base_version, body.document)


@router.get("/graphs/{graph_id}/versions", response_model=list[GraphVersionInfo])
def list_graph_versions(graph_id: GraphId, db: DbDep) -> list[GraphVersionInfo]:
    return graph_store.list_versions(db, graph_id)


@router.get("/graphs/{graph_id}/versions/{version}", response_model=GraphRecord)
def get_graph_version(
    graph_id: GraphId, db: DbDep, version: Annotated[int, Path(ge=1)]
) -> GraphRecord:
    return graph_store.get_graph(db, graph_id, version)

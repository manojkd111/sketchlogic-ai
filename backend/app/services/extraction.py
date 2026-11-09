"""Upload -> GraphDocument extraction via the configured InferenceProvider.

Extraction never overwrites an existing graph: if this upload was already extracted, the stored
graph (which may contain user corrections) is returned unchanged. Re-extraction that proposes
changes against locked elements is a Phase 3 feature.
"""

from __future__ import annotations

from app.core.config import Settings
from app.db.repository import Database
from app.inference.base import ExtractionRequest, ProviderUnavailableError
from app.inference.providers import get_provider
from app.schemas.graph import GraphDocument, SourceKind
from app.services import graph_store
from app.services.graph_store import GraphErrorCode, GraphRecord, GraphStoreError


def graph_id_for_upload(upload_id: str) -> str:
    return f"graph-{upload_id}"


def extract_upload(db: Database, settings: Settings, upload_id: str) -> tuple[GraphRecord, bool]:
    """Return `(record, created)`. `created` is False when the graph already existed."""
    row = db.get_upload(upload_id)
    if row is None:
        raise GraphStoreError(
            GraphErrorCode.UPLOAD_NOT_FOUND, f"Upload '{upload_id}' not found.", status_code=404
        )

    graph_id = graph_id_for_upload(upload_id)
    if db.get_graph(graph_id) is not None:
        return graph_store.get_graph(db, graph_id), False

    content = (settings.uploads_dir / row.storage_path).read_bytes()
    request = ExtractionRequest(
        upload_id=upload_id,
        source_kind=SourceKind.XLSX if row.kind == "xlsx" else SourceKind.IMAGE,
        media_type=row.media_type,
        content=content,
    )
    try:
        provider = get_provider(settings)
        raw = provider.extract_graph(request)
    except ProviderUnavailableError as exc:
        raise GraphStoreError(
            GraphErrorCode.PROVIDER_UNAVAILABLE, str(exc), status_code=503
        ) from exc

    # Re-validate provider output from plain data: providers return structured data only, and
    # we never trust an in-memory object to have passed validation. The graph id is ours.
    data = raw.model_dump(mode="json")
    data["id"] = graph_id
    doc = GraphDocument.model_validate(data)
    return graph_store.create_graph(db, doc), True

"""Upload -> GraphDocument extraction.

Images go to the configured InferenceProvider; .xlsx workbooks are parsed deterministically by
`xlsx_import` (no model involved).

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
from app.services.xlsx_import import XlsxImportError, import_xlsx


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

    # Spreadsheets hold the graph as data: parse them deterministically, no model needed.
    if row.kind == "xlsx":
        try:
            doc = import_xlsx(
                content, graph_id=graph_id, upload_id=upload_id, filename=row.original_name
            )
        except XlsxImportError as exc:
            raise GraphStoreError(GraphErrorCode.XLSX_NO_GRAPH, str(exc), status_code=422) from exc
        return graph_store.create_graph(db, doc), True

    request = ExtractionRequest(
        upload_id=upload_id,
        source_kind=SourceKind.IMAGE,
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

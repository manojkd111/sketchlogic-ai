from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.inference.base import ExtractionRequest, ProviderUnavailableError
from app.inference.providers import BedrockProvider, MockProvider, get_provider
from app.schemas.graph import (
    EdgeEvidence,
    GraphDocument,
    Origin,
    Provenance,
    SourceKind,
)
from app.services.graph_ops import graph_summary, to_networkx

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_SCHEMA = REPO_ROOT / "shared" / "schemas" / "graph.v1.json"
EXAMPLE = REPO_ROOT / "shared" / "examples" / "three-tier.graph.json"


def _doc(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "g1",
        "title": "Test",
        "groups": [{"id": "vpc", "label": "VPC"}],
        "nodes": [
            {"id": "a", "label": "Client", "kind": "actor"},
            {"id": "b", "label": "API", "kind": "service", "group_id": "vpc"},
        ],
        "edges": [{"id": "e1", "source": "a", "target": "b", "label": "HTTPS"}],
    }
    base.update(overrides)
    return base


def test_minimal_document_defaults() -> None:
    doc = GraphDocument.model_validate(_doc())
    assert doc.schema_version == "1.0"
    assert doc.edges[0].evidence is EdgeEvidence.OBSERVED
    assert doc.nodes[0].provenance.origin is Origin.AI_EXTRACTED


def test_rejects_unknown_schema_version() -> None:
    with pytest.raises(ValidationError):
        GraphDocument.model_validate(_doc(schema_version="2.0"))


def test_rejects_extra_fields() -> None:
    # AI output must be pure data in the agreed shape; no smuggled fields (e.g. code).
    with pytest.raises(ValidationError, match="extra"):
        GraphDocument.model_validate(_doc(render="<script>alert(1)</script>"))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"edges": [{"id": "e1", "source": "a", "target": "zzz"}]}, "not a known node"),
        (
            {"nodes": [{"id": "a", "label": "A"}, {"id": "a", "label": "dup"}], "edges": []},
            "duplicate node id",
        ),
        ({"nodes": [{"id": "a", "label": "A", "group_id": "nope"}], "edges": []}, "known group"),
        (
            {
                "groups": [
                    {"id": "g1", "label": "1", "parent_id": "g2"},
                    {"id": "g2", "label": "2", "parent_id": "g1"},
                ],
                "nodes": [],
                "edges": [],
            },
            "cycle",
        ),
    ],
)
def test_referential_integrity(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GraphDocument.model_validate(_doc(**overrides))


def test_inferred_edges_must_be_uncertain() -> None:
    edge = {"id": "e1", "source": "a", "target": "b", "evidence": "inferred", "confidence": 1.0}
    with pytest.raises(ValidationError, match=r"confidence < 1\.0"):
        GraphDocument.model_validate(_doc(edges=[edge]))
    edge["confidence"] = 0.55
    doc = GraphDocument.model_validate(_doc(edges=[edge]))
    assert [e.id for e in doc.inferred_edges()] == ["e1"]


def test_user_corrections_are_always_locked() -> None:
    assert Provenance(origin=Origin.USER_CORRECTED).locked is True
    nodes = [{"id": "a", "label": "A", "provenance": {"origin": "user_corrected"}}]
    doc = GraphDocument.model_validate(_doc(nodes=nodes, edges=[], groups=[]))
    assert doc.locked_element_ids() == {"a"}


def test_rejects_invalid_ids_and_confidence() -> None:
    with pytest.raises(ValidationError):
        GraphDocument.model_validate(_doc(id="has spaces"))
    with pytest.raises(ValidationError):
        GraphDocument.model_validate(
            _doc(nodes=[{"id": "a", "label": "A", "confidence": 1.5}], edges=[])
        )


def test_networkx_conversion_and_summary() -> None:
    edges = [
        {"id": "e1", "source": "a", "target": "b", "direction": "bidirectional"},
    ]
    doc = GraphDocument.model_validate(_doc(edges=edges))
    g = to_networkx(doc)
    assert g.has_edge("a", "b") and g.has_edge("b", "a")
    s = graph_summary(doc)
    assert s["node_count"] == 2
    assert s["edge_count"] == 1
    assert s["is_acyclic"] is False


def test_json_roundtrip() -> None:
    doc = GraphDocument.model_validate(_doc())
    again = GraphDocument.model_validate_json(doc.model_dump_json())
    assert again == doc


def test_shared_json_schema_is_up_to_date() -> None:
    """shared/schemas/graph.v1.json must match the Pydantic model.
    Regenerate with: python -m scripts.export_schema"""
    assert SHARED_SCHEMA.exists(), "run `python -m scripts.export_schema` from backend/"
    committed = json.loads(SHARED_SCHEMA.read_text(encoding="utf-8"))
    assert committed == GraphDocument.model_json_schema()


def test_shared_example_validates() -> None:
    doc = GraphDocument.model_validate_json(EXAMPLE.read_text(encoding="utf-8"))
    assert doc.inferred_edges(), "example should demonstrate an inferred edge"


def test_validate_endpoint(client: TestClient) -> None:
    ok = client.post("/api/v1/graphs/validate", json=_doc())
    assert ok.status_code == 200
    assert ok.json()["summary"]["node_count"] == 2
    bad = client.post(
        "/api/v1/graphs/validate", json=_doc(edges=[{"id": "e", "source": "a", "target": "x"}])
    )
    assert bad.status_code == 422


def test_schema_endpoint(client: TestClient) -> None:
    r = client.get("/api/v1/schema/graph")
    assert r.status_code == 200
    assert r.json()["title"] == "GraphDocument"


def test_mock_provider_emits_valid_graph() -> None:
    doc = MockProvider().extract_graph(
        ExtractionRequest(
            upload_id="u1", source_kind=SourceKind.IMAGE, media_type="image/png", content=b""
        )
    )
    GraphDocument.model_validate(doc.model_dump())
    assert doc.inferred_edges()


def test_bedrock_disabled_by_default(tmp_path: Path) -> None:
    s = Settings(data_dir=tmp_path)
    assert s.aws_enabled is False
    with pytest.raises(ProviderUnavailableError):
        BedrockProvider(s)
    with pytest.raises(ValidationError, match="AWS"):
        Settings(data_dir=tmp_path, inference_provider="bedrock")
    assert get_provider(s).name == "mock"

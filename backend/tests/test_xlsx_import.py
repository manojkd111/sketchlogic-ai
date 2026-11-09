from __future__ import annotations

import io
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.schemas.graph import EdgeDirection, EdgeEvidence, GraphDocument, NodeKind, Origin
from app.services import xlsx_import
from app.services.xlsx_import import XlsxImportError, import_xlsx

ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]+$")


def workbook(sheets: dict[str, list[list[Any]]]) -> bytes:
    wb = Workbook()
    first = True
    for title, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        assert ws is not None
        ws.title = title
        for row in rows:
            ws.append(row)
        first = False
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def load(sheets: dict[str, list[list[Any]]], **kw: Any) -> GraphDocument:
    return import_xlsx(workbook(sheets), graph_id="g1", **kw)


def labels(doc: GraphDocument) -> dict[str, str]:
    return {n.id: n.label for n in doc.nodes}


def edge_pairs(doc: GraphDocument) -> list[tuple[str, str, str | None]]:
    by_id = labels(doc)
    return [(by_id[e.source], by_id[e.target], e.label) for e in doc.edges]


# Edge lists -----------------------------------------------------------------------------------


def test_simple_edge_list() -> None:
    doc = load({"Flow": [["From", "To", "Label"], ["Client", "API", "HTTPS"], ["API", "DB", None]]})
    assert edge_pairs(doc) == [("Client", "API", "HTTPS"), ("API", "DB", None)]
    assert all(e.evidence is EdgeEvidence.OBSERVED and e.confidence == 1.0 for e in doc.edges)
    assert all(el.provenance.origin is Origin.IMPORTED for el in [*doc.nodes, *doc.edges])
    assert not any(el.provenance.locked for el in [*doc.nodes, *doc.edges])
    assert doc.metadata.provider == "xlsx-import"
    assert all(n.position is None for n in doc.nodes)  # editor lays it out


def test_header_synonyms_title_row_numbers_and_blank_rows() -> None:
    doc = load(
        {
            "Sheet1": [
                ["Payment system dependencies"],
                [],
                ["Source", "Notes", "Target", "Relationship"],
                ["Checkout", "x", "Payments", "calls"],
                [None, None, None, None],
                [101, None, 202.0, None],
            ]
        }
    )
    assert edge_pairs(doc) == [("Checkout", "Payments", "calls"), ("101", "202", None)]


def test_direction_column_duplicates_case_and_self_loops() -> None:
    doc = load(
        {
            "E": [
                ["from", "to", "direction"],
                ["A", "B", "both"],
                ["a", "b", "both"],  # same nodes (case-insensitive), same label -> duplicate
                ["B", "C", "none"],
                ["C", "C", ""],
            ]
        }
    )
    assert [e.direction for e in doc.edges] == [EdgeDirection.BIDIRECTIONAL, EdgeDirection.NONE]
    assert sorted(n.label for n in doc.nodes) == ["A", "B", "C"]
    assert any("self-connection" in w for w in doc.metadata.warnings)


def test_row_with_one_end_adds_an_unconnected_node() -> None:
    doc = load({"E": [["From", "To"], ["A", "B"], ["Lonely", None]]})
    assert sorted(n.label for n in doc.nodes) == ["A", "B", "Lonely"]
    assert len(doc.edges) == 1


def test_ids_are_schema_safe_and_unique_even_when_names_collide() -> None:
    long_name = "Ünïcödé service / with <weird> chars & a very long name " * 3
    doc = load({"E": [["From", "To"], ["API", "api!"], ["api?", long_name]]})
    ids = [n.id for n in doc.nodes]
    assert len(ids) == len(set(ids))
    assert all(ID_RE.match(i) and len(i) <= 64 for i in ids)
    assert len(next(n.label for n in doc.nodes if n.label.startswith("Ünï"))) <= 200


def test_formulas_are_never_imported_or_evaluated() -> None:
    # Written without cached values, so data_only reads them as empty.
    doc = load(
        {
            "E": [
                ["From", "To", "Label"],
                ["A", "B", '=HYPERLINK("http://evil.example","click")'],
                ['=CONCAT("x","y")', "C", "ok"],
            ]
        }
    )
    assert edge_pairs(doc) == [("A", "B", None)]
    assert all("=" not in n.label for n in doc.nodes)
    assert sorted(n.label for n in doc.nodes) == ["A", "B", "C"]


# Adjacency matrix -----------------------------------------------------------------------------


def test_adjacency_matrix_with_markers_labels_and_no_values() -> None:
    doc = load(
        {
            "Matrix": [
                [None, "Web", "API", "DB"],
                ["Web", None, "x", 0],
                ["API", "no", None, "SQL"],
                ["DB", "", None, None],
            ]
        }
    )
    assert edge_pairs(doc) == [("Web", "API", None), ("API", "DB", "SQL")]


def test_matrix_needs_matching_row_and_column_names() -> None:
    with pytest.raises(XlsxImportError, match="No graph found"):
        load({"Data": [["Month", "Q1", "Q2"], ["Revenue", 1, 2], ["Cost", 3, 4]]})


# Nodes sheet, sheet choice --------------------------------------------------------------------


def test_nodes_sheet_sets_kinds_labels_and_groups() -> None:
    doc = load(
        {
            "Nodes": [
                ["Name", "Type", "Group", "Label"],
                ["Customer DB", "Customer DB", "Private subnet", "Customers (Postgres)"],
                ["User Service", "microservice", "Private subnet", None],
                ["Shopper", "user", None, None],
                ["Mystery", "flux capacitor", None, None],
                ["Storefront", "frontend", None, None],
            ],
            "Edges": [["From", "To"], ["Shopper", "User Service"], ["User Service", "Customer DB"]],
        }
    )
    kinds = {n.label: n.kind for n in doc.nodes}
    assert kinds == {
        "Shopper": NodeKind.ACTOR,
        "User Service": NodeKind.SERVICE,
        "Customers (Postgres)": NodeKind.DATABASE,
        "Mystery": NodeKind.UNKNOWN,
        "Storefront": NodeKind.COMPONENT,
    }
    assert [g.label for g in doc.groups] == ["Private subnet"]
    gid = doc.groups[0].id
    assert {n.label for n in doc.nodes if n.group_id == gid} == {
        "Customers (Postgres)",
        "User Service",
    }


def test_first_recognisable_sheet_wins_and_others_are_reported() -> None:
    doc = load(
        {
            "Readme": [["This workbook describes our system"]],
            "Flow": [["From", "To"], ["A", "B"]],
            "Old": [["From", "To"], ["X", "Y"]],
        }
    )
    assert edge_pairs(doc) == [("A", "B", None)]
    assert any("ignored: Readme, Old" in w for w in doc.metadata.warnings)


def test_title_comes_from_filename() -> None:
    doc = load({"E": [["From", "To"], ["A", "B"]]}, filename="checkout-flow.xlsx")
    assert doc.title == "checkout-flow"
    assert doc.metadata.source is not None and doc.metadata.source.filename == "checkout-flow.xlsx"


# Rejections -----------------------------------------------------------------------------------


def test_unrecognised_workbook() -> None:
    with pytest.raises(XlsxImportError, match="From/To"):
        load({"Notes": [["hello"], ["world"]]})


def test_unreadable_workbook() -> None:
    with pytest.raises(XlsxImportError, match="could not be read"):
        import_xlsx(b"PK\x03\x04 not really a workbook", graph_id="g1")


def test_too_many_edges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xlsx_import, "MAX_EDGES", 3)
    rows: list[list[Any]] = [["From", "To"]] + [[f"a{i}", f"b{i}"] for i in range(5)]
    with pytest.raises(XlsxImportError, match="more than 3 connections"):
        load({"E": rows})


def test_too_many_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(xlsx_import, "MAX_SCAN_ROWS", 4)
    rows: list[list[Any]] = [["From", "To"]] + [[f"a{i}", f"b{i}"] for i in range(10)]
    with pytest.raises(XlsxImportError, match="more than 4 rows"):
        load({"E": rows})


# Through the API ------------------------------------------------------------------------------


def _upload(client: TestClient, data: bytes, name: str = "flow.xlsx") -> str:
    r = client.post("/api/v1/uploads", files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 201, r.text
    upload_id: str = r.json()["id"]
    return upload_id


def test_extract_endpoint_imports_xlsx(client: TestClient, xlsx_bytes: bytes) -> None:
    upload_id = _upload(client, xlsx_bytes)
    r = client.post(f"/api/v1/uploads/{upload_id}/extract")
    assert r.status_code == 201, r.text
    doc = r.json()["document"]
    assert doc["metadata"]["source"]["kind"] == "xlsx"
    assert doc["metadata"]["provider"] == "xlsx-import"
    assert [n["label"] for n in doc["nodes"]] == ["Client", "API"]
    assert doc["edges"][0]["label"] == "HTTPS"
    assert any("ignored: Notes" in w for w in doc["metadata"]["warnings"])


def test_extract_endpoint_rejects_workbook_without_graph(client: TestClient) -> None:
    upload_id = _upload(client, workbook({"Notes": [["just"], ["text"]]}))
    r = client.post(f"/api/v1/uploads/{upload_id}/extract")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "xlsx_no_graph"
    assert client.get(f"/api/v1/graphs/graph-{upload_id}").status_code == 404

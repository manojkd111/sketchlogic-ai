from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.repository import Database

GRAPHS = "/api/v1/graphs"


def _doc(graph_id: str = "g1", **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": graph_id,
        "title": "Checkout",
        "nodes": [
            {"id": "a", "label": "Client", "kind": "actor"},
            {"id": "b", "label": "API", "kind": "service"},
        ],
        "edges": [
            {
                "id": "e1",
                "source": "a",
                "target": "b",
                "evidence": "inferred",
                "confidence": 0.6,
                "rationale": "Adjacent boxes.",
            }
        ],
    }
    base.update(overrides)
    return base


def _create(client: TestClient, **kw: Any) -> dict[str, Any]:
    r = client.post(GRAPHS, json=_doc(**kw))
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


# Happy paths ---------------------------------------------------------------


def test_create_then_get(client: TestClient) -> None:
    created = _create(client)
    assert created["version"] == 1
    assert created["document"]["edges"][0]["evidence"] == "inferred"

    got = client.get(f"{GRAPHS}/g1")
    assert got.status_code == 200
    assert got.json() == created


def test_put_appends_versions_and_history_is_immutable(client: TestClient) -> None:
    _create(client)
    edited = _doc(title="Checkout v2")
    edited["nodes"][1]["label"] = "Orders API"
    edited["nodes"][1]["provenance"] = {"origin": "user_corrected"}

    r = client.put(f"{GRAPHS}/g1", json={"base_version": 1, "document": edited})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2
    assert body["title"] == "Checkout v2"
    # Manual correction stays locked after the round-trip through storage.
    assert body["document"]["nodes"][1]["provenance"] == {
        "origin": "user_corrected",
        "locked": True,
    }

    versions = client.get(f"{GRAPHS}/g1/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    v1 = client.get(f"{GRAPHS}/g1/versions/1").json()
    assert v1["document"]["nodes"][1]["label"] == "API"
    assert v1["version"] == 1


def test_list_graphs(client: TestClient) -> None:
    _create(client, graph_id="g1")
    _create(client, graph_id="g2")
    items = client.get(GRAPHS).json()
    assert {i["id"] for i in items} == {"g1", "g2"}
    assert all(i["version"] == 1 for i in items)


def test_persists_across_app_restarts(client: TestClient, settings: Settings) -> None:
    _create(client)
    db = Database(settings.database_path)
    row = db.get_graph("g1")
    assert row is not None and row.current_version == 1


# Rejections ----------------------------------------------------------------


def test_create_duplicate_is_409(client: TestClient) -> None:
    _create(client)
    r = client.post(GRAPHS, json=_doc())
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "graph_exists"


def test_create_invalid_document_is_422_and_not_stored(client: TestClient) -> None:
    bad = _doc(edges=[{"id": "e", "source": "a", "target": "missing"}])
    assert client.post(GRAPHS, json=bad).status_code == 422
    assert client.get(f"{GRAPHS}/g1").status_code == 404


def test_create_rejects_extra_fields(client: TestClient) -> None:
    r = client.post(GRAPHS, json=_doc(render="<script>alert(1)</script>"))
    assert r.status_code == 422


def test_stale_put_is_409_with_current_version(client: TestClient) -> None:
    _create(client)
    first = client.put(f"{GRAPHS}/g1", json={"base_version": 1, "document": _doc(title="A")})
    assert first.status_code == 200
    stale = client.put(f"{GRAPHS}/g1", json={"base_version": 1, "document": _doc(title="B")})
    assert stale.status_code == 409
    err = stale.json()["error"]
    assert err["code"] == "graph_version_conflict"
    assert err["current_version"] == 2
    # The losing write left no trace.
    assert client.get(f"{GRAPHS}/g1").json()["title"] == "A"
    assert len(client.get(f"{GRAPHS}/g1/versions").json()) == 2


def test_put_id_mismatch_is_422(client: TestClient) -> None:
    _create(client)
    r = client.put(f"{GRAPHS}/g1", json={"base_version": 1, "document": _doc("other")})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "graph_id_mismatch"


def test_put_unknown_graph_is_404(client: TestClient) -> None:
    r = client.put(f"{GRAPHS}/nope", json={"base_version": 1, "document": _doc("nope")})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "graph_not_found"


def test_put_invalid_body_is_422(client: TestClient) -> None:
    _create(client)
    assert client.put(f"{GRAPHS}/g1", json={"document": _doc()}).status_code == 422
    assert (
        client.put(f"{GRAPHS}/g1", json={"base_version": 0, "document": _doc()}).status_code == 422
    )
    assert (
        client.put(
            f"{GRAPHS}/g1", json={"base_version": 1, "document": _doc(), "force": True}
        ).status_code
        == 422
    )


def test_get_unknown_graph_and_version_404(client: TestClient) -> None:
    assert client.get(f"{GRAPHS}/missing").json()["error"]["code"] == "graph_not_found"
    assert client.get(f"{GRAPHS}/missing/versions").status_code == 404
    _create(client)
    r = client.get(f"{GRAPHS}/g1/versions/9")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "graph_version_not_found"


def test_rejects_malformed_graph_id(client: TestClient) -> None:
    assert client.get(f"{GRAPHS}/has%20space").status_code == 422
    assert client.get(f"{GRAPHS}/" + "x" * 65).status_code == 422

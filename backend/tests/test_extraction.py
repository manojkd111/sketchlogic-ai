from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings


def _upload(client: TestClient, png_bytes: bytes) -> str:
    r = client.post("/api/v1/uploads", files={"file": ("board.png", png_bytes, "image/png")})
    assert r.status_code == 201, r.text
    upload_id: str = r.json()["id"]
    return upload_id


def test_extract_creates_graph_from_upload(client: TestClient, png_bytes: bytes) -> None:
    upload_id = _upload(client, png_bytes)
    r = client.post(f"/api/v1/uploads/{upload_id}/extract")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] == f"graph-{upload_id}"
    assert body["version"] == 1
    assert body["document"]["metadata"]["source"]["upload_id"] == upload_id
    assert any(e["evidence"] == "inferred" for e in body["document"]["edges"])
    assert client.get(f"/api/v1/graphs/graph-{upload_id}").status_code == 200


def test_reextract_never_overwrites_user_edits(client: TestClient, png_bytes: bytes) -> None:
    upload_id = _upload(client, png_bytes)
    created = client.post(f"/api/v1/uploads/{upload_id}/extract").json()
    doc = created["document"]
    doc["nodes"][0]["label"] = "Customer"
    doc["nodes"][0]["provenance"] = {"origin": "user_corrected", "locked": True}
    saved = client.put(f"/api/v1/graphs/{created['id']}", json={"base_version": 1, "document": doc})
    assert saved.status_code == 200

    again = client.post(f"/api/v1/uploads/{upload_id}/extract")
    assert again.status_code == 200
    assert again.json()["version"] == 2
    assert again.json()["document"]["nodes"][0]["label"] == "Customer"


def test_extract_unknown_upload_is_404(client: TestClient) -> None:
    r = client.post(f"/api/v1/uploads/{'0' * 32}/extract")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "upload_not_found"
    assert client.post("/api/v1/uploads/not-hex/extract").status_code == 404


def test_extract_with_unavailable_provider_is_503(
    client: TestClient, settings: Settings, png_bytes: bytes
) -> None:
    upload_id = _upload(client, png_bytes)
    settings.inference_provider = "local"  # not implemented yet
    r = client.post(f"/api/v1/uploads/{upload_id}/extract")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "provider_unavailable"
    assert client.get(f"/api/v1/graphs/graph-{upload_id}").status_code == 404

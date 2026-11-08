"""Smoke tests: the app boots and every Phase 1 route responds."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.smoke


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["graph_schema_version"] == "1.0"
    assert body["aws_enabled"] is False
    assert body["inference_provider"] == "mock"


def test_openapi_lists_phase1_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for p in (
        "/api/v1/health",
        "/api/v1/uploads",
        "/api/v1/uploads/validate",
        "/api/v1/uploads/{upload_id}",
        "/api/v1/schema/graph",
        "/api/v1/graphs/validate",
    ):
        assert p in paths, p


def test_upload_roundtrip(client: TestClient, png_bytes: bytes) -> None:
    r = client.post("/api/v1/uploads", files={"file": ("board.png", png_bytes, "image/png")})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["kind"] == "png"
    assert created["training_consent"] is False

    fetched = client.get(f"/api/v1/uploads/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["sha256"] == created["sha256"]


def test_cors_allows_frontend_origin(client: TestClient) -> None:
    r = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"

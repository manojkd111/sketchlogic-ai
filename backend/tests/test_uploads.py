from __future__ import annotations

import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.conftest import make_image, make_xlsx

VALIDATE = "/api/v1/uploads/validate"


def _post(client: TestClient, name: str, data: bytes, ctype: str = "application/octet-stream"):
    return client.post(VALIDATE, files={"file": (name, data, ctype)})


@pytest.mark.parametrize(("fmt", "kind"), [("PNG", "png"), ("JPEG", "jpeg"), ("WEBP", "webp")])
def test_valid_images(client: TestClient, fmt: str, kind: str) -> None:
    r = _post(client, f"x.{kind}", make_image(fmt, (640, 480)))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["kind"] == kind
    assert (body["width"], body["height"]) == (640, 480)


def test_valid_xlsx_reports_sheets(client: TestClient, xlsx_bytes: bytes) -> None:
    r = _post(client, "flow.xlsx", xlsx_bytes)
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "xlsx"
    assert r.json()["sheet_names"] == ["Flow", "Notes"]


def test_kind_is_sniffed_not_trusted(client: TestClient, png_bytes: bytes) -> None:
    # Wrong extension and wrong content type, but real PNG bytes.
    r = _post(client, "evil.exe", png_bytes, "application/x-msdownload")
    assert r.status_code == 200
    assert r.json()["kind"] == "png"


def test_rejects_empty(client: TestClient) -> None:
    r = _post(client, "empty.png", b"")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "empty_file"


def test_rejects_unsupported_type(client: TestClient) -> None:
    r = _post(client, "notes.png", b"GIF89a" + b"\x00" * 64, "image/png")
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "unsupported_type"


def test_rejects_truncated_image(client: TestClient, png_bytes: bytes) -> None:
    r = _post(client, "broken.png", png_bytes[: len(png_bytes) // 2])
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "corrupt_file"


def test_rejects_tiny_image(client: TestClient) -> None:
    r = _post(client, "tiny.png", make_image("PNG", (8, 8)))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "image_too_small"


def test_rejects_oversized_dimensions(client: TestClient, settings: Settings) -> None:
    settings.max_image_side = 500
    r = _post(client, "big.png", make_image("PNG", (800, 100)))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "image_too_large"


def test_rejects_oversized_file(client: TestClient, settings: Settings) -> None:
    r = _post(client, "huge.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * settings.max_upload_bytes)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"


def test_rejects_non_workbook_zip(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hello")
    r = _post(client, "archive.xlsx", buf.getvalue())
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "xlsx_invalid"


def test_rejects_macro_workbook(client: TestClient) -> None:
    r = _post(client, "macro.xlsx", make_xlsx(macros=True))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "xlsx_macros_not_allowed"


def test_rejects_zip_bomb(client: TestClient, settings: Settings) -> None:
    settings.max_xlsx_uncompressed_bytes = 1024
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", "<workbook/>")
        z.writestr("xl/bomb.xml", "0" * 50_000)
    r = _post(client, "bomb.xlsx", buf.getvalue())
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "xlsx_uncompressed_too_large"


def test_validate_does_not_store(client: TestClient, settings: Settings, png_bytes: bytes) -> None:
    _post(client, "a.png", png_bytes)
    assert not settings.uploads_dir.exists() or not any(settings.uploads_dir.iterdir())


def test_upload_stores_with_safe_name(
    client: TestClient, settings: Settings, png_bytes: bytes
) -> None:
    r = client.post(
        "/api/v1/uploads",
        files={"file": ("../../etc/<passwd>.png", png_bytes, "image/png")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "_passwd_.png"
    stored = list(settings.uploads_dir.iterdir())
    assert [p.name for p in stored] == [f"{body['id']}.png"]


def test_training_consent_is_opt_in(client: TestClient, png_bytes: bytes) -> None:
    default = client.post("/api/v1/uploads", files={"file": ("a.png", png_bytes, "image/png")})
    assert default.json()["training_consent"] is False
    opted = client.post(
        "/api/v1/uploads",
        files={"file": ("a.png", png_bytes, "image/png")},
        data={"training_consent": "true"},
    )
    assert opted.json()["training_consent"] is True


def test_get_unknown_upload_404(client: TestClient) -> None:
    assert client.get("/api/v1/uploads/" + "0" * 32).status_code == 404
    assert client.get("/api/v1/uploads/not-a-hex-id").status_code == 404

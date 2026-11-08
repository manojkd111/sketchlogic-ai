from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(environment="test", data_dir=tmp_path / "var", max_upload_bytes=2 * 1024 * 1024)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def make_image(fmt: str = "PNG", size: tuple[int, int] = (320, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (240, 240, 240)).save(buf, format=fmt)
    return buf.getvalue()


def make_xlsx(*, macros: bool = False) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Flow"
    ws.append(["From", "To", "Label"])
    ws.append(["Client", "API", "HTTPS"])
    wb.create_sheet("Notes")
    buf = io.BytesIO()
    wb.save(buf)
    if not macros:
        return buf.getvalue()
    out = io.BytesIO()
    with zipfile.ZipFile(buf) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item))
        dst.writestr("xl/vbaProject.bin", b"\x00" * 16)
    return out.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    return make_image("PNG")


@pytest.fixture
def xlsx_bytes() -> bytes:
    return make_xlsx()

"""Collect predictions by calling the SketchLogic API, exactly as the UI does.

For each manifest sample: `POST /api/v1/uploads` (training consent OFF) then
`POST /api/v1/uploads/{id}/extract`, and save the returned document as `<sample id>.json`.
Whatever provider the backend is configured with (mock, local, ...) is what gets measured.

Point this at a backend with its own data dir (e.g. `SKETCHLOGIC_DATA_DIR=var/eval`) so
evaluation uploads don't mix with real ones.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

TIMEOUT_S = 120


def _check_url(api: str) -> str:
    parsed = urlparse(api)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"--api must be an http(s) URL, got {api!r}")
    return api.rstrip("/")


def _post(url: str, body: bytes, content_type: str) -> dict[str, Any]:
    req = Request(url, data=body, method="POST", headers={"Content-Type": content_type})  # noqa: S310 - scheme checked in _check_url
    with urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
        data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return data


def _multipart(filename: str, content: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = [
        (  # never opt evaluation uploads into training
            f"--{boundary}\r\nContent-Disposition: form-data; "
            'name="training_consent"\r\n\r\nfalse\r\n'
        ).encode(),
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n'
        ).encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def read_manifest(path: Path, split: str | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [r for r in rows if split is None or r.get("split") == split]


def predict_via_api(
    manifest: Path,
    out_dir: Path,
    api: str,
    *,
    split: str | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    base = _check_url(api)
    rows = read_manifest(manifest, split)[: limit if limit is not None else None]
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {"ok": 0, "failed": 0}
    for row in rows:
        image = manifest.parent / row["image"]
        body, ctype = _multipart(image.name, image.read_bytes(), "image/png")
        try:
            upload = _post(f"{base}/api/v1/uploads", body, ctype)
            record = _post(f"{base}/api/v1/uploads/{upload['id']}/extract", b"", "application/json")
        except (HTTPError, URLError, TimeoutError, KeyError, ValueError) as exc:
            counts["failed"] += 1
            print(f"  {row['id']}: failed ({exc})")
            continue
        (out_dir / f"{row['id']}.json").write_text(
            json.dumps(record["document"], indent=2) + "\n", encoding="utf-8"
        )
        counts["ok"] += 1
    return counts

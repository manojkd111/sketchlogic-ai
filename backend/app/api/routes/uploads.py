from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import DbDep, SettingsDep
from app.core.config import Settings
from app.db.repository import UploadRow, utcnow
from app.services.upload_validation import (
    ErrorCode,
    FileKind,
    UploadValidationError,
    ValidatedFile,
    validate_upload,
)

router = APIRouter(prefix="/uploads", tags=["uploads"])

_CHUNK = 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._ \-]+")


class ValidationResult(BaseModel):
    valid: bool = True
    filename: str
    kind: FileKind
    media_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    sheet_names: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class UploadResponse(ValidationResult):
    id: str
    sha256: str
    training_consent: bool


async def _read_limited(file: UploadFile, settings: Settings) -> bytes:
    """Read at most max_upload_bytes + 1 so oversized uploads fail fast."""
    limit = settings.max_upload_bytes
    buf = bytearray()
    while chunk := await file.read(_CHUNK):
        buf.extend(chunk)
        if len(buf) > limit:
            raise UploadValidationError(
                ErrorCode.FILE_TOO_LARGE,
                f"File exceeds the {limit}-byte upload limit.",
                status_code=413,
            )
    return bytes(buf)


def _sanitize_filename(name: str | None) -> str:
    # Drop any client-supplied directories (POSIX or Windows separators).
    base = Path((name or "upload").replace("\\", "/")).name
    cleaned = _SAFE_NAME.sub("_", base).strip(" .")[:120]
    return cleaned or "upload"


def _result(name: str, v: ValidatedFile) -> ValidationResult:
    return ValidationResult(
        filename=name,
        kind=v.kind,
        media_type=v.media_type,
        size_bytes=v.size_bytes,
        width=v.width,
        height=v.height,
        sheet_names=v.sheet_names,
        warnings=v.warnings,
    )


@router.post("/validate", response_model=ValidationResult)
async def validate_only(settings: SettingsDep, file: UploadFile = File(...)) -> ValidationResult:
    """Validate a file without storing it."""
    data = await _read_limited(file, settings)
    return _result(_sanitize_filename(file.filename), validate_upload(data, settings))


@router.post("", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def create_upload(
    settings: SettingsDep,
    db: DbDep,
    file: UploadFile = File(...),
    training_consent: bool = Form(
        False, description="Opt-in to allow this file to be used for model training."
    ),
) -> UploadResponse:
    data = await _read_limited(file, settings)
    name = _sanitize_filename(file.filename)
    validated = validate_upload(data, settings)

    upload_id = uuid.uuid4().hex
    ext = "jpg" if validated.kind is FileKind.JPEG else validated.kind.value
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    target = settings.uploads_dir / f"{upload_id}.{ext}"
    target.write_bytes(data)

    sha = hashlib.sha256(data).hexdigest()
    db.insert_upload(
        UploadRow(
            id=upload_id,
            original_name=name,
            kind=validated.kind.value,
            media_type=validated.media_type,
            size_bytes=validated.size_bytes,
            sha256=sha,
            width=validated.width,
            height=validated.height,
            storage_path=target.name,
            training_consent=training_consent,
            created_at=utcnow(),
        )
    )
    return UploadResponse(
        **_result(name, validated).model_dump(),
        id=upload_id,
        sha256=sha,
        training_consent=training_consent,
    )


@router.get("/{upload_id}", response_model=UploadResponse)
def get_upload(upload_id: str, db: DbDep) -> UploadResponse:
    if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
        raise HTTPException(status_code=404, detail="Upload not found")
    row = db.get_upload(upload_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return UploadResponse(
        id=row.id,
        filename=row.original_name,
        kind=FileKind(row.kind),
        media_type=row.media_type,
        size_bytes=row.size_bytes,
        width=row.width,
        height=row.height,
        sha256=row.sha256,
        training_consent=row.training_consent,
    )

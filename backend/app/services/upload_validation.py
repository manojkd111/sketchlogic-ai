"""Validation for user uploads (images and XLSX workbooks).

We never trust the client-supplied filename or Content-Type. The file kind is
determined from magic bytes, then fully decoded/inspected:

  * Images: decoded with Pillow (`verify()` + `load()`), dimension and pixel
    limits enforced to block decompression bombs.
  * XLSX: must be a ZIP containing the OOXML workbook parts; total
    uncompressed size is bounded to block zip bombs; macro-enabled workbooks
    (vbaProject.bin) are rejected.
"""

from __future__ import annotations

import io
import re
import warnings
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum

from PIL import Image, UnidentifiedImageError

from app.core.config import Settings


class FileKind(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"
    XLSX = "xlsx"


IMAGE_KINDS = frozenset({FileKind.PNG, FileKind.JPEG, FileKind.WEBP})

MEDIA_TYPES: dict[FileKind, str] = {
    FileKind.PNG: "image/png",
    FileKind.JPEG: "image/jpeg",
    FileKind.WEBP: "image/webp",
    FileKind.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

_PIL_FORMATS: dict[FileKind, str] = {
    FileKind.PNG: "PNG",
    FileKind.JPEG: "JPEG",
    FileKind.WEBP: "WEBP",
}


class ErrorCode(StrEnum):
    EMPTY_FILE = "empty_file"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_TYPE = "unsupported_type"
    CORRUPT_FILE = "corrupt_file"
    IMAGE_TOO_SMALL = "image_too_small"
    IMAGE_TOO_LARGE = "image_too_large"
    XLSX_INVALID = "xlsx_invalid"
    XLSX_MACROS = "xlsx_macros_not_allowed"
    XLSX_TOO_LARGE = "xlsx_uncompressed_too_large"


class UploadValidationError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class ValidatedFile:
    kind: FileKind
    media_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    sheet_names: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def sniff_kind(data: bytes) -> FileKind | None:
    """Identify the file kind from its leading bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return FileKind.PNG
    if data.startswith(b"\xff\xd8\xff"):
        return FileKind.JPEG
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return FileKind.WEBP
    if data.startswith(b"PK\x03\x04"):
        return FileKind.XLSX  # confirmed by _validate_xlsx
    return None


def validate_upload(data: bytes, settings: Settings) -> ValidatedFile:
    size = len(data)
    if size == 0:
        raise UploadValidationError(ErrorCode.EMPTY_FILE, "The uploaded file is empty.")
    if size > settings.max_upload_bytes:
        raise UploadValidationError(
            ErrorCode.FILE_TOO_LARGE,
            f"File is {size} bytes; the limit is {settings.max_upload_bytes} bytes.",
            status_code=413,
        )

    kind = sniff_kind(data)
    if kind is None:
        raise UploadValidationError(
            ErrorCode.UNSUPPORTED_TYPE,
            "Unsupported file type. Upload a PNG, JPEG, WebP image or an .xlsx workbook.",
            status_code=415,
        )
    if kind is FileKind.XLSX:
        return _validate_xlsx(data, settings)
    return _validate_image(data, kind, settings)


def _validate_image(data: bytes, kind: FileKind, settings: Settings) -> ValidatedFile:
    notes: list[str] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as probe:
                width, height = probe.size
                fmt = probe.format
                # Reject before decoding pixel data if dimensions are absurd.
                _check_dimensions(width, height, settings)
                probe.verify()
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                if getattr(img, "n_frames", 1) > 1:
                    notes.append("Animated image: only the first frame will be used.")
    except UploadValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UploadValidationError(
            ErrorCode.IMAGE_TOO_LARGE, f"Image has too many pixels: {exc}", status_code=413
        ) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise UploadValidationError(
            ErrorCode.CORRUPT_FILE, "The image could not be decoded; it may be corrupt."
        ) from exc

    if fmt != _PIL_FORMATS[kind]:
        raise UploadValidationError(
            ErrorCode.CORRUPT_FILE, f"File signature says {kind.value} but decodes as {fmt}."
        )
    return ValidatedFile(
        kind=kind,
        media_type=MEDIA_TYPES[kind],
        size_bytes=len(data),
        width=width,
        height=height,
        warnings=notes,
    )


def _check_dimensions(width: int, height: int, settings: Settings) -> None:
    if min(width, height) < settings.min_image_side:
        raise UploadValidationError(
            ErrorCode.IMAGE_TOO_SMALL,
            f"Image is {width}x{height}px; each side must be at least {settings.min_image_side}px.",
        )
    if max(width, height) > settings.max_image_side or width * height > settings.max_image_pixels:
        raise UploadValidationError(
            ErrorCode.IMAGE_TOO_LARGE,
            f"Image is {width}x{height}px; max side is {settings.max_image_side}px and max "
            f"area is {settings.max_image_pixels} pixels.",
            status_code=413,
        )


def _validate_xlsx(data: bytes, settings: Settings) -> ValidatedFile:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UploadValidationError(ErrorCode.CORRUPT_FILE, "The archive is corrupt.") from exc

    with zf:
        infos = zf.infolist()
        names = {i.filename for i in infos}
        if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
            raise UploadValidationError(
                ErrorCode.XLSX_INVALID,
                "ZIP file is not an Excel workbook (.xlsx). Legacy .xls is not supported.",
                status_code=415,
            )
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise UploadValidationError(
                ErrorCode.XLSX_MACROS, "Macro-enabled workbooks are not accepted."
            )
        total = sum(i.file_size for i in infos)
        if total > settings.max_xlsx_uncompressed_bytes:
            raise UploadValidationError(
                ErrorCode.XLSX_TOO_LARGE,
                f"Workbook expands to {total} bytes; limit is "
                f"{settings.max_xlsx_uncompressed_bytes}.",
                status_code=413,
            )
        bad = zf.testzip()
        if bad is not None:
            raise UploadValidationError(
                ErrorCode.CORRUPT_FILE, f"Workbook member '{bad}' is corrupt."
            )
        sheet_names = _read_sheet_names(zf.read("xl/workbook.xml"))

    return ValidatedFile(
        kind=FileKind.XLSX,
        media_type=MEDIA_TYPES[FileKind.XLSX],
        size_bytes=len(data),
        sheet_names=sheet_names,
    )


def _read_sheet_names(workbook_xml: bytes) -> list[str]:
    """Extract sheet names without a full XML parser (avoids XXE / entity expansion)."""
    if b"<!DOCTYPE" in workbook_xml or b"<!ENTITY" in workbook_xml:
        raise UploadValidationError(
            ErrorCode.XLSX_INVALID, "Workbook XML contains a DOCTYPE, which is not allowed."
        )
    text = workbook_xml.decode("utf-8", errors="replace")
    return re.findall(r"<(?:\w+:)?sheet\b[^>]*?\bname=\"([^\"]*)\"", text)

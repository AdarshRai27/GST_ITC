"""Safe handling of Streamlit uploaded files for the ITC Sentinel pipeline.

Streamlit's ``st.file_uploader`` returns an ``UploadedFile`` object, not a
filesystem path. The ingestion functions in :mod:`itc_sentinel.ingest` accept
filesystem paths, so uploaded bytes must be materialised safely before they
reach the parser.

This module keeps that boundary explicit and testable without importing
Streamlit:

* File sizes are bounded (``MAX_UPLOAD_BYTES``).
* Only documented extensions are accepted.
* Original filenames are sanitised so path-traversal attempts cannot escape
  the run directory.
* Empty uploads are rejected with an actionable error.
* Temporary copies can be removed deterministically after ingestion.

No uploaded content is logged. The caller is responsible for deleting the
returned temporary path once ingestion has completed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "GSTR2B_EXTENSIONS",
    "MAX_UPLOAD_BYTES",
    "PURCHASE_EXTENSIONS",
    "UploadValidationError",
    "cleanup_paths",
    "safe_filename",
    "save_uploaded_file",
]

# Bounded upload size for the demo: 10 MiB per file. Real purchase registers
# can be larger, but the MVP deliberately caps memory/disk use.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

PURCHASE_EXTENSIONS = (".csv", ".xlsx")
GSTR2B_EXTENSIONS = (".json",)

_MAX_FILENAME_LENGTH = 120


class UploadValidationError(ValueError):
    """Raised when an uploaded file is missing, empty, oversized, or unsafe."""


def safe_filename(name: Any, default: str = "uploaded_file") -> str:
    """Return a safe basename for *name*.

    Handles both POSIX and Windows separators, strips NUL bytes and control
    characters, rejects ``.``/``..``, and bounds the length while preserving a
    sensible extension.
    """
    if name is None:
        return default

    text = str(name).replace("\x00", "")
    # Treat both separator styles as separators regardless of host OS.
    text = text.replace("\\", "/").rsplit("/", 1)[-1]
    text = "".join(ch for ch in text if ch.isprintable()).strip()

    if text in {"", ".", ".."}:
        return default

    if len(text) > _MAX_FILENAME_LENGTH:
        suffix = Path(text).suffix
        stem_limit = max(1, _MAX_FILENAME_LENGTH - len(suffix))
        text = text[:stem_limit] + suffix

    return text


def _read_upload_bytes(uploaded: Any) -> bytes:
    """Read bytes from a Streamlit ``UploadedFile`` or a binary file object."""
    getbuffer = getattr(uploaded, "getbuffer", None)
    if callable(getbuffer):
        return bytes(getbuffer())

    read = getattr(uploaded, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, str):
            return data.encode("utf-8")
        return bytes(data)

    raise UploadValidationError(
        "Unsupported upload object: expected a Streamlit UploadedFile or a "
        "binary file-like object."
    )


def save_uploaded_file(
    uploaded: Any,
    target_dir: str | Path,
    allowed_extensions: Iterable[str],
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
    kind: str = "upload",
) -> str:
    """Persist an uploaded file safely and return its filesystem path.

    Args:
        uploaded: A Streamlit ``UploadedFile`` or binary file-like object.
        target_dir: Directory in which the temporary copy is written. It is
            created when missing.
        allowed_extensions: Extensions accepted for this upload, e.g.
            ``(".csv", ".xlsx")``. Case-insensitive.
        max_bytes: Maximum accepted size in bytes.
        kind: Short prefix used to avoid collisions between purchase-register
            and GSTR-2B uploads in the same directory.

    Returns:
        The absolute path of the written temporary file.

    Raises:
        UploadValidationError: If the upload is missing, empty, oversized, of
            an unsupported type, or cannot be written safely.
    """
    if uploaded is None:
        raise UploadValidationError("No file was uploaded.")

    filename = safe_filename(getattr(uploaded, "name", None))
    suffix = Path(filename).suffix.lower()
    allowed = tuple(ext.lower() for ext in allowed_extensions)
    if suffix not in allowed:
        raise UploadValidationError(
            f"Unsupported file type '{suffix or '(none)'}' for '{filename}'; "
            f"expected one of {', '.join(allowed)}."
        )

    data = _read_upload_bytes(uploaded)
    if not data:
        raise UploadValidationError(f"Uploaded file '{filename}' is empty.")
    if len(data) > max_bytes:
        raise UploadValidationError(
            f"Uploaded file '{filename}' is {len(data)} bytes; the limit is "
            f"{max_bytes} bytes."
        )

    directory = Path(target_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)

    prefix = safe_filename(kind, default="upload")
    target = (directory / f"{prefix}_{filename}").resolve()
    if target.parent != directory:
        raise UploadValidationError(
            f"Unsafe upload path for '{filename}'; refusing to write."
        )

    try:
        target.write_bytes(data)
    except OSError as exc:
        cleanup_paths([target])
        raise UploadValidationError(
            f"Could not store uploaded file '{filename}': {exc}"
        ) from exc

    return str(target)


def cleanup_paths(paths: Iterable[str | Path | None]) -> None:
    """Best-effort deletion of temporary upload files.

    Missing files are ignored. Errors are swallowed because cleanup must not
    mask the original ingestion result; callers that need strict cleanup can
    check the filesystem directly.
    """
    for path in paths:
        if path is None:
            continue
        try:
            os.unlink(path)
        except FileNotFoundError:
            continue
        except OSError:
            continue

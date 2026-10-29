"""Tests for safe uploaded-file handling (src/itc_sentinel/uploads.py).

These tests reproduce the original defect: a Streamlit ``UploadedFile`` is not
a filesystem path. Bytes must be materialised safely, bounded in size, and
cleaned up after ingestion. No real taxpayer data is used.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from itc_sentinel.ingest import (
    IngestionError,
    load_gstr2b_json,
    load_purchase_register,
)
from itc_sentinel.uploads import (
    GSTR2B_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    PURCHASE_EXTENSIONS,
    UploadValidationError,
    cleanup_paths,
    safe_filename,
    save_uploaded_file,
)

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"


class FakeUpload:
    """Minimal stand-in for ``streamlit.runtime.uploaded_file_manager.UploadedFile``."""

    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getbuffer(self) -> memoryview:
        return memoryview(self._data)


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------


def test_safe_filename_strips_directory_components():
    assert safe_filename("../../evil.csv") == "evil.csv"
    assert safe_filename("..\\..\\evil.csv") == "evil.csv"
    assert safe_filename("C:\\temp\\invoice.xlsx") == "invoice.xlsx"


def test_safe_filename_removes_nul_and_handles_empty():
    assert safe_filename("bad\x00name.csv") == "badname.csv"
    assert safe_filename("") == "uploaded_file"
    assert safe_filename("..") == "uploaded_file"


def test_safe_filename_bounds_length():
    name = "a" * 300 + ".csv"
    result = safe_filename(name)
    assert len(result) <= 120
    assert result.endswith(".csv")


# ---------------------------------------------------------------------------
# Saving and cleanup
# ---------------------------------------------------------------------------


def test_save_valid_csv_and_cleanup(tmp_path):
    upload = FakeUpload("purchase.csv", b"gstin,invoice_number\n")
    path = save_uploaded_file(
        upload, tmp_path, PURCHASE_EXTENSIONS, kind="purchase"
    )

    assert Path(path).is_file()
    assert Path(path).read_bytes() == upload.getbuffer().tobytes()
    assert "purchase_purchase.csv" in Path(path).name

    cleanup_paths([path])
    assert not Path(path).exists()


def test_path_traversal_filename_stays_inside_target(tmp_path):
    target = tmp_path / "runs" / "abc" / "uploads"
    upload = FakeUpload("..\\..\\..\\escape.csv", b"gstin\n")
    path = save_uploaded_file(upload, target, PURCHASE_EXTENSIONS)

    resolved_target = target.resolve()
    assert Path(path).resolve().parent == resolved_target
    assert not (tmp_path / "escape.csv").exists()

    cleanup_paths([path])


def test_repeated_upload_same_name_overwrites_safely(tmp_path):
    first = save_uploaded_file(
        FakeUpload("purchase.csv", b"first\n"), tmp_path, PURCHASE_EXTENSIONS
    )
    second = save_uploaded_file(
        FakeUpload("purchase.csv", b"second\n"), tmp_path, PURCHASE_EXTENSIONS
    )

    assert first == second
    assert Path(second).read_bytes() == b"second\n"
    cleanup_paths([first])


def test_purchase_and_gstr2b_uploads_do_not_collide(tmp_path):
    purchase = save_uploaded_file(
        FakeUpload("data.csv", b"purchase\n"),
        tmp_path,
        PURCHASE_EXTENSIONS,
        kind="purchase",
    )
    gstr2b = save_uploaded_file(
        FakeUpload("data.json", b"gstr2b\n"),
        tmp_path,
        GSTR2B_EXTENSIONS,
        kind="gstr2b",
    )

    assert purchase != gstr2b
    assert Path(purchase).read_bytes() == b"purchase\n"
    assert Path(gstr2b).read_bytes() == b"gstr2b\n"
    cleanup_paths([purchase, gstr2b])


# ---------------------------------------------------------------------------
# Invalid uploads
# ---------------------------------------------------------------------------


def test_none_upload_rejected(tmp_path):
    with pytest.raises(UploadValidationError, match="No file"):
        save_uploaded_file(None, tmp_path, PURCHASE_EXTENSIONS)


def test_empty_upload_rejected(tmp_path):
    with pytest.raises(UploadValidationError, match="empty"):
        save_uploaded_file(
            FakeUpload("empty.csv", b""), tmp_path, PURCHASE_EXTENSIONS
        )


def test_unsupported_extension_rejected(tmp_path):
    with pytest.raises(UploadValidationError, match="Unsupported file type"):
        save_uploaded_file(
            FakeUpload("data.txt", b"data"), tmp_path, PURCHASE_EXTENSIONS
        )


def test_oversized_upload_rejected(tmp_path):
    with pytest.raises(UploadValidationError, match="limit"):
        save_uploaded_file(
            FakeUpload("big.csv", b"x" * 20),
            tmp_path,
            PURCHASE_EXTENSIONS,
            max_bytes=10,
        )
    assert MAX_UPLOAD_BYTES >= 1


def test_unsupported_object_rejected(tmp_path):
    class NotAFile:
        name = "data.csv"

    with pytest.raises(UploadValidationError, match="Unsupported upload object"):
        save_uploaded_file(NotAFile(), tmp_path, PURCHASE_EXTENSIONS)


# ---------------------------------------------------------------------------
# Uploaded bytes reach the real parsers
# ---------------------------------------------------------------------------


def test_uploaded_csv_reaches_purchase_register_parser(tmp_path):
    content = (SAMPLE_DIR / "purchase_register_synthetic.csv").read_bytes()
    path = save_uploaded_file(
        FakeUpload("purchase_register_synthetic.csv", content),
        tmp_path,
        PURCHASE_EXTENSIONS,
        kind="purchase",
    )
    try:
        result = load_purchase_register(path)
        assert result.row_count == 9
        assert result.source_type.value == "purchase_register"
    finally:
        cleanup_paths([path])


def test_uploaded_xlsx_reaches_purchase_register_parser(tmp_path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "gstin",
            "invoice_number",
            "invoice_date",
            "taxable_value",
            "cgst",
            "sgst",
            "igst",
            "cess",
            "vendor_name",
        ]
    )
    sheet.append(
        [
            "29ABCDE1234F1Z5",
            "INV-001",
            "2024-04-15",
            "1000.00",
            "90.00",
            "90.00",
            "0.00",
            "0.00",
            "Synthetic Vendor",
        ]
    )
    target = tmp_path / "purchase.xlsx"
    workbook.save(target)

    path = save_uploaded_file(
        FakeUpload("purchase.xlsx", target.read_bytes()),
        tmp_path / "uploads",
        PURCHASE_EXTENSIONS,
        kind="purchase",
    )
    try:
        result = load_purchase_register(path)
        assert result.row_count == 1
        assert result.raw_records[0]["gstin"] == "29ABCDE1234F1Z5"
    finally:
        cleanup_paths([path])


def test_uploaded_json_reaches_gstr2b_parser(tmp_path):
    content = (SAMPLE_DIR / "gstr2b_synthetic.json").read_bytes()
    path = save_uploaded_file(
        FakeUpload("gstr2b_synthetic.json", content),
        tmp_path,
        GSTR2B_EXTENSIONS,
        kind="gstr2b",
    )
    try:
        result = load_gstr2b_json(path)
        assert result.row_count == 7
        assert result.source_type.value == "gstr_2b"
    finally:
        cleanup_paths([path])


def test_malformed_csv_reaches_parser_and_fails_safely(tmp_path):
    path = save_uploaded_file(
        FakeUpload("bad.csv", b"gstin,invoice_number\n29ABCDE1234F1Z5,INV-1\n"),
        tmp_path,
        PURCHASE_EXTENSIONS,
    )
    try:
        with pytest.raises(IngestionError, match="column validation"):
            load_purchase_register(path)
    finally:
        cleanup_paths([path])


def test_invalid_xlsx_reaches_parser_and_fails_safely(tmp_path):
    path = save_uploaded_file(
        FakeUpload("corrupt.xlsx", b"this is not an xlsx file"),
        tmp_path,
        PURCHASE_EXTENSIONS,
    )
    try:
        with pytest.raises(IngestionError, match="Invalid or unreadable XLSX"):
            load_purchase_register(path)
    finally:
        cleanup_paths([path])


def test_malformed_json_reaches_parser_and_fails_safely(tmp_path):
    path = save_uploaded_file(
        FakeUpload("bad.json", b"{not json"),
        tmp_path,
        GSTR2B_EXTENSIONS,
    )
    try:
        with pytest.raises(IngestionError, match="Malformed JSON"):
            load_gstr2b_json(path)
    finally:
        cleanup_paths([path])


def test_empty_json_object_fails_with_actionable_error(tmp_path):
    path = save_uploaded_file(
        FakeUpload("empty.json", b"{}"),
        tmp_path,
        GSTR2B_EXTENSIONS,
    )
    try:
        with pytest.raises(IngestionError, match="missing required top-level"):
            load_gstr2b_json(path)
    finally:
        cleanup_paths([path])


def test_cleanup_is_idempotent(tmp_path):
    cleanup_paths([tmp_path / "does-not-exist", None])

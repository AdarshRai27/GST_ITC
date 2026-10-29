"""Input ingestion for the ITC Sentinel pipeline.

Loads purchase-register (CSV/XLSX) and GSTR-2B (JSON) files, validates their
structure, and returns raw records together with human-readable validation
issues. Invalid rows are preserved; nothing is silently dropped.

Public functions:
    load_purchase_register(path) -> IngestResult
    load_gstr2b_json(path) -> IngestResult
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .schemas import (
    GSTR2B_INVOICE_FIELDS,
    GSTR2B_INVOICE_REQUIRED,
    GSTR2B_TOP_LEVEL_FIELDS,
    PURCHASE_REGISTER_REQUIRED,
    IngestResult,
    SourceType,
    ValidationIssue,
)

__all__ = [
    "IngestionError",
    "load_purchase_register",
    "load_gstr2b_json",
]


class IngestionError(Exception):
    """Raised for file-level ingestion failures (missing file, bad type,
    malformed contents, missing required columns)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_hash(path: str) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: str) -> None:
    """Validate that *path* points to a readable file that exists."""
    if not os.path.isfile(path):
        raise IngestionError(f"Input file not found: {path}")


def _require_extension(path: str, allowed: tuple[str, ...]) -> None:
    """Validate that *path* has one of the allowed extensions."""
    suffix = Path(path).suffix.lower()
    if suffix not in allowed:
        raise IngestionError(
            f"Unsupported file type '{suffix}' for {path}; "
            f"expected one of {allowed}."
        )


def _validate_columns(
    columns: list[str],
    required: list[str],
    source_file: str,
    row_index: int = -1,
) -> list[ValidationIssue]:
    """Return issues for required columns missing from *columns*."""
    issues: list[ValidationIssue] = []
    present = set(columns)
    for name in required:
        if name not in present:
            issues.append(
                ValidationIssue(
                    field=name,
                    row_index=row_index,
                    message=(
                        f"Missing required column '{name}' in {source_file}"
                    ),
                    severity="error",
                )
            )
    return issues


def _clean_cell(value: Any) -> str | None:
    """Normalize a raw cell to a stripped string or None when empty."""
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN
        return None
    text = str(value).strip()
    return text if text != "" else None


# ---------------------------------------------------------------------------
# Purchase register (CSV / XLSX)
# ---------------------------------------------------------------------------


def _read_csv(path: str) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV file into header + list of dicts (raw strings preserved)."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise IngestionError(f"CSV file has no header row: {path}")
        header = [name.strip() if name else name for name in reader.fieldnames]
        records: list[dict[str, str]] = []
        for row in reader:
            cleaned: dict[str, str] = {}
            for key, value in row.items():
                clean_key = key.strip() if key else key
                cleaned[clean_key] = value
            records.append(cleaned)
    return header, records


def _read_xlsx(path: str) -> tuple[list[str], list[dict[str, str]]]:
    """Read the first sheet of an XLSX file into header + list of dicts."""
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, KeyError, ValueError) as exc:
        raise IngestionError(
            f"Invalid or unreadable XLSX file {path}: {exc}"
        ) from exc
    try:
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        try:
            first_row = next(rows)
        except StopIteration:
            raise IngestionError(f"XLSX file has no data: {path}") from None
        header = [
            str(cell).strip() if cell is not None else "" for cell in first_row
        ]
        records: list[dict[str, str]] = []
        for row in rows:
            record: dict[str, str] = {}
            for index, cell in enumerate(row):
                key = header[index] if index < len(header) else f"col_{index}"
                record[key] = _clean_cell(cell)
            records.append(record)
        return header, records
    finally:
        workbook.close()


def load_purchase_register(path: str) -> IngestResult:
    """Load a purchase-register CSV or XLSX file.

    Validates that the file exists, is of a supported type, has a header row,
    and contains all required columns. Raw cell values are preserved as
    strings; normalization happens in :mod:`itc_sentinel.normalize`.

    Raises:
        IngestionError: If the file is missing, of an unsupported type,
            unreadable, or missing required columns.
    """
    _require_file(path)
    _require_extension(path, (".csv", ".xlsx"))

    source_file = str(Path(path).resolve())
    file_hash = _file_hash(path)

    if path.lower().endswith(".csv"):
        header, raw_records = _read_csv(path)
    else:
        header, raw_records = _read_xlsx(path)

    # Whole-file column validation. Missing required columns is a file-level
    # error because no row can be meaningfully interpreted without them.
    column_issues = _validate_columns(
        header, PURCHASE_REGISTER_REQUIRED, source_file
    )
    if column_issues:
        raise IngestionError(
            "Purchase register failed column validation: "
            + "; ".join(issue.message for issue in column_issues)
        )

    return IngestResult(
        source_type=SourceType.PURCHASE_REGISTER,
        source_file=source_file,
        raw_records=raw_records,
        issues=column_issues,
        row_count=len(raw_records),
        file_hash=file_hash,
    )


# ---------------------------------------------------------------------------
# GSTR-2B JSON
# ---------------------------------------------------------------------------


def load_gstr2b_json(path: str) -> IngestResult:
    """Load a GSTR-2B JSON file using the declared supported contract.

    Declared contract (an assumption pending confirmation against a real
    GSTR-2B export):

        {
          "gstin": "<recipient GSTIN>",
          "period": "<MMYYYY>",
          "invoices": [
            {
              "supplier_gstin": "<supplier GSTIN>",
              "invoice_number": "<invoice no.>",
              "invoice_date": "<date>",
              "taxable_value": <number>,
              "cgst": <number>,
              "sgst": <number>,
              "igst": <number>,
              "cess": <number>,
              "invoice_type": "<B2B | ...>"
            },
            ...
          ]
        }

    Only the fields in ``GSTR2B_INVOICE_FIELDS`` are read; all other top-level
    or invoice fields are ignored. Invalid invoices are preserved as raw
    records and flagged during normalization, not discarded here.

    Raises:
        IngestionError: If the file is missing, not JSON, missing top-level
            required fields, or ``invoices`` is not a list.
    """
    _require_file(path)
    _require_extension(path, (".json",))

    source_file = str(Path(path).resolve())
    file_hash = _file_hash(path)

    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise IngestionError(
            f"Malformed JSON in {source_file}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise IngestionError(
            f"GSTR-2B JSON root must be an object in {source_file}; "
            f"got {type(data).__name__}."
        )

    missing_top = [
        name for name in GSTR2B_TOP_LEVEL_FIELDS if name not in data
    ]
    if missing_top:
        raise IngestionError(
            "GSTR-2B JSON missing required top-level field(s): "
            + ", ".join(missing_top)
            + f" in {source_file}."
        )

    invoices = data.get("invoices")
    if not isinstance(invoices, list):
        raise IngestionError(
            f"GSTR-2B 'invoices' must be a list in {source_file}; "
            f"got {type(invoices).__name__}."
        )

    raw_records: list[dict[str, Any]] = []
    issues: list[ValidationIssue] = []

    for index, invoice in enumerate(invoices):
        if not isinstance(invoice, dict):
            raw_records.append({"_row_index": index, "_raw": invoice})
            issues.append(
                ValidationIssue(
                    field="invoices",
                    row_index=index,
                    message=(
                        f"Invoice at index {index} is not an object; "
                        "preserved as-is and will be flagged invalid."
                    ),
                    severity="error",
                )
            )
            continue
        record: dict[str, Any] = {}
        for field_name in GSTR2B_INVOICE_FIELDS:
            if field_name in invoice:
                record[field_name] = invoice[field_name]
        raw_records.append(record)

    column_issues = _validate_columns(
        GSTR2B_INVOICE_FIELDS,
        GSTR2B_INVOICE_REQUIRED,
        source_file,
    )
    issues.extend(column_issues)

    return IngestResult(
        source_type=SourceType.GSTR_2B,
        source_file=source_file,
        raw_records=raw_records,
        issues=issues,
        row_count=len(raw_records),
        file_hash=file_hash,
    )

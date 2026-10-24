"""Shared types, enums, and stable field names for the ITC Sentinel pipeline.

This module defines the canonical schema contract used by ingestion and
normalization. Field names here are stable identifiers; raw source columns are
mapped to them during ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    """Origin of an input record."""

    PURCHASE_REGISTER = "purchase_register"
    GSTR_2B = "gstr_2b"


class ValidationStatus(str, Enum):
    """Row-level validation outcome.

    INVALID rows are preserved with their issues; they are never silently
    dropped or coerced into valid transactions.
    """

    VALID = "valid"
    INVALID = "invalid"


# ---------------------------------------------------------------------------
# Stable raw column names (purchase register CSV/XLSX)
# ---------------------------------------------------------------------------
PURCHASE_REGISTER_COLUMNS: list[str] = [
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

PURCHASE_REGISTER_REQUIRED: list[str] = [
    "gstin",
    "invoice_number",
    "invoice_date",
    "taxable_value",
]

# ---------------------------------------------------------------------------
# Stable raw field names (declared GSTR-2B JSON contract)
# ---------------------------------------------------------------------------
GSTR2B_TOP_LEVEL_FIELDS: list[str] = ["gstin", "period", "invoices"]

GSTR2B_INVOICE_FIELDS: list[str] = [
    "supplier_gstin",
    "invoice_number",
    "invoice_date",
    "taxable_value",
    "cgst",
    "sgst",
    "igst",
    "cess",
    "invoice_type",
]

GSTR2B_INVOICE_REQUIRED: list[str] = [
    "supplier_gstin",
    "invoice_number",
    "invoice_date",
    "taxable_value",
]

# ---------------------------------------------------------------------------
# Normalized column names (output of normalize.py)
# ---------------------------------------------------------------------------
NORMALIZED_COLUMNS: list[str] = [
    "source_type",
    "source_row",
    "source_file",
    "gstin",
    "invoice_number",
    "invoice_date",
    "taxable_value",
    "cgst",
    "sgst",
    "igst",
    "cess",
    "total_tax",
    "total_amount",
    "vendor_name",
    "invoice_type",
    "validation_status",
    "validation_issues",
]

# ---------------------------------------------------------------------------
# Money / rounding policy
# ---------------------------------------------------------------------------
# All monetary values are represented as Decimal. Amounts are rounded to 2
# decimal places (paise precision) using ROUND_HALF_UP. This policy is
# explicit and tested; it is a configurable assumption pending CA review.
MONEY_PLACES = Decimal("0.01")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation problem detected on a row.

    Attributes:
        field: The source field name (or "row" for whole-row issues).
        row_index: Zero-based index of the row within the source file.
        message: Human-readable description of the problem.
        severity: "error" (row invalid) or "warning" (row usable but flagged).
    """

    field: str
    row_index: int
    message: str
    severity: str = "error"


@dataclass
class IngestResult:
    """Result of loading a single input file.

    Attributes:
        source_type: Origin of the records.
        source_file: Path of the file that was loaded.
        raw_records: List of dicts representing each source row, exactly as
            parsed (original values preserved).
        issues: File-level or whole-dataset validation issues.
        row_count: Number of records parsed.
        file_hash: SHA-256 of the file contents for reproducibility.
    """

    source_type: SourceType
    source_file: str
    raw_records: list[dict[str, Any]] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    row_count: int = 0
    file_hash: str = ""

    @property
    def valid_record_count(self) -> int:
        """Count of raw records (pre-normalization); validity is set later."""
        return len(self.raw_records)


@dataclass
class NormalizedRecord:
    """A single canonical, normalized reconciliation input row.

    Attributes:
        source_type: Origin of the record.
        source_row: Zero-based index in the source file.
        source_file: Path of the source file.
        gstin: Normalized GSTIN (uppercase, whitespace stripped) or None.
        invoice_number: Normalized invoice key or None.
        invoice_date: Normalized ISO date or None.
        taxable_value, cgst, sgst, igst, cess: Monetary Decimal values or None.
        total_tax: cgst + sgst + igst + cess (Decimal or None).
        total_amount: taxable_value + total_tax (Decimal or None).
        vendor_name: Normalized vendor name or None.
        invoice_type: Invoice type string or None.
        validation_status: VALID or INVALID.
        validation_issues: Row-level issues (empty when VALID).
        raw_values: Original source field values preserved for traceability.
    """

    source_type: SourceType
    source_row: int
    source_file: str
    gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    taxable_value: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    cess: Decimal | None = None
    total_tax: Decimal | None = None
    total_amount: Decimal | None = None
    vendor_name: str | None = None
    invoice_type: str | None = None
    validation_status: ValidationStatus = ValidationStatus.INVALID
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    raw_values: dict[str, Any] = field(default_factory=dict)

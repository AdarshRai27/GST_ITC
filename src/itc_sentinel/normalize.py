"""Data normalization for the ITC Sentinel pipeline.

Normalizes GSTIN, invoice numbers, dates, and monetary values into canonical
form. Invalid values are preserved with row-level issues; invalid rows are
never silently dropped or coerced into valid transactions.

All monetary values are represented as :class:`decimal.Decimal` and rounded
to two decimal places (paise precision) using ROUND_HALF_UP. This policy is
explicit and tested; it is a configurable assumption pending CA review.

Public functions:
    normalize_gstin(value) -> str | None
    normalize_invoice_number(value) -> str | None
    normalize_date(value) -> date | None
    normalize_amount(value) -> Decimal | None
    normalize_records(records, source_type, source_file) -> list[NormalizedRecord]
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from .schemas import (
    MONEY_PLACES,
    NormalizedRecord,
    SourceType,
    ValidationIssue,
    ValidationStatus,
)

__all__ = [
    "normalize_gstin",
    "normalize_invoice_number",
    "normalize_date",
    "normalize_amount",
    "normalize_records",
]

# GSTIN structural pattern: 15 alphanumeric characters.
# First two digits = state code; no claim is made about official validity.
_GSTIN_RE = re.compile(r"^[A-Za-z0-9]{15}$")

# Whitespace runs inside a value.
_WHITESPACE_RE = re.compile(r"\s+")

# Supported input date formats (tried in order). ISO first for determinism.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d-%m-%y",
    "%d/%m/%y",
    "%b %d, %Y",
    "%d %b %Y",
)

# Characters stripped from amount strings before parsing (currency symbols,
# thousands separators, spaces). The minus sign and decimal point are kept.
_AMOUNT_STRIP_CHARS = ",₹$€£"


# ---------------------------------------------------------------------------
# Field normalizers
# ---------------------------------------------------------------------------


def normalize_gstin(value: Any) -> str | None:
    """Normalize a GSTIN to uppercase, whitespace-collapsed form.

    Returns None when the value is missing or fails the basic structural
    check (15 alphanumeric characters). This is a structural sanity check
    only; it does not verify the GSTIN against the GST portal or validate
    the checksum digit.
    """
    if value is None:
        return None
    text = _WHITESPACE_RE.sub("", str(value)).strip().upper()
    if text == "":
        return None
    if not _GSTIN_RE.match(text):
        return None
    return text


def normalize_invoice_number(value: Any) -> str | None:
    """Normalize an invoice number by collapsing whitespace and uppercasing.

    Returns None when the value is missing or empty. No structural validation
    is applied beyond non-emptiness, because invoice formats vary by vendor.
    """
    if value is None:
        return None
    text = _WHITESPACE_RE.sub(" ", str(value)).strip().upper()
    return text if text != "" else None


def normalize_date(value: Any) -> date | None:
    """Parse a date value into an ISO :class:`datetime.date`.

    Tries each format in :data:`_DATE_FORMATS` in order. Returns None when
    the value is missing, empty, or unparseable. No silent coercion is
    performed: an unparseable date stays invalid and is reported as an issue.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if text == "":
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_amount(value: Any) -> Decimal | None:
    """Parse a monetary value into a :class:`decimal.Decimal`.

    Strips currency symbols and thousands separators, then parses the
    remainder. The result is quantized to two decimal places using
    ROUND_HALF_UP. Returns None when the value is missing, empty, or
    not a valid number. Invalid numeric input is never silently coerced to
    zero.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # Booleans are not meaningful monetary values.
        return None
    if isinstance(value, (int, float)):
        text = str(value)
    else:
        text = str(value).strip()
        if text == "":
            return None
        for ch in _AMOUNT_STRIP_CHARS:
            text = text.replace(ch, "")
        text = text.strip()
        if text == "" or text in ("-", "+"):
            return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Record-level normalization
# ---------------------------------------------------------------------------


def _get(record: dict[str, Any], field_name: str) -> Any:
    """Return a record field, tolerating missing keys."""
    return record.get(field_name)


def normalize_records(
    records: list[dict[str, Any]],
    source_type: SourceType,
    source_file: str,
) -> list[NormalizedRecord]:
    """Normalize a list of raw ingestion records.

    Each input record becomes exactly one :class:`NormalizedRecord`. Records
    with invalid fields are marked :class:`ValidationStatus.INVALID` and keep
    their issues; they are never dropped. Original source values are preserved
    in ``raw_values`` for traceability.

    Args:
        records: Raw records as returned by an ingestion loader.
        source_type: Origin of the records.
        source_file: Path of the source file.

    Returns:
        A list of :class:`NormalizedRecord`, one per input record, in order.
    """
    normalized: list[NormalizedRecord] = []
    for index, record in enumerate(records):
        issues: list[ValidationIssue] = []

        raw_gstin = _get(record, "gstin") or _get(record, "supplier_gstin")
        gstin = normalize_gstin(raw_gstin)
        if raw_gstin is not None and gstin is None:
            issues.append(
                ValidationIssue(
                    field="gstin",
                    row_index=index,
                    message=(
                        f"Invalid GSTIN format: {raw_gstin!r} "
                        "(expected 15 alphanumeric characters)."
                    ),
                    severity="error",
                )
            )

        invoice_number = normalize_invoice_number(
            _get(record, "invoice_number")
        )
        if _get(record, "invoice_number") is not None and invoice_number is None:
            issues.append(
                ValidationIssue(
                    field="invoice_number",
                    row_index=index,
                    message=(
                        f"Missing or empty invoice number at row {index}."
                    ),
                    severity="error",
                )
            )

        invoice_date = normalize_date(_get(record, "invoice_date"))
        if _get(record, "invoice_date") is not None and invoice_date is None:
            issues.append(
                ValidationIssue(
                    field="invoice_date",
                    row_index=index,
                    message=(
                        f"Unparseable invoice date: "
                        f"{_get(record, 'invoice_date')!r}."
                    ),
                    severity="error",
                )
            )

        taxable_value = normalize_amount(_get(record, "taxable_value"))
        if _get(record, "taxable_value") is not None and taxable_value is None:
            issues.append(
                ValidationIssue(
                    field="taxable_value",
                    row_index=index,
                    message=(
                        f"Invalid taxable value: "
                        f"{_get(record, 'taxable_value')!r}."
                    ),
                    severity="error",
                )
            )

        cgst = normalize_amount(_get(record, "cgst"))
        sgst = normalize_amount(_get(record, "sgst"))
        igst = normalize_amount(_get(record, "igst"))
        cess = normalize_amount(_get(record, "cess"))

        for field_name, parsed in (
            ("cgst", cgst),
            ("sgst", sgst),
            ("igst", igst),
            ("cess", cess),
        ):
            if _get(record, field_name) is not None and parsed is None:
                issues.append(
                    ValidationIssue(
                        field=field_name,
                        row_index=index,
                        message=f"Invalid {field_name} value: "
                        f"{_get(record, field_name)!r}.",
                        severity="error",
                    )
                )

        vendor_name = normalize_invoice_number(_get(record, "vendor_name"))
        invoice_type = normalize_invoice_number(_get(record, "invoice_type"))

        total_tax: Decimal | None = None
        total_amount: Decimal | None = None
        if (
            taxable_value is not None
            and all(
                component is not None
                for component in (cgst, sgst, igst, cess)
            )
        ):
            total_tax = (cgst + sgst + igst + cess).quantize(
                MONEY_PLACES, rounding=ROUND_HALF_UP
            )
            total_amount = (taxable_value + total_tax).quantize(
                MONEY_PLACES, rounding=ROUND_HALF_UP
            )

        # Missing required fields make a row invalid.
        required_missing = []
        if gstin is None:
            required_missing.append("gstin")
        if invoice_number is None:
            required_missing.append("invoice_number")
        if invoice_date is None:
            required_missing.append("invoice_date")
        if taxable_value is None:
            required_missing.append("taxable_value")
        for name in required_missing:
            if not any(issue.field == name for issue in issues):
                issues.append(
                    ValidationIssue(
                        field=name,
                        row_index=index,
                        message=f"Required field '{name}' is missing.",
                        severity="error",
                    )
                )

        validation_status = (
            ValidationStatus.VALID if not issues else ValidationStatus.INVALID
        )

        normalized.append(
            NormalizedRecord(
                source_type=source_type,
                source_row=index,
                source_file=source_file,
                gstin=gstin,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                taxable_value=taxable_value,
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                cess=cess,
                total_tax=total_tax,
                total_amount=total_amount,
                vendor_name=vendor_name,
                invoice_type=invoice_type,
                validation_status=validation_status,
                validation_issues=issues,
                raw_values=dict(record),
            )
        )

    return normalized

"""Tests for the normalization module (src/itc_sentinel/normalize.py).

Covers GSTIN, invoice-number, date, and amount normalization; row-level
invalid-row preservation; and monetary total calculations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from itc_sentinel.normalize import (
    normalize_amount,
    normalize_date,
    normalize_gstin,
    normalize_invoice_number,
    normalize_records,
)
from itc_sentinel.schemas import (
    MONEY_PLACES,
    NormalizedRecord,
    SourceType,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# GSTIN normalization
# ---------------------------------------------------------------------------


def test_normalize_gstin_valid():
    assert normalize_gstin("29ABCDE1234F1Z5") == "29ABCDE1234F1Z5"


def test_normalize_gstin_upcases_and_strips_whitespace():
    assert normalize_gstin("  29 abcde 1234 f1z5  ") == "29ABCDE1234F1Z5"


def test_normalize_gstin_none_returns_none():
    assert normalize_gstin(None) is None


def test_normalize_gstin_empty_returns_none():
    assert normalize_gstin("") is None
    assert normalize_gstin("   ") is None


def test_normalize_gstin_invalid_length_returns_none():
    assert normalize_gstin("29ABCDE1234F1Z") is None  # 14 chars
    assert normalize_gstin("29ABCDE1234F1Z5X") is None  # 16 chars


def test_normalize_gstin_non_alphanumeric_returns_none():
    assert normalize_gstin("29ABCDE-1234F1Z5") is None


# ---------------------------------------------------------------------------
# Invoice number normalization
# ---------------------------------------------------------------------------


def test_normalize_invoice_number_valid():
    assert normalize_invoice_number("INV-001") == "INV-001"


def test_normalize_invoice_number_collapses_whitespace_and_upcases():
    assert normalize_invoice_number("  inv  002  ") == "INV 002"


def test_normalize_invoice_number_none_and_empty():
    assert normalize_invoice_number(None) is None
    assert normalize_invoice_number("") is None
    assert normalize_invoice_number("   ") is None


# ---------------------------------------------------------------------------
# Date normalization
# ---------------------------------------------------------------------------


def test_normalize_date_iso():
    assert normalize_date("2024-04-15") == date(2024, 4, 15)


def test_normalize_date_multiple_formats():
    assert normalize_date("15-04-2024") == date(2024, 4, 15)
    assert normalize_date("15/04/2024") == date(2024, 4, 15)
    assert normalize_date("2024/04/15") == date(2024, 4, 15)
    assert normalize_date("15-04-24") == date(2024, 4, 15)


def test_normalize_date_invalid_returns_none():
    assert normalize_date("not-a-date") is None
    assert normalize_date("") is None
    assert normalize_date(None) is None
    assert normalize_date("13-13-2024") is None


# ---------------------------------------------------------------------------
# Amount normalization
# ---------------------------------------------------------------------------


def test_normalize_amount_plain():
    assert normalize_amount("5000.00") == Decimal("5000.00")


def test_normalize_amount_strips_commas_and_currency():
    assert normalize_amount("1,000.50") == Decimal("1000.50")
    assert normalize_amount("₹250") == Decimal("250.00")
    assert normalize_amount("  100  ") == Decimal("100.00")


def test_normalize_amount_rounding_half_up():
    assert normalize_amount("0.005") == Decimal("0.01")
    assert normalize_amount("0.004") == Decimal("0.00")
    assert normalize_amount("2.005") == Decimal("2.01")


def test_normalize_amount_negative():
    assert normalize_amount("-100.00") == Decimal("-100.00")


def test_normalize_amount_invalid_returns_none():
    assert normalize_amount("not-an-amount") is None
    assert normalize_amount("") is None
    assert normalize_amount(None) is None
    assert normalize_amount(True) is None  # boolean not a monetary value


def test_normalize_amount_quantizes_to_two_places():
    result = normalize_amount("123.456")
    assert result == Decimal("123.46")
    assert result == result.quantize(MONEY_PLACES)


# ---------------------------------------------------------------------------
# Record-level normalization
# ---------------------------------------------------------------------------


def test_normalize_records_valid_row(valid_row):
    records = normalize_records(
        [valid_row], SourceType.PURCHASE_REGISTER, "tests/fixture.csv"
    )
    assert len(records) == 1
    row = records[0]
    assert isinstance(row, NormalizedRecord)
    assert row.validation_status == ValidationStatus.VALID
    assert row.gstin == "29ABCDE1234F1Z5"
    assert row.invoice_number == "INV-001"
    assert row.invoice_date == date(2024, 4, 15)
    assert row.taxable_value == Decimal("5000.00")
    assert row.cgst == Decimal("450.00")
    assert row.sgst == Decimal("450.00")
    assert row.igst == Decimal("0.00")
    assert row.cess == Decimal("0.00")
    assert row.total_tax == Decimal("900.00")
    assert row.total_amount == Decimal("5900.00")
    assert row.raw_values == valid_row


def test_normalize_records_invalid_row_not_dropped():
    records = normalize_records(
        [
            {
                "gstin": "BAD",
                "invoice_number": "",
                "invoice_date": "not-a-date",
                "taxable_value": "not-an-amount",
            }
        ],
        SourceType.PURCHASE_REGISTER,
        "tests/fixture.csv",
    )
    assert len(records) == 1  # preserved, not dropped
    row = records[0]
    assert row.validation_status == ValidationStatus.INVALID
    assert len(row.validation_issues) >= 4  # gstin, invoice_number, date, amount


def test_normalize_records_missing_required_fields_flagged():
    records = normalize_records(
        [{"gstin": "29ABCDE1234F1Z5"}],
        SourceType.PURCHASE_REGISTER,
        "tests/fixture.csv",
    )
    row = records[0]
    assert row.validation_status == ValidationStatus.INVALID
    fields = {issue.field for issue in row.validation_issues}
    assert "invoice_number" in fields
    assert "invoice_date" in fields
    assert "taxable_value" in fields


def test_normalize_records_total_tax_and_amount():
    records = normalize_records(
        [
            {
                "gstin": "29ABCDE1234F1Z5",
                "invoice_number": "INV-1",
                "invoice_date": "2024-04-15",
                "taxable_value": "1000.00",
                "cgst": "90.00",
                "sgst": "90.00",
                "igst": "0.00",
                "cess": "0.00",
            }
        ],
        SourceType.PURCHASE_REGISTER,
        "tests/fixture.csv",
    )
    row = records[0]
    assert row.total_tax == Decimal("180.00")
    assert row.total_amount == Decimal("1180.00")


def test_normalize_records_missing_tax_components_total_is_none():
    records = normalize_records(
        [
            {
                "gstin": "29ABCDE1234F1Z5",
                "invoice_number": "INV-1",
                "invoice_date": "2024-04-15",
                "taxable_value": "1000.00",
                "cgst": "90.00",
                "sgst": None,
                "igst": None,
                "cess": None,
            }
        ],
        SourceType.PURCHASE_REGISTER,
        "tests/fixture.csv",
    )
    row = records[0]
    assert row.total_tax is None
    assert row.total_amount is None


def test_normalize_records_duplicate_rows_preserved():
    row_input = {
        "gstin": "29ABCDE1234F1Z5",
        "invoice_number": "INV-DUP",
        "invoice_date": "2024-04-15",
        "taxable_value": "100.00",
        "cgst": "9.00",
        "sgst": "9.00",
        "igst": "0.00",
        "cess": "0.00",
    }
    records = normalize_records(
        [dict(row_input), dict(row_input)],
        SourceType.PURCHASE_REGISTER,
        "tests/fixture.csv",
    )
    assert len(records) == 2  # duplicates preserved, not deduplicated


def test_normalize_records_is_deterministic(valid_row):
    first = normalize_records(
        [valid_row], SourceType.PURCHASE_REGISTER, "tests/fixture.csv"
    )
    second = normalize_records(
        [valid_row], SourceType.PURCHASE_REGISTER, "tests/fixture.csv"
    )
    assert first == second


def test_normalize_records_gstr2b_source_type(gstr2b_normalized):
    assert len(gstr2b_normalized) == 3
    for row in gstr2b_normalized:
        assert row.source_type == SourceType.GSTR_2B

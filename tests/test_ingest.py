"""Tests for the ingestion module (src/itc_sentinel/ingest.py).

Covers CSV/XLSX purchase-register loading and GSTR-2B JSON loading, column
validation, malformed-file handling, and preservation of invalid rows.
"""

from __future__ import annotations

import pytest

from itc_sentinel.ingest import (
    IngestionError,
    load_gstr2b_json,
    load_purchase_register,
)
from itc_sentinel.schemas import SourceType

# ---------------------------------------------------------------------------
# Valid fixtures load
# ---------------------------------------------------------------------------


def test_valid_purchase_register_csv_loads(purchase_register_raw):
    result = purchase_register_raw

    assert result.source_type == SourceType.PURCHASE_REGISTER
    assert result.row_count == 7
    assert result.file_hash != ""
    assert len(result.raw_records) == 7
    assert result.raw_records[0]["gstin"] == "29ABCDE1234F1Z5"
    assert result.raw_records[0]["invoice_number"] == "INV-001"
    assert result.raw_records[0]["taxable_value"] == "5000.00"


def test_valid_gstr2b_json_loads(gstr2b_raw):
    result = gstr2b_raw

    assert result.source_type == SourceType.GSTR_2B
    assert result.row_count == 3
    assert result.file_hash != ""
    assert result.raw_records[0]["supplier_gstin"] == "07FGHIJ5678K1Z6"
    assert result.raw_records[0]["invoice_number"] == "GSTR-INV-101"


# ---------------------------------------------------------------------------
# Missing required columns produce useful errors
# ---------------------------------------------------------------------------


def test_purchase_register_missing_required_column(tmp_csv):
    path = tmp_csv(
        ["gstin", "invoice_number", "vendor_name"],
        [
            {
                "gstin": "29ABCDE1234F1Z5",
                "invoice_number": "INV-1",
                "vendor_name": "X",
            }
        ],
        "missing_cols.csv",
    )
    with pytest.raises(IngestionError) as excinfo:
        load_purchase_register(str(path))
    message = str(excinfo.value)
    assert "invoice_date" in message
    assert "taxable_value" in message
    assert str(path) in message


def test_gstr2b_missing_top_level_field(tmp_json):
    path = tmp_json({"gstin": "29ABCDE1234F1Z5", "invoices": []})
    with pytest.raises(IngestionError) as excinfo:
        load_gstr2b_json(str(path))
    assert "period" in str(excinfo.value)


def test_gstr2b_invoices_not_a_list(tmp_json):
    path = tmp_json(
        {
            "gstin": "29ABCDE1234F1Z5",
            "period": "042024",
            "invoices": {},
        }
    )
    with pytest.raises(IngestionError) as excinfo:
        load_gstr2b_json(str(path))
    message = str(excinfo.value).lower()
    assert "invoices" in message
    assert "list" in message


# ---------------------------------------------------------------------------
# Malformed files produce useful errors
# ---------------------------------------------------------------------------


def test_malformed_json_produces_error(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(IngestionError) as excinfo:
        load_gstr2b_json(str(target))
    assert "Malformed JSON" in str(excinfo.value)


def test_csv_missing_required_columns_produces_error(tmp_path):
    target = tmp_path / "bad.csv"
    target.write_text("gstin,invoice_number\n", encoding="utf-8")
    with pytest.raises(IngestionError) as excinfo:
        load_purchase_register(str(target))
    assert "taxable_value" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Missing file / wrong file type
# ---------------------------------------------------------------------------


def test_missing_file_raises(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(IngestionError) as excinfo:
        load_purchase_register(str(missing))
    assert "not found" in str(excinfo.value).lower()


def test_unsupported_file_type_raises(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("not a register", encoding="utf-8")
    with pytest.raises(IngestionError):
        load_purchase_register(str(target))
    with pytest.raises(IngestionError):
        load_gstr2b_json(str(target))


# ---------------------------------------------------------------------------
# Empty datasets and empty files
# ---------------------------------------------------------------------------


def test_empty_csv_with_header_returns_zero_rows(tmp_csv):
    path = tmp_csv(
        [
            "gstin",
            "invoice_number",
            "invoice_date",
            "taxable_value",
        ],
        [],
        "empty.csv",
    )
    result = load_purchase_register(str(path))
    assert result.row_count == 0
    assert result.raw_records == []


def test_empty_json_invoices_list(tmp_json):
    path = tmp_json(
        {
            "gstin": "29ABCDE1234F1Z5",
            "period": "042024",
            "invoices": [],
        }
    )
    result = load_gstr2b_json(str(path))
    assert result.row_count == 0
    assert result.raw_records == []


# ---------------------------------------------------------------------------
# Invalid rows are preserved, not silently discarded
# ---------------------------------------------------------------------------


def test_invalid_rows_preserved_in_sample(purchase_register_raw):
    # The sample CSV contains intentionally invalid rows (bad GSTIN, missing
    # invoice number, bad date, bad amount). None may be dropped at ingest.
    assert purchase_register_raw.row_count == 7
    gstins = [row.get("gstin") for row in purchase_register_raw.raw_records]
    assert "INVALID-GSTIN" in gstins
    empty_inv = [
        row for row in purchase_register_raw.raw_records
        if row.get("invoice_number") == ""
    ]
    assert len(empty_inv) == 1


def test_normalization_preserves_invalid_rows(purchase_register_normalized):
    """Invalid rows remain in the output with validation_status INVALID."""
    invalid_count = sum(
        1 for r in purchase_register_normalized
        if r.validation_status.name == "INVALID"
    )
    assert invalid_count >= 1
    assert len(purchase_register_normalized) == 7


def test_normalized_invalid_row_keeps_issues(purchase_register_normalized):
    invalid_rows = [
        r for r in purchase_register_normalized
        if r.validation_status.name == "INVALID"
    ]
    assert len(invalid_rows) >= 1
    for row in invalid_rows:
        assert len(row.validation_issues) >= 1
        assert row.raw_values  # original values preserved for traceability


# ---------------------------------------------------------------------------
# Determinism / reproducibility
# ---------------------------------------------------------------------------


def test_ingest_is_deterministic(purchase_register_path):
    first = load_purchase_register(str(purchase_register_path))
    second = load_purchase_register(str(purchase_register_path))
    assert first.file_hash == second.file_hash
    assert first.raw_records == second.raw_records


def test_amount_rounding_is_deterministic(money_examples):
    from itc_sentinel.normalize import normalize_amount

    results = [normalize_amount(text) for text, _ in money_examples]
    expected = [decimal for _, decimal in money_examples]
    assert results == expected

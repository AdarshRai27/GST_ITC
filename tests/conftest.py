"""Shared pytest fixtures for the ITC Sentinel test suite.

Fixtures provide synthetic input data and paths to sample files only. No real
taxpayer data is used.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from itc_sentinel.ingest import load_gstr2b_json, load_purchase_register
from itc_sentinel.normalize import normalize_records

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "sample"
PURCHASE_REGISTER_CSV = FIXTURES_DIR / "purchase_register.csv"
GSTR2B_JSON = FIXTURES_DIR / "gstr2b.json"


@pytest.fixture
def purchase_register_path() -> Path:
    return PURCHASE_REGISTER_CSV


@pytest.fixture
def gstr2b_path() -> Path:
    return GSTR2B_JSON


@pytest.fixture
def purchase_register_raw(purchase_register_path: Path):
    return load_purchase_register(str(purchase_register_path))


@pytest.fixture
def gstr2b_raw(gstr2b_path: Path):
    return load_gstr2b_json(str(gstr2b_path))


@pytest.fixture
def purchase_register_normalized(purchase_register_raw):
    return normalize_records(
        purchase_register_raw.raw_records,
        purchase_register_raw.source_type,
        purchase_register_raw.source_file,
    )


@pytest.fixture
def gstr2b_normalized(gstr2b_raw):
    return normalize_records(
        gstr2b_raw.raw_records,
        gstr2b_raw.source_type,
        gstr2b_raw.source_file,
    )


@pytest.fixture
def tmp_csv(tmp_path: Path) -> Path:
    """Write a CSV file from a header and rows; return its path."""

    def writer(header: list[str], rows: list[dict], name: str = "data.csv") -> Path:
        target = tmp_path / name
        with open(target, "w", newline="", encoding="utf-8") as handle:
            csv_writer = csv.DictWriter(handle, fieldnames=header)
            csv_writer.writeheader()
            for row in rows:
                csv_writer.writerow(row)
        return target

    return writer


@pytest.fixture
def tmp_json(tmp_path: Path) -> Path:
    """Write a JSON file from an object; return its path."""

    def writer(obj, name: str = "data.json") -> Path:
        target = tmp_path / name
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(obj, handle)
        return target

    return writer


@pytest.fixture
def valid_row() -> dict:
    return {
        "gstin": "29ABCDE1234F1Z5",
        "invoice_number": "INV-001",
        "invoice_date": "2024-04-15",
        "taxable_value": "5000.00",
        "cgst": "450.00",
        "sgst": "450.00",
        "igst": "0.00",
        "cess": "0.00",
        "vendor_name": "Acme Supplies",
    }


@pytest.fixture
def money_examples() -> list[tuple[str, Decimal]]:
    return [
        ("5000.00", Decimal("5000.00")),
        ("1,000.50", Decimal("1000.50")),
        ("₹250", Decimal("250.00")),
        ("  100  ", Decimal("100.00")),
        ("0.005", Decimal("0.01")),  # ROUND_HALF_UP -> 0.01
        ("0.004", Decimal("0.00")),  # ROUND_HALF_UP -> 0.00
        ("-100.00", Decimal("-100.00")),
    ]

"""Synthetic data generator for ITC Sentinel Phase 2.

Generates a purchase-register CSV and GSTR-2B JSON with known ground truth
for testing deterministic reconciliation. All data is synthetic; no real
taxpayer data is used.

Outputs (deterministic, seeded):
  data/sample/purchase_register_synthetic.csv
  data/sample/gstr2b_synthetic.json
  data/sample/ground_truth.json

Usage:
    python scripts/generate_synthetic_data.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Synthetic data (deterministic, no randomness)
# ---------------------------------------------------------------------------

# Each purchase-register row: (gstin, invoice_number, invoice_date,
# taxable_value, cgst, sgst, igst, cess, vendor_name)
PURCHASE_ROWS = [
    # 0: Exact match (books and 2B agree on everything)
    ("29ABCDE1234F1Z5", "INV-1001", "2024-04-15", "5000.00", "450.00", "450.00", "0.00", "0.00", "Acme Supplies"),
    # 1: Exact match
    ("07FGHIJ5678K1Z6", "INV-2001", "2024-04-16", "8000.00", "0.00", "0.00", "1440.00", "0.00", "Delhi Traders"),
    # 2: Invoice-number formatting difference ("INV-3001" vs "INV 3001")
    ("29ABCDE1234F1Z5", "INV-3001", "2024-04-17", "3000.00", "270.00", "270.00", "0.00", "0.00", "Acme Supplies"),
    # 3: Amount mismatch (same invoice, different taxable value)
    ("07FGHIJ5678K1Z6", "INV-4001", "2024-04-18", "6000.00", "540.00", "540.00", "0.00", "0.00", "Delhi Traders"),
    # 4: Tax-head mismatch (domestic vs IGST)
    ("29ABCDE1234F1Z5", "INV-5001", "2024-04-19", "4000.00", "360.00", "360.00", "0.00", "0.00", "Acme Supplies"),
    # 5: Duplicate of row 0 (same GSTIN + invoice number)
    ("29ABCDE1234F1Z5", "INV-1001", "2024-04-15", "5000.00", "450.00", "450.00", "0.00", "0.00", "Acme Supplies"),
    # 6: Invalid GSTIN (will fail Phase 1 validation)
    ("BAD-GSTIN", "INV-7001", "2024-04-20", "2000.00", "180.00", "180.00", "0.00", "0.00", "Bad Vendor"),
    # 7: Unmatched in books (no counterpart in GSTR-2B)
    ("07FGHIJ5678K1Z6", "INV-9001", "2024-04-21", "1500.00", "135.00", "135.00", "0.00", "0.00", "Delhi Traders"),
    # 8: Probable fuzzy match (invoice number similar but not exact)
    ("29ABCDE1234F1Z5", "INV-6001A", "2024-04-22", "2500.00", "225.00", "225.00", "0.00", "0.00", "Acme Supplies"),
]

# Each GSTR-2B invoice: (supplier_gstin, invoice_number, invoice_date,
# taxable_value, cgst, sgst, igst, cess, invoice_type)
GSTR2B_INVOICES = [
    # 0: Exact match for books row 0
    ("29ABCDE1234F1Z5", "INV-1001", "2024-04-15", "5000.00", "450.00", "450.00", "0.00", "0.00", "B2B"),
    # 1: Exact match for books row 1
    ("07FGHIJ5678K1Z6", "INV-2001", "2024-04-16", "8000.00", "0.00", "0.00", "1440.00", "0.00", "B2B"),
    # 2: Formatting difference for books row 2 ("INV 3001" vs "INV-3001")
    ("29ABCDE1234F1Z5", "INV 3001", "2024-04-17", "3000.00", "270.00", "270.00", "0.00", "0.00", "B2B"),
    # 3: Amount mismatch for books row 3 (2B says 5500 not 6000)
    ("07FGHIJ5678K1Z6", "INV-4001", "2024-04-18", "5500.00", "495.00", "495.00", "0.00", "0.00", "B2B"),
    # 4: Tax-head mismatch for books row 4 (2B uses IGST instead of CGST+SGST)
    ("29ABCDE1234F1Z5", "INV-5001", "2024-04-19", "4000.00", "0.00", "0.00", "720.00", "0.00", "B2B"),
    # 6: Unmatched in GSTR-2B (no counterpart in books)
    ("29ABCDE1234F1Z5", "INV-8001", "2024-04-23", "3500.00", "315.00", "315.00", "0.00", "0.00", "B2B"),
    # 8: Probable fuzzy match for books row 8 ("INV-6001A" vs "INV-6001-B")
    ("29ABCDE1234F1Z5", "INV-6001-B", "2024-04-22", "2500.00", "225.00", "225.00", "0.00", "0.00", "B2B"),
]

# Expected outcomes per purchase-register row index.
# Key: row index -> expected match status
EXPECTED_BOOK_STATUS = {
    0: "exact",
    1: "exact",
    2: "fuzzy",          # invoice number formatting differs (INV-3001 vs INV 3001)
    3: "amount_mismatch",
    4: "tax_head_mismatch",
    5: "duplicate",
    6: "invalid",
    7: "unmatched_books",
    8: "probable",       # invoice number similar but not exact (INV-6001A vs INV-6001-B)
}

# Expected unmatched GSTR-2B indices
EXPECTED_UNMATCHED_GSTR2B = [5]  # INV-8001 has no counterpart in books


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _write_purchase_register(path: Path) -> None:
    header = [
        "gstin", "invoice_number", "invoice_date", "taxable_value",
        "cgst", "sgst", "igst", "cess", "vendor_name",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in PURCHASE_ROWS:
            writer.writerow(row)


def _write_gstr2b_json(path: Path) -> None:
    data = {
        "gstin": "29ABCDE1234F1Z5",
        "period": "042024",
        "invoices": [
            {
                "supplier_gstin": row[0],
                "invoice_number": row[1],
                "invoice_date": row[2],
                "taxable_value": row[3],
                "cgst": row[4],
                "sgst": row[5],
                "igst": row[6],
                "cess": row[7],
                "invoice_type": row[8],
            }
            for row in GSTR2B_INVOICES
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _write_ground_truth(path: Path) -> None:
    truth = {
        "purchase_register_file": "purchase_register_synthetic.csv",
        "gstr2b_file": "gstr2b_synthetic.json",
        "description": "Synthetic ground truth for Phase 2 deterministic reconciliation testing.",
        "expected_book_status": EXPECTED_BOOK_STATUS,
        "expected_unmatched_gstr2b_indices": EXPECTED_UNMATCHED_GSTR2B,
        "expected_counts": {
            "exact": 2,
            "fuzzy": 1,
            "amount_mismatch": 1,
            "tax_head_mismatch": 1,
            "duplicate": 1,
            "invalid": 1,
            "probable": 1,
            "unmatched_books": 1,
            "unmatched_gstr2b": 1,
        },
        "notes": (
            "All data is synthetic. Ground truth is defined independently "
            "of the matching implementation."
        ),
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(truth, handle, indent=2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    base = Path(__file__).resolve().parent.parent / "data" / "sample"
    base.mkdir(parents=True, exist_ok=True)

    _write_purchase_register(base / "purchase_register_synthetic.csv")
    _write_gstr2b_json(base / "gstr2b_synthetic.json")
    _write_ground_truth(base / "ground_truth.json")

    print(f"Wrote {base / 'purchase_register_synthetic.csv'}")
    print(f"Wrote {base / 'gstr2b_synthetic.json'}")
    print(f"Wrote {base / 'ground_truth.json'}")


if __name__ == "__main__":
    main()

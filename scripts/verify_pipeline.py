"""Reproducible end-to-end verification for the ITC Sentinel MVP.

Runs the complete synthetic-data pipeline (ingest → normalize → reconcile →
decide → metrics → export → audit) and compares the result with the committed
ground truth. Prints one line per check and exits non-zero on failure.

Usage (from the repository root):

    python scripts/verify_pipeline.py

This script replaces the stale ``verify_phase6.py`` reference in the earlier
audit report. It is intentionally dependency-light and uses only the project
package plus the synthetic fixtures.
"""

from __future__ import annotations

import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from itc_sentinel.audit import (  # noqa: E402
    AuditEvent,
    AuditEventType,
    AuditLog,
    _utc_now_iso,
)
from itc_sentinel.decision import (  # noqa: E402
    Action,
    allowed_review_decisions,
    decide,
    validate_review_decision,
)
from itc_sentinel.ingest import load_gstr2b_json, load_purchase_register  # noqa: E402
from itc_sentinel.matcher import MatchStatus, reconcile  # noqa: E402
from itc_sentinel.metrics import compute_metrics  # noqa: E402
from itc_sentinel.normalize import normalize_records  # noqa: E402
from itc_sentinel.report import export_workbook, safe_cell_value  # noqa: E402

SAMPLE = ROOT / "data" / "sample"
PURCHASE = SAMPLE / "purchase_register_synthetic.csv"
GSTR2B = SAMPLE / "gstr2b_synthetic.json"
GROUND_TRUTH = SAMPLE / "ground_truth.json"

_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    if not condition:
        _failures.append(name)


def main() -> int:
    truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))

    purchase_raw = load_purchase_register(str(PURCHASE))
    gstr2b_raw = load_gstr2b_json(str(GSTR2B))
    check("purchase-register ingestion", purchase_raw.row_count == 9,
          f"{purchase_raw.row_count} rows")
    check("GSTR-2B ingestion", gstr2b_raw.row_count == 7,
          f"{gstr2b_raw.row_count} rows")

    books = normalize_records(
        purchase_raw.raw_records, purchase_raw.source_type, purchase_raw.source_file
    )
    gstr2b = normalize_records(
        gstr2b_raw.raw_records, gstr2b_raw.source_type, gstr2b_raw.source_file
    )
    check("normalization preserves rows", len(books) == 9 and len(gstr2b) == 7)

    result = reconcile(books, gstr2b)
    book_status = {
        str(m.purchase_record.source_row): m.match_status.value
        for m in result.matches
        if m.purchase_record is not None
    }
    check(
        "book-row statuses match ground truth",
        book_status == truth["expected_book_status"],
        f"{book_status}",
    )

    unmatched_2b = [
        m.gstr2b_record.source_row
        for m in result.matches
        if m.gstr2b_record is not None and m.match_status == MatchStatus.UNMATCHED_GSTR2B
    ]
    check(
        "unmatched GSTR-2B indices match ground truth",
        unmatched_2b == truth["expected_unmatched_gstr2b_indices"],
        f"{unmatched_2b}",
    )
    check(
        "status counts match ground truth",
        result.summary == truth["expected_counts"],
        f"{result.summary}",
    )

    confirmed_statuses = {
        MatchStatus.EXACT,
        MatchStatus.AMOUNT_MISMATCH,
        MatchStatus.TAX_HEAD_MISMATCH,
        MatchStatus.FUZZY,
    }
    confirmed_rows = {
        int(row): status
        for row, status in truth["expected_book_status"].items()
        if MatchStatus(status) in confirmed_statuses
    }
    predicted = {int(row): MatchStatus(status) for row, status in book_status.items()}
    true_positives = sum(
        1
        for row, status in confirmed_rows.items()
        if predicted.get(row) == status
    )
    precision = true_positives / sum(
        1 for status in predicted.values() if status in confirmed_statuses
    )
    recall = true_positives / len(confirmed_rows)
    check("confirmed-match precision = 1.0", precision == 1.0, f"{precision:.2f}")
    check("confirmed-match recall = 1.0", recall == 1.0, f"{recall:.2f}")

    decisions = [decide(match) for match in result.matches]
    check("one decision per reconciliation row", len(decisions) == len(result.matches))
    exact = [
        d for d in decisions if d.match_result.match_status == MatchStatus.EXACT
    ]
    check(
        "exact matches are candidates, not approved claims",
        all(
            d.action == Action.PROPOSE_ITC_CLAIM and d.review_required
            for d in exact
        ),
    )
    invalid = [
        d for d in decisions if d.match_result.match_status == MatchStatus.INVALID
    ]
    check(
        "invalid rows cannot be approved",
        all("approve" not in allowed_review_decisions(d) for d in invalid)
        and all(
            _raises(lambda d=d: validate_review_decision(d, "approve"))
            for d in invalid
        ),
    )

    metrics = compute_metrics(result, decisions, [])
    check("confirmed KPI excludes mismatches", metrics.confirmed_matches == 2,
          f"{metrics.confirmed_matches}")
    check("review-required count", metrics.review_required == 9,
          f"{metrics.review_required}")
    check("no records reviewed initially", metrics.reviewed_records == 0)
    check(
        "source-row count",
        metrics.total_source_rows == 16,
        f"{metrics.total_source_rows}",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        export_path = Path(temp_dir) / "verification.xlsx"
        export = export_workbook(str(export_path), decisions)
        check(
            "Excel export creates expected sheets",
            export.sheets[:3] == ["Summary", "Reconciliation", "Decisions"],
            ", ".join(export.sheets),
        )
        check("Excel file is non-empty", export_path.stat().st_size > 0)
        check(
            "formula injection is escaped",
            safe_cell_value("=1+1") == "'=1+1"
            and safe_cell_value("  =1+1") == "'  =1+1",
        )

        audit_path = Path(temp_dir) / "audit.jsonl"
        audit = AuditLog(audit_path)
        audit.append(
            AuditEvent(
                event_id="verify-1",
                timestamp=_utc_now_iso(),
                event_type=AuditEventType.RUN_STARTED,
                run_id="verify-run",
                summary="verification",
            )
        )
        check("audit log round-trips", audit.read_events()[0].event_id == "verify-1")

    check(
        "provisional exposure is quantified",
        metrics.provisional_exposure == Decimal("8890.00"),
        f"{metrics.provisional_exposure}",
    )

    print()
    if _failures:
        print(f"FAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("All pipeline verification checks passed.")
    return 0


def _raises(func) -> bool:
    try:
        func()
    except ValueError:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())

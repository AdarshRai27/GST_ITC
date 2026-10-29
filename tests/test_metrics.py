"""Tests for dashboard/report metrics (src/itc_sentinel/metrics.py).

The original defect counted amount mismatches, tax-head mismatches and fuzzy
matches as "confirmed matches". These tests lock in the corrected definitions.
"""

from __future__ import annotations

from decimal import Decimal

from itc_sentinel.audit import ReviewRecord
from itc_sentinel.decision import decide
from itc_sentinel.ingest import load_gstr2b_json, load_purchase_register
from itc_sentinel.matcher import ReconciliationResult, reconcile
from itc_sentinel.metrics import compute_metrics
from itc_sentinel.normalize import normalize_records

PURCHASE_CSV = "data/sample/purchase_register_synthetic.csv"
GSTR2B_JSON = "data/sample/gstr2b_synthetic.json"


def _run_sample():
    purchase = load_purchase_register(PURCHASE_CSV)
    gstr2b = load_gstr2b_json(GSTR2B_JSON)
    books = normalize_records(
        purchase.raw_records, purchase.source_type, purchase.source_file
    )
    gstr2b_records = normalize_records(
        gstr2b.raw_records, gstr2b.source_type, gstr2b.source_file
    )
    result = reconcile(books, gstr2b_records)
    decisions = [decide(match) for match in result.matches]
    return result, decisions


def _review(record_id: str, decision: str, timestamp: str = "2026-01-01T00:00:00+00:00"):
    return ReviewRecord(
        review_id=f"rev-{record_id}-{decision}",
        run_id="run-1",
        invoice_key="29ABCDE1234F1Z5|INV-1001",
        match_status="exact",
        suggested_action="propose_itc_claim",
        decision=decision,
        timestamp=timestamp,
        record_id=record_id,
        new_state=decision,
    )


def test_sample_counts_are_predictable():
    result, decisions = _run_sample()
    metrics = compute_metrics(result, decisions, [])

    # 9 purchase-register rows + 7 GSTR-2B invoices = 16 source rows.
    assert metrics.total_source_rows == 16
    # 10 reconciliation rows: 9 book-side results + 1 GSTR-2B-only result.
    assert metrics.total_reconciliation_rows == 10

    assert metrics.exact_matches == 2
    assert metrics.fuzzy_candidates == 1
    assert metrics.probable_candidates == 1
    assert metrics.low_confidence_candidates == 0
    assert metrics.amount_mismatches == 1
    assert metrics.tax_head_mismatches == 1
    assert metrics.duplicates == 1
    assert metrics.invalid_records == 1
    assert metrics.unmatched_books == 1
    assert metrics.unmatched_gstr2b == 1

    # Every status has exactly one bucket; nothing is double counted.
    assert sum(
        [
            metrics.exact_matches,
            metrics.fuzzy_candidates,
            metrics.probable_candidates,
            metrics.low_confidence_candidates,
            metrics.amount_mismatches,
            metrics.tax_head_mismatches,
            metrics.duplicates,
            metrics.invalid_records,
            metrics.unmatched_books,
            metrics.unmatched_gstr2b,
        ]
    ) == metrics.total_reconciliation_rows


def test_mismatches_and_fuzzy_are_not_confirmed_matches():
    result, decisions = _run_sample()
    metrics = compute_metrics(result, decisions, [])

    assert metrics.confirmed_matches == metrics.exact_matches == 2
    assert metrics.amount_mismatches == 1
    assert metrics.tax_head_mismatches == 1
    assert metrics.fuzzy_candidates == 1
    assert metrics.probable_candidates == 1
    # The old buggy KPI would have reported 5.
    assert metrics.confirmed_matches != (
        metrics.exact_matches
        + metrics.amount_mismatches
        + metrics.tax_head_mismatches
        + metrics.fuzzy_candidates
    )


def test_metrics_agree_with_matcher_summary():
    result, decisions = _run_sample()
    summary = result.summary
    metrics = compute_metrics(result, decisions, [])

    assert metrics.exact_matches == summary.get("exact", 0)
    assert metrics.fuzzy_candidates == summary.get("fuzzy", 0)
    assert metrics.probable_candidates == summary.get("probable", 0)
    assert metrics.amount_mismatches == summary.get("amount_mismatch", 0)
    assert metrics.tax_head_mismatches == summary.get("tax_head_mismatch", 0)
    assert metrics.duplicates == summary.get("duplicate", 0)
    assert metrics.invalid_records == summary.get("invalid", 0)
    assert metrics.unmatched_books == summary.get("unmatched_books", 0)
    assert metrics.unmatched_gstr2b == summary.get("unmatched_gstr2b", 0)


def test_review_metrics_use_latest_decision_per_record():
    result, decisions = _run_sample()
    reviews = [
        _review("books:0", "pending", "2026-01-01T00:00:00+00:00"),
        _review("books:0", "approve", "2026-01-02T00:00:00+00:00"),
        _review("books:0", "reject", "2026-01-03T00:00:00+00:00"),
        _review("books:1", "approve", "2026-01-04T00:00:00+00:00"),
        _review("books:2", "pending", "2026-01-05T00:00:00+00:00"),
    ]
    metrics = compute_metrics(result, decisions, reviews)

    # books:0 counted once, with its latest state (reject).
    assert metrics.reviewed_records == 3
    assert metrics.rejected == 1
    assert metrics.accepted == 1
    assert metrics.pending == 1
    assert metrics.review_records_total == 5
    assert metrics.reviews_for_other_runs == 0
    assert metrics.awaiting_review == metrics.review_required - 3


def test_reviews_from_other_runs_are_not_counted():
    result, decisions = _run_sample()
    reviews = [
        _review("books:999", "approve"),
        _review("books:0", "approve"),
    ]
    metrics = compute_metrics(result, decisions, reviews)

    assert metrics.reviewed_records == 1
    assert metrics.accepted == 1
    assert metrics.reviews_for_other_runs == 1


def test_empty_run_metrics_are_zero_and_complete():
    metrics = compute_metrics(ReconciliationResult(), [], [])

    assert metrics.total_reconciliation_rows == 0
    assert metrics.total_source_rows == 0
    assert metrics.confirmed_matches == 0
    assert metrics.review_required == 0
    assert metrics.awaiting_review == 0
    assert metrics.provisional_exposure == Decimal("0.00")
    assert metrics.review_completion_ratio == 1.0


def test_review_required_matches_decision_policy():
    result, decisions = _run_sample()
    metrics = compute_metrics(result, decisions, [])

    expected = sum(1 for d in decisions if d.review_required)
    assert metrics.review_required == expected
    # Only the GSTR-2B-only row is outside the review worklist.
    assert metrics.review_required == 9
    assert metrics.awaiting_review == 9
    assert metrics.review_completion_ratio == 0.0


def test_metrics_as_dict_includes_derived_values():
    result, decisions = _run_sample()
    data = compute_metrics(result, decisions, []).as_dict()

    assert data["confirmed_matches"] == 2
    assert "review_completion_ratio" in data
    assert data["amount_mismatches"] == 1

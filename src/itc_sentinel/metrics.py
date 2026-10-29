"""Dashboard/report metrics for ITC Sentinel.

Metrics are calculated here, once, and consumed by both the Streamlit UI and
the Excel export. This prevents the UI from inventing its own aggregation and
prevents mismatches from being counted as confirmed matches.

Counting rules
--------------
* **Reconciliation rows** count :class:`~itc_sentinel.matcher.MatchResult`
  objects. A matched pair is one reconciliation row, not two.
* **Source rows** count the underlying purchase-register and GSTR-2B records.
  A matched pair therefore contributes two source rows but one reconciliation
  row.
* **Status counts** are mutually exclusive because each reconciliation result
  has exactly one ``match_status``.
* **Confirmed matches** means exact matches only. Amount mismatches,
  tax-head mismatches, fuzzy matches, probable matches, duplicates, invalid
  rows, and unmatched rows are *not* confirmed matches.
* **Reviewed records** are de-duplicated by stable record identity; when a
  reviewer changes a decision, the latest review record wins.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal

from .audit import ReviewRecord
from .decision import DecisionResult
from .matcher import MatchStatus, ReconciliationResult, record_identity

__all__ = ["ReconciliationMetrics", "compute_metrics"]

# Statuses that are explicitly *not* confirmed matches. Kept as a single
# documented set so a future status cannot silently be folded into the
# confirmed-match KPI.
NON_CONFIRMED_STATUSES: frozenset[MatchStatus] = frozenset(
    {
        MatchStatus.AMOUNT_MISMATCH,
        MatchStatus.TAX_HEAD_MISMATCH,
        MatchStatus.FUZZY,
        MatchStatus.PROBABLE,
        MatchStatus.LOW_CONFIDENCE,
        MatchStatus.UNMATCHED_BOOKS,
        MatchStatus.UNMATCHED_GSTR2B,
        MatchStatus.DUPLICATE,
        MatchStatus.INVALID,
    }
)


@dataclass(frozen=True)
class ReconciliationMetrics:
    """Aggregated, documented reconciliation metrics for one run."""

    total_reconciliation_rows: int = 0
    total_source_rows: int = 0

    exact_matches: int = 0
    fuzzy_candidates: int = 0
    probable_candidates: int = 0
    low_confidence_candidates: int = 0
    amount_mismatches: int = 0
    tax_head_mismatches: int = 0
    duplicates: int = 0
    invalid_records: int = 0
    unmatched_books: int = 0
    unmatched_gstr2b: int = 0

    review_required: int = 0
    reviewed_records: int = 0
    awaiting_review: int = 0
    accepted: int = 0
    rejected: int = 0
    pending: int = 0
    review_records_total: int = 0
    reviews_for_other_runs: int = 0

    provisional_exposure: Decimal = Decimal("0.00")

    @property
    def confirmed_matches(self) -> int:
        """Exact matches only; mismatches are never confirmed matches."""
        return self.exact_matches

    @property
    def review_completion_ratio(self) -> float:
        """Share of review-required rows that have any recorded review.

        A run with nothing to review is treated as complete (1.0).
        """
        if self.review_required <= 0:
            return 1.0
        return min(1.0, self.reviewed_records / self.review_required)

    def as_dict(self) -> dict[str, object]:
        """Return a plain dictionary, including derived properties."""
        data = asdict(self)
        data["confirmed_matches"] = self.confirmed_matches
        data["review_completion_ratio"] = self.review_completion_ratio
        return data


def _status_bucket(status: MatchStatus) -> str:
    return {
        MatchStatus.EXACT: "exact_matches",
        MatchStatus.FUZZY: "fuzzy_candidates",
        MatchStatus.PROBABLE: "probable_candidates",
        MatchStatus.LOW_CONFIDENCE: "low_confidence_candidates",
        MatchStatus.AMOUNT_MISMATCH: "amount_mismatches",
        MatchStatus.TAX_HEAD_MISMATCH: "tax_head_mismatches",
        MatchStatus.DUPLICATE: "duplicates",
        MatchStatus.INVALID: "invalid_records",
        MatchStatus.UNMATCHED_BOOKS: "unmatched_books",
        MatchStatus.UNMATCHED_GSTR2B: "unmatched_gstr2b",
    }[status]


def _review_key(record: ReviewRecord) -> str:
    """Return the association key for a review record."""
    if record.record_id:
        return record.record_id
    return f"invoice:{record.invoice_key or ''}"


def _decision_keys(decisions: list[DecisionResult]) -> dict[str, DecisionResult]:
    """Build the set of identities present in this run."""
    return {
        record_identity(d.match_result): d
        for d in decisions
    }


def compute_metrics(
    result: ReconciliationResult,
    decisions: list[DecisionResult],
    review_records: list[ReviewRecord] | None = None,
) -> ReconciliationMetrics:
    """Compute all dashboard metrics for one reconciliation run.

    Args:
        result: The reconciliation result for the run. Used for source-row
            counts.
        decisions: The decisions produced for every match result.
        review_records: Human review records for this run (may include older
            records for the same records; the latest wins).

    Returns:
        A :class:`ReconciliationMetrics` instance.
    """
    review_records = review_records or []

    status_counts: dict[str, int] = {
        "exact_matches": 0,
        "fuzzy_candidates": 0,
        "probable_candidates": 0,
        "low_confidence_candidates": 0,
        "amount_mismatches": 0,
        "tax_head_mismatches": 0,
        "duplicates": 0,
        "invalid_records": 0,
        "unmatched_books": 0,
        "unmatched_gstr2b": 0,
    }

    total_source_rows = 0
    for match in result.matches:
        if match.purchase_record is not None:
            total_source_rows += 1
        if match.gstr2b_record is not None:
            total_source_rows += 1

    for decision in decisions:
        status_counts[_status_bucket(decision.match_result.match_status)] += 1

    decision_by_id = _decision_keys(decisions)
    invoice_index: dict[str, str] = {}
    for key, decision in decision_by_id.items():
        record = (
            decision.match_result.purchase_record
            or decision.match_result.gstr2b_record
        )
        if record is None:
            continue
        invoice_key = (
            f"invoice:{record.gstin or ''}|{record.invoice_number or ''}"
        )
        invoice_index[invoice_key] = key

    # Latest review per stable record identity wins.
    latest: dict[str, str] = {}
    reviews_for_other_runs = 0
    for record in review_records:
        key = _review_key(record)
        if record.record_id:
            if key not in decision_by_id:
                reviews_for_other_runs += 1
                continue
        else:
            key = invoice_index.get(key, key)
            if key not in decision_by_id:
                reviews_for_other_runs += 1
                continue
        latest[key] = record.decision

    review_required = sum(1 for d in decisions if d.review_required)
    required_ids = {
        key for key, d in decision_by_id.items() if d.review_required
    }
    required_latest = {
        key: state for key, state in latest.items() if key in required_ids
    }
    reviewed_required = len(required_latest)

    exposure = Decimal("0.00")
    for decision in decisions:
        if decision.exposure_amount is not None:
            exposure += decision.exposure_amount

    return ReconciliationMetrics(
        total_reconciliation_rows=len(decisions),
        total_source_rows=total_source_rows,
        exact_matches=status_counts["exact_matches"],
        fuzzy_candidates=status_counts["fuzzy_candidates"],
        probable_candidates=status_counts["probable_candidates"],
        low_confidence_candidates=status_counts["low_confidence_candidates"],
        amount_mismatches=status_counts["amount_mismatches"],
        tax_head_mismatches=status_counts["tax_head_mismatches"],
        duplicates=status_counts["duplicates"],
        invalid_records=status_counts["invalid_records"],
        unmatched_books=status_counts["unmatched_books"],
        unmatched_gstr2b=status_counts["unmatched_gstr2b"],
        review_required=review_required,
        reviewed_records=reviewed_required,
        awaiting_review=max(0, review_required - reviewed_required),
        accepted=sum(
            1 for state in required_latest.values() if state == "approve"
        ),
        rejected=sum(
            1 for state in required_latest.values() if state == "reject"
        ),
        pending=sum(
            1 for state in required_latest.values() if state == "pending"
        ),
        review_records_total=len(review_records),
        reviews_for_other_runs=reviews_for_other_runs,
        provisional_exposure=exposure.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    )

"""Tests for the deterministic reconciliation module (src/itc_sentinel/matcher.py).

Covers exact matching, fuzzy/probable matching, unmatched records, duplicates,
invalid records, one-to-one constraints, determinism, and ground-truth
precision/recall measurement.

All fixtures are synthetic; no real taxpayer data is used.
"""

from __future__ import annotations

from decimal import Decimal

from itc_sentinel.ingest import load_gstr2b_json, load_purchase_register
from itc_sentinel.matcher import (
    MatchStatus,
    ReconciliationSettings,
    reconcile,
)
from itc_sentinel.normalize import (
    normalize_amount,
    normalize_date,
    normalize_gstin,
    normalize_invoice_number,
    normalize_records,
)
from itc_sentinel.schemas import (
    NormalizedRecord,
    SourceType,
    ValidationIssue,
    ValidationStatus,
)

PURCHASE_CSV = "data/sample/purchase_register_synthetic.csv"
GSTR2B_JSON = "data/sample/gstr2b_synthetic.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_normalized(purchase_path=PURCHASE_CSV, gstr2b_path=GSTR2B_JSON):
    """Load and normalize both input files; return (books, gstr2b)."""
    book_ingest = load_purchase_register(purchase_path)
    gstr_ingest = load_gstr2b_json(gstr2b_path)

    books = normalize_records(
        book_ingest.raw_records,
        book_ingest.source_type,
        book_ingest.source_file,
    )
    gstr2b = normalize_records(
        gstr_ingest.raw_records,
        gstr_ingest.source_type,
        gstr_ingest.source_file,
    )
    return books, gstr2b


def _book_statuses(result):
    """Return {source_row: match_status} for purchase-register records."""
    statuses = {}
    for m in result.matches:
        if m.purchase_record is not None:
            statuses[m.purchase_record.source_row] = m.match_status
    return statuses


def _gstr2b_statuses(result):
    """Return {source_row: match_status} for unmatched GSTR-2B records."""
    statuses = {}
    for m in result.matches:
        if m.gstr2b_record is not None and m.purchase_record is None:
            statuses[m.gstr2b_record.source_row] = m.match_status
    return statuses


def _matched_pairs(result):
    """Return {(book_row, gstr2b_row): match_status} for matched pairs."""
    pairs = {}
    for m in result.matched_pairs:
        b = m.purchase_record.source_row if m.purchase_record else None
        g = m.gstr2b_record.source_row if m.gstr2b_record else None
        pairs[(b, g)] = m.match_status
    return pairs


# ---------------------------------------------------------------------------
# End-to-end reconciliation on synthetic fixtures
# ---------------------------------------------------------------------------


def test_synthetic_exact_matches():
    """Books rows 0 and 1 should match GSTR-2B exactly."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[0] == MatchStatus.EXACT
    assert statuses[1] == MatchStatus.EXACT

    pairs = _matched_pairs(result)
    assert (0, 0) in pairs and pairs[(0, 0)] == MatchStatus.EXACT
    assert (1, 1) in pairs and pairs[(1, 1)] == MatchStatus.EXACT


def test_synthetic_invoice_formatting_difference_is_fuzzy():
    """Books row 2 (INV-3001) vs GSTR-2B index 2 (INV 3001) should be FUZZY."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[2] == MatchStatus.FUZZY
    pairs = _matched_pairs(result)
    assert (2, 2) in pairs and pairs[(2, 2)] == MatchStatus.FUZZY


def test_synthetic_amount_mismatch():
    """Books row 3 (taxable 6000 vs 2B 5500) should be AMOUNT_MISMATCH."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[3] == MatchStatus.AMOUNT_MISMATCH
    pairs = _matched_pairs(result)
    assert (3, 3) in pairs and pairs[(3, 3)] == MatchStatus.AMOUNT_MISMATCH


def test_synthetic_tax_head_mismatch():
    """Books row 4 (CGST+SGST vs IGST) should be TAX_HEAD_MISMATCH."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[4] == MatchStatus.TAX_HEAD_MISMATCH
    pairs = _matched_pairs(result)
    assert (4, 4) in pairs and pairs[(4, 4)] == MatchStatus.TAX_HEAD_MISMATCH


def test_synthetic_duplicate_is_flagged():
    """Books row 5 (duplicate of row 0) should be DUPLICATE."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[5] == MatchStatus.DUPLICATE


def test_synthetic_invalid_record_is_flagged():
    """Books row 6 (bad GSTIN) should be INVALID."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[6] == MatchStatus.INVALID


def test_synthetic_unmatched_books():
    """Books row 7 (INV-9001, no counterpart) should be UNMATCHED_BOOKS."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[7] == MatchStatus.UNMATCHED_BOOKS


def test_synthetic_probable_match():
    """Books row 8 (INV-6001A vs INV-6001-B) should be PROBABLE."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)

    assert statuses[8] == MatchStatus.PROBABLE
    pairs = _matched_pairs(result)
    assert (8, 6) in pairs and pairs[(8, 6)] == MatchStatus.PROBABLE


def test_synthetic_unmatched_gstr2b():
    """GSTR-2B index 5 (INV-8001, no counterpart) should be UNMATCHED_GSTR2B."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)
    statuses = _gstr2b_statuses(result)

    assert statuses[5] == MatchStatus.UNMATCHED_GSTR2B


# ---------------------------------------------------------------------------
# One-to-one matching constraint
# ---------------------------------------------------------------------------


def test_one_to_one_no_record_matched_twice():
    """No purchase-register or GSTR-2B record may appear in more than one pair."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)

    book_rows = [
        m.purchase_record.source_row
        for m in result.matched_pairs
        if m.purchase_record is not None
    ]
    gstr_rows = [
        m.gstr2b_record.source_row
        for m in result.matched_pairs
        if m.gstr2b_record is not None
    ]
    assert len(book_rows) == len(set(book_rows)), "Book record matched twice"
    assert len(gstr_rows) == len(set(gstr_rows)), "GSTR-2B record matched twice"


def test_same_gstin_constraint():
    """Matches only occur between records sharing the same normalized GSTIN."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)

    for m in result.matched_pairs:
        b = m.purchase_record
        g = m.gstr2b_record
        assert b.gstin == g.gstin, "Match across different GSTINs"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_reconcile_is_deterministic():
    """Identical inputs must produce identical results across runs."""
    books, gstr2b = _load_normalized()
    first = reconcile(books, gstr2b)
    second = reconcile(books, gstr2b)

    assert first.summary == second.summary
    for m1, m2 in zip(first.matches, second.matches, strict=True):
        assert m1.match_status == m2.match_status
        assert m1.confidence == m2.confidence
        assert m1.reason == m2.reason


# ---------------------------------------------------------------------------
# Ground-truth precision/recall measurement
# ---------------------------------------------------------------------------


def test_ground_truth_precision_recall():
    """Measure precision and recall against synthetic ground truth.

    Confirmed matches (EXACT, AMOUNT_MISMATCH, TAX_HEAD_MISMATCH, FUZZY)
    are evaluated. PROBABLE matches are reported separately and are not
    counted as confirmed.

    Ground truth is defined independently of the matching implementation.
    """
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)

    # Ground truth: book row -> expected match status (confirmed statuses only).
    # PROBABLE (row 8) is evaluated separately.
    ground_truth_confirmed = {
        0: MatchStatus.EXACT,
        1: MatchStatus.EXACT,
        2: MatchStatus.FUZZY,
        3: MatchStatus.AMOUNT_MISMATCH,
        4: MatchStatus.TAX_HEAD_MISMATCH,
    }
    # Book rows expected to NOT have a confirmed match.
    ground_truth_no_match = {5, 6, 7}

    predicted = _book_statuses(result)

    confirmed_statuses = {
        MatchStatus.EXACT,
        MatchStatus.AMOUNT_MISMATCH,
        MatchStatus.TAX_HEAD_MISMATCH,
        MatchStatus.FUZZY,
    }

    true_positives = 0
    false_positives = 0
    false_negatives = 0

    for row, _expected in ground_truth_confirmed.items():
        actual = predicted.get(row)
        if actual in confirmed_statuses:
            # Verify the match is to the expected GSTR-2B record.
            actual_pair = None
            for m in result.matched_pairs:
                if (
                    m.purchase_record is not None
                    and m.purchase_record.source_row == row
                ):
                    actual_pair = m
                    break
            if (
                actual_pair is not None
                and actual_pair.gstr2b_record is not None
                and actual_pair.gstr2b_record.source_row == row
            ):
                true_positives += 1
            else:
                false_positives += 1  # matched to wrong record
        else:
            false_negatives += 1  # expected match but none predicted

    # False positives: predicted confirmed match where ground truth says no match.
    for row, actual in predicted.items():
        if row in ground_truth_no_match and actual in confirmed_statuses:
            false_positives += 1

    precision = (
        true_positives / (true_positives + false_positives)
        if (true_positives + false_positives) > 0
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if (true_positives + false_negatives) > 0
        else 0.0
    )

    probable_count = sum(
        1 for m in result.matches if m.match_status == MatchStatus.PROBABLE
    )

    # Store metrics for reporting.
    test_ground_truth_precision_recall.precision = precision
    test_ground_truth_precision_recall.recall = recall
    test_ground_truth_precision_recall.true_positives = true_positives
    test_ground_truth_precision_recall.false_positives = false_positives
    test_ground_truth_precision_recall.false_negatives = false_negatives
    test_ground_truth_precision_recall.probable_count = probable_count

    # 5 confirmed matches all correct: rows 0,1 (exact), 2 (fuzzy), 3 (amount), 4 (tax_head)
    assert true_positives == 5
    assert false_positives == 0
    assert false_negatives == 0
    assert precision == 1.0
    assert recall == 1.0
    assert probable_count == 1  # row 8


def test_ground_truth_metrics_reported(capsys):
    """Report matching metrics for the record.

    Acceptance thresholds for precision/recall are not defined in the
    documentation; measured values are reported without claiming a target.
    """
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)

    confirmed = [
        m
        for m in result.matched_pairs
        if m.match_status
        in (
            MatchStatus.EXACT,
            MatchStatus.AMOUNT_MISMATCH,
            MatchStatus.TAX_HEAD_MISMATCH,
            MatchStatus.FUZZY,
        )
    ]
    probable = [m for m in result.matches if m.match_status == MatchStatus.PROBABLE]

    print("\n--- Ground-truth matching metrics (synthetic data) ---")
    print(f"Confirmed matches: {len(confirmed)}")
    print(f"Probable matches: {len(probable)}")
    print(f"Unmatched books: {len(result.unmatched_books)}")
    print(f"Unmatched GSTR-2B: {len(result.unmatched_gstr2b)}")
    print(f"Duplicates: {len(result.duplicate_records)}")
    print(f"Invalid records: {len(result.invalid_records)}")
    print(f"Summary by status: {result.summary}")


# ---------------------------------------------------------------------------
# Edge cases with synthetic in-memory records
# ---------------------------------------------------------------------------


def _make_record(
    source_row,
    gstin,
    invoice_number,
    invoice_date="2024-04-15",
    taxable_value="1000.00",
    cgst="90.00",
    sgst="90.00",
    igst="0.00",
    cess="0.00",
    source_type=SourceType.PURCHASE_REGISTER,
    valid=True,
):
    g = normalize_gstin(gstin)
    inv = normalize_invoice_number(invoice_number)
    dt = normalize_date(invoice_date)
    tv = normalize_amount(taxable_value)
    c = normalize_amount(cgst)
    s = normalize_amount(sgst)
    i = normalize_amount(igst)
    ce = normalize_amount(cess)

    issues: list[ValidationIssue] = []
    status = ValidationStatus.VALID if valid else ValidationStatus.INVALID
    if not valid:
        issues.append(ValidationIssue("gstin", source_row, "invalid GSTIN", "error"))

    total_tax = None
    total_amount = None
    if tv is not None and all(x is not None for x in (c, s, i, ce)):
        total_tax = c + s + i + ce
        total_amount = tv + total_tax

    return NormalizedRecord(
        source_type=source_type,
        source_row=source_row,
        source_file="test.csv",
        gstin=g,
        invoice_number=inv,
        invoice_date=dt,
        taxable_value=tv,
        cgst=c,
        sgst=s,
        igst=i,
        cess=ce,
        total_tax=total_tax,
        total_amount=total_amount,
        validation_status=status,
        validation_issues=issues,
    )


def test_invalid_records_are_not_matched():
    """Invalid records must never participate in matching."""
    books = [
        _make_record(0, "29ABCDE1234F1Z5", "INV-1", valid=False),
        _make_record(1, "29ABCDE1234F1Z5", "INV-2"),
    ]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-2", source_type=SourceType.GSTR_2B
        ),
    ]
    result = reconcile(books, gstr2b)

    statuses = _book_statuses(result)
    assert statuses[0] == MatchStatus.INVALID
    assert statuses[1] == MatchStatus.EXACT


def test_empty_inputs_produce_no_matches():
    """Empty input lists produce an empty reconciliation result."""
    result = reconcile([], [])
    assert len(result.matches) == 0
    assert result.summary == {}


def test_all_unmatched_when_no_gstin_overlap():
    """When no GSTINs overlap, all records are unmatched."""
    books = [_make_record(0, "29ABCDE1234F1Z5", "INV-1")]
    gstr2b = [
        _make_record(
            0, "07FGHIJ5678K1Z6", "INV-1", source_type=SourceType.GSTR_2B
        ),
    ]
    result = reconcile(books, gstr2b)

    assert len(result.matches) == 2
    assert all(
        m.match_status
        in (MatchStatus.UNMATCHED_BOOKS, MatchStatus.UNMATCHED_GSTR2B)
        for m in result.matches
    )


def test_low_confidence_threshold_downgrade():
    """Matches below low_confidence_threshold are downgraded to LOW_CONFIDENCE."""
    settings = ReconciliationSettings(
        fuzzy_threshold=50.0,
        probable_threshold=40.0,
        low_confidence_threshold=0.90,
    )
    books = [_make_record(0, "29ABCDE1234F1Z5", "INV-1")]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-XYZ", source_type=SourceType.GSTR_2B
        ),
    ]
    result = reconcile(books, gstr2b, settings=settings)

    matched = [
        m
        for m in result.matches
        if m.match_status in (MatchStatus.PROBABLE, MatchStatus.LOW_CONFIDENCE)
    ]
    assert len(matched) >= 1

    # Any match below 0.90 confidence must be LOW_CONFIDENCE.
    for m in result.matches:
        if m.match_status in (
            MatchStatus.PROBABLE,
            MatchStatus.LOW_CONFIDENCE,
        ):
            if m.confidence < 0.90:
                assert m.match_status == MatchStatus.LOW_CONFIDENCE


def test_conflicting_candidates_one_to_one():
    """When one book invoice could match multiple GSTR-2B invoices, only the
    best (highest-confidence) match is chosen; the other GSTR-2B invoice is
    unmatched."""
    books = [
        _make_record(0, "29ABCDE1234F1Z5", "INV-100"),
    ]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-100", source_type=SourceType.GSTR_2B
        ),
        _make_record(
            1, "29ABCDE1234F1Z5", "INV-101", source_type=SourceType.GSTR_2B
        ),
    ]
    result = reconcile(books, gstr2b)

    matched_pairs = result.matched_pairs
    assert len(matched_pairs) == 1  # only one book record, one match
    # The GSTR-2B record not matched should be UNMATCHED_GSTR2B
    unmatched = result.unmatched_gstr2b
    assert len(unmatched) == 1


def test_competing_candidates_deterministic_winner():
    """When two book invoices compete for one GSTR-2B invoice, the
    higher-priority match (exact over amount mismatch) wins deterministically,
    regardless of candidate generation order."""
    books = [
        _make_record(0, "29ABCDE1234F1Z5", "INV-100", taxable_value="1000.00"),
        _make_record(1, "29ABCDE1234F1Z5", "INV-100", taxable_value="2000.00"),
    ]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-100", taxable_value="1000.00",
            source_type=SourceType.GSTR_2B,
        ),
    ]
    result = reconcile(books, gstr2b)

    # Book 0 (exact match on amount) wins over book 1 (amount mismatch).
    # Book 1 shares GSTIN+invoice_number with book 0, so it is DUPLICATE
    # (duplicate detection runs before matching).
    pairs = _matched_pairs(result)
    assert (0, 0) in pairs and pairs[(0, 0)] == MatchStatus.EXACT
    statuses = _book_statuses(result)
    assert statuses[1] == MatchStatus.DUPLICATE


def test_probable_matches_different_cores_is_uncertain():
    """Probable matching is similarity-based and does not require the same
    invoice core, so it can match clearly different invoice numbers. Such
    matches are uncertain and should be treated as needing review."""
    books = [
        _make_record(0, "29ABCDE1234F1Z5", "INV-1000A"),
    ]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-1000B", source_type=SourceType.GSTR_2B
        ),
    ]
    # "INV-1000A" vs "INV-1000B" have different cores ("INV1000A" vs
    # "INV1000B") but very high rapidfuzz similarity. This is PROBABLE at
    # best, not a confirmed match.
    result = reconcile(books, gstr2b)
    statuses = _book_statuses(result)
    assert statuses[0] == MatchStatus.PROBABLE


def test_gstr2b_duplicate_not_flagged_scope_boundary():
    """Duplicate detection is defined for the purchase register only
    (phases.md Phase 2). A duplicate GSTR-2B invoice is not flagged as
    DUPLICATE; it is matched or unmatched like any other record. This is a
    documented scope boundary, not a defect."""
    books = [
        _make_record(0, "29ABCDE1234F1Z5", "INV-100"),
    ]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-100", source_type=SourceType.GSTR_2B
        ),
        _make_record(
            1, "29ABCDE1234F1Z5", "INV-100", source_type=SourceType.GSTR_2B
        ),
    ]
    result = reconcile(books, gstr2b)

    # One GSTR-2B matches exactly; the other is UNMATCHED_GSTR2B (not DUPLICATE).
    statuses = _gstr2b_statuses(result)
    status_values = set(statuses.values())
    assert MatchStatus.DUPLICATE not in status_values
    assert MatchStatus.UNMATCHED_GSTR2B in status_values


def test_match_result_has_traceable_source_records():
    """Every matched pair carries references to both source records and a
    human-readable reason."""
    books, gstr2b = _load_normalized()
    result = reconcile(books, gstr2b)

    for m in result.matched_pairs:
        assert m.purchase_record is not None
        assert m.gstr2b_record is not None
        assert m.reason  # non-empty explanation
        assert m.purchase_record.source_file
        assert m.gstr2b_record.source_file


def test_amount_difference_populated_on_mismatch():
    """amount_difference records books taxable_value minus 2B taxable_value
    for amount-mismatch pairs."""
    books = [
        _make_record(0, "29ABCDE1234F1Z5", "INV-100", taxable_value="1000.00"),
    ]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-100", taxable_value="800.00",
            source_type=SourceType.GSTR_2B,
        ),
    ]
    result = reconcile(books, gstr2b)

    pairs = _matched_pairs(result)
    assert (0, 0) in pairs and pairs[(0, 0)] == MatchStatus.AMOUNT_MISMATCH
    for m in result.matched_pairs:
        if m.match_status == MatchStatus.AMOUNT_MISMATCH:
            assert m.amount_difference == Decimal("200.00")


def test_date_discrepancy_recorded():
    """A differing invoice date is listed in discrepancies."""
    books = [
        _make_record(0, "29ABCDE1234F1Z5", "INV-100", invoice_date="2024-04-15"),
    ]
    gstr2b = [
        _make_record(
            0, "29ABCDE1234F1Z5", "INV-100", invoice_date="2024-04-16",
            source_type=SourceType.GSTR_2B,
        ),
    ]
    result = reconcile(books, gstr2b)

    pairs = _matched_pairs(result)
    assert (0, 0) in pairs and pairs[(0, 0)] == MatchStatus.AMOUNT_MISMATCH
    for m in result.matched_pairs:
        assert "invoice_date" in m.discrepancies

"""Tests for the decision support module (src/itc_sentinel/decision.py).

Covers suggested action, exposure, priority, flags, reason, reason code,
review requirement, and eligibility status for every match status.

Key assertions:
- Matching status, eligibility status, and operational action are distinct.
- All match statuses map to eligibility_status UNCERTAIN (except
  UNMATCHED_GSTR2B which is NOT_ASSESSED); matching is not proof of ITC
  eligibility.
- Decisions are deterministic and traceable to source records.
- No external action fields exist (no filing, payment holds, vendor messages).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from itc_sentinel.decision import (
    Action,
    DecisionResult,
    DecisionSettings,
    EligibilityStatus,
    Flag,
    Priority,
    ReasonCode,
    decide,
    decide_all,
    total_exposure,
)
from itc_sentinel.matcher import MatchResult, MatchStatus
from itc_sentinel.schemas import (
    NormalizedRecord,
    SourceType,
    ValidationStatus,
)

# ---------------------------------------------------------------------------
# Helpers
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
    from itc_sentinel.normalize import (
        normalize_amount,
        normalize_date,
        normalize_gstin,
        normalize_invoice_number,
    )
    from itc_sentinel.schemas import ValidationIssue

    g = normalize_gstin(gstin)
    inv = normalize_invoice_number(invoice_number)
    dt = normalize_date(invoice_date)
    tv = normalize_amount(taxable_value)
    c = normalize_amount(cgst)
    s = normalize_amount(sgst)
    i = normalize_amount(igst)
    ce = normalize_amount(cess)

    issues = []
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


def _make_match(
    source_row,
    match_status,
    book_taxable_value="1000.00",
    gstr2b_taxable_value=None,
    confidence=1.0,
    valid=True,
):
    book = _make_record(
        source_row, "29ABCDE1234F1Z5", f"INV-{source_row}",
        taxable_value=book_taxable_value, valid=valid,
    )
    gstr2b = None
    amount_difference = None
    if match_status in (
        MatchStatus.EXACT,
        MatchStatus.AMOUNT_MISMATCH,
        MatchStatus.TAX_HEAD_MISMATCH,
        MatchStatus.FUZZY,
        MatchStatus.PROBABLE,
        MatchStatus.LOW_CONFIDENCE,
    ):
        gstr2b = _make_record(
            source_row, "29ABCDE1234F1Z5", f"INV-{source_row}",
            taxable_value=gstr2b_taxable_value or book_taxable_value,
            source_type=SourceType.GSTR_2B,
        )
        if book.taxable_value is not None and gstr2b.taxable_value is not None:
            amount_difference = (
                book.taxable_value - gstr2b.taxable_value
            )
    return MatchResult(
        purchase_record=book,
        gstr2b_record=gstr2b,
        match_status=match_status,
        confidence=confidence,
        reason="test reason",
        amount_difference=amount_difference,
    )


def _assert_decision_fields(decision: DecisionResult):
    """Every decision must have stable, traceable fields."""
    assert isinstance(decision, DecisionResult)
    assert decision.reason  # non-empty explanation
    assert decision.reason_code  # stable reason code
    assert isinstance(decision.action, Action)
    assert isinstance(decision.priority, Priority)
    assert isinstance(decision.flags, list)
    assert isinstance(decision.review_required, bool)
    assert isinstance(decision.eligibility_status, EligibilityStatus)
    assert isinstance(decision.rule_sources_applied, list)
    assert decision.exposure_amount is not None
    # Traceable source records (at least one side must carry source_file).
    purchase = decision.match_result.purchase_record
    gstr = decision.match_result.gstr2b_record
    if purchase is not None:
        assert purchase.source_file
    if gstr is not None:
        assert gstr.source_file


# ---------------------------------------------------------------------------
# Per-status decisions
# ---------------------------------------------------------------------------


def test_decide_exact_match():
    match = _make_match(0, MatchStatus.EXACT)
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.CLAIM_ITC
    assert decision.priority == Priority.LOW
    assert decision.flags == []
    assert decision.reason_code == ReasonCode.EXACT_MATCH
    assert decision.exposure_amount == Decimal("0")
    assert decision.review_required is False
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN
    assert "R-MATCH-EXACT" in decision.rule_sources_applied
    assert "R-ITC-ELIGIBILITY" in decision.rule_sources_applied


def test_decide_amount_mismatch():
    match = _make_match(0, MatchStatus.AMOUNT_MISMATCH, book_taxable_value="6000.00",
                        gstr2b_taxable_value="5500.00")
    # Custom settings: exposure 500 >= 400 high threshold → HIGH priority.
    settings = DecisionSettings(
        high_exposure_threshold=Decimal("400.00"),
        medium_exposure_threshold=Decimal("100.00"),
    )
    decision = decide(match, decision_settings=settings)
    _assert_decision_fields(decision)
    assert decision.action == Action.REQUEST_CLARIFICATION
    assert decision.priority == Priority.HIGH
    assert Flag.AMOUNT_MISMATCH in decision.flags
    assert decision.reason_code == ReasonCode.AMOUNT_MISMATCH
    assert decision.exposure_amount == Decimal("500.00")
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


def test_decide_tax_head_mismatch():
    match = _make_match(0, MatchStatus.TAX_HEAD_MISMATCH,
                        book_taxable_value="4000.00",
                        gstr2b_taxable_value="4000.00")
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.FLAG_FOR_REVIEW
    assert decision.priority == Priority.HIGH
    assert Flag.TAX_HEAD_MISMATCH in decision.flags
    assert decision.reason_code == ReasonCode.TAX_HEAD_MISMATCH
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


def test_decide_fuzzy_match():
    match = _make_match(0, MatchStatus.FUZZY, confidence=0.88)
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.REQUEST_CLARIFICATION
    assert decision.priority == Priority.MEDIUM
    assert Flag.FUZZY_MATCH in decision.flags
    assert decision.reason_code == ReasonCode.FUZZY_MATCH
    assert decision.exposure_amount == Decimal("0")
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


def test_decide_probable_match():
    match = _make_match(0, MatchStatus.PROBABLE, confidence=0.84)
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.FLAG_FOR_REVIEW
    assert decision.priority == Priority.MEDIUM
    assert Flag.PROBABLE_MATCH in decision.flags
    assert decision.reason_code == ReasonCode.PROBABLE_MATCH
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


def test_decide_low_confidence():
    match = _make_match(0, MatchStatus.LOW_CONFIDENCE, confidence=0.5)
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.FLAG_FOR_REVIEW
    assert decision.priority == Priority.MEDIUM
    assert Flag.LOW_CONFIDENCE_MATCH in decision.flags
    assert decision.reason_code == ReasonCode.LOW_CONFIDENCE_MATCH
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


def test_decide_unmatched_books():
    match = _make_match(0, MatchStatus.UNMATCHED_BOOKS,
                        book_taxable_value="3000.00")
    # Override tax components so total_amount == taxable_value (3000.00).
    match.purchase_record.cgst = Decimal("0")
    match.purchase_record.sgst = Decimal("0")
    match.purchase_record.igst = Decimal("0")
    match.purchase_record.cess = Decimal("0")
    match.purchase_record.total_tax = Decimal("0")
    match.purchase_record.total_amount = Decimal("3000.00")
    # Custom settings: exposure 3000 >= 2000 high threshold → HIGH priority.
    settings = DecisionSettings(
        high_exposure_threshold=Decimal("2000.00"),
        medium_exposure_threshold=Decimal("1000.00"),
    )
    decision = decide(match, decision_settings=settings)
    _assert_decision_fields(decision)
    assert decision.action == Action.FLAG_FOR_REVIEW
    assert decision.priority == Priority.HIGH
    assert Flag.MISSING_IN_2B in decision.flags
    assert decision.reason_code == ReasonCode.UNMATCHED_BOOKS
    assert decision.exposure_amount == Decimal("3000.00")
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


def test_decide_unmatched_gstr2b():
    gstr2b = _make_record(
        0, "29ABCDE1234F1Z5", "INV-0", source_type=SourceType.GSTR_2B,
    )
    match = MatchResult(
        purchase_record=None,
        gstr2b_record=gstr2b,
        match_status=MatchStatus.UNMATCHED_GSTR2B,
        confidence=0.0,
        reason="test",
    )
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.NO_ACTION
    assert decision.priority == Priority.LOW
    assert decision.flags == []
    assert decision.reason_code == ReasonCode.UNMATCHED_GSTR2B
    assert decision.exposure_amount == Decimal("0")
    assert decision.review_required is False
    assert decision.eligibility_status == EligibilityStatus.NOT_ASSESSED


def test_decide_duplicate():
    match = _make_match(0, MatchStatus.DUPLICATE,
                        book_taxable_value="1000.00")
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.FLAG_FOR_REVIEW
    assert decision.priority == Priority.HIGH
    assert Flag.DUPLICATE in decision.flags
    assert decision.reason_code == ReasonCode.DUPLICATE
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


def test_decide_invalid():
    match = _make_match(0, MatchStatus.INVALID, valid=False)
    decision = decide(match)
    _assert_decision_fields(decision)
    assert decision.action == Action.FLAG_FOR_REVIEW
    assert decision.priority == Priority.HIGH
    assert Flag.INVALID_DATA in decision.flags
    assert decision.reason_code == ReasonCode.INVALID_DATA
    assert decision.exposure_amount == Decimal("0")
    assert decision.review_required is True
    assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


# ---------------------------------------------------------------------------
# Distinctness: eligibility vs match status vs action
# ---------------------------------------------------------------------------


def test_eligibility_never_equals_match_status():
    """Eligibility status must not be derived directly from match status."""
    for status in MatchStatus:
        match = _make_match(0, status)
        decision = decide(match)
        # Matching is not proof of eligibility: all statuses are UNCERTAIN
        # except UNMATCHED_GSTR2B which is NOT_ASSESSED.
        if status == MatchStatus.UNMATCHED_GSTR2B:
            assert decision.eligibility_status == EligibilityStatus.NOT_ASSESSED
        else:
            assert decision.eligibility_status == EligibilityStatus.UNCERTAIN


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_decide_is_deterministic():
    match = _make_match(0, MatchStatus.AMOUNT_MISMATCH,
                        book_taxable_value="6000.00",
                        gstr2b_taxable_value="5500.00")
    first = decide(match)
    second = decide(match)
    assert first.action == second.action
    assert first.priority == second.priority
    assert first.exposure_amount == second.exposure_amount
    assert first.reason == second.reason
    assert first.reason_code == second.reason_code
    assert first.review_required == second.review_required


# ---------------------------------------------------------------------------
# decide_all and total_exposure
# ---------------------------------------------------------------------------


def test_decide_all_with_reconciliation_result():
    from itc_sentinel.matcher import ReconciliationResult
    matches = [
        _make_match(0, MatchStatus.EXACT),
        _make_match(1, MatchStatus.AMOUNT_MISMATCH,
                    book_taxable_value="6000.00",
                    gstr2b_taxable_value="5500.00"),
    ]
    result = ReconciliationResult(matches=matches)
    decisions = decide_all(result)
    assert len(decisions) == 2
    assert decisions[0].reason_code == ReasonCode.EXACT_MATCH
    assert decisions[1].reason_code == ReasonCode.AMOUNT_MISMATCH


def test_decide_all_with_iterable():
    matches = [
        _make_match(0, MatchStatus.EXACT),
        _make_match(1, MatchStatus.INVALID, valid=False),
    ]
    decisions = decide_all(matches)
    assert len(decisions) == 2


def test_total_exposure_sums_without_double_counting():
    d1 = DecisionResult(
        match_result=_make_match(0, MatchStatus.EXACT),
        action=Action.CLAIM_ITC,
        priority=Priority.LOW,
        exposure_amount=Decimal("0"),
    )
    d2 = DecisionResult(
        match_result=_make_match(1, MatchStatus.AMOUNT_MISMATCH,
                                 book_taxable_value="6000.00",
                                 gstr2b_taxable_value="5500.00"),
        action=Action.REQUEST_CLARIFICATION,
        priority=Priority.HIGH,
        exposure_amount=Decimal("500.00"),
    )
    d3 = DecisionResult(
        match_result=_make_match(2, MatchStatus.UNMATCHED_BOOKS,
                                 book_taxable_value="3000.00"),
        action=Action.FLAG_FOR_REVIEW,
        priority=Priority.HIGH,
        exposure_amount=Decimal("3000.00"),
    )
    total = total_exposure([d1, d2, d3])
    assert total == Decimal("3500.00")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_decide_unknown_status_raises():
    match = _make_match(0, MatchStatus.EXACT)
    # Temporarily corrupt the status to test error handling.
    match.match_status = "not-a-status"  # type: ignore[assignment]
    with pytest.raises(ValueError):
        decide(match)


def test_decide_missing_tax_values_safe():
    """Decisions must not crash when tax values are missing."""
    book = _make_record(0, "29ABCDE1234F1Z5", "INV-0",
                        taxable_value=None, cgst=None, sgst=None,
                        igst=None, cess=None)
    match = MatchResult(
        purchase_record=book,
        gstr2b_record=None,
        match_status=MatchStatus.UNMATCHED_BOOKS,
        confidence=0.0,
        reason="test",
    )
    decision = decide(match)
    assert decision.review_required is True
    assert decision.exposure_amount == Decimal("0")

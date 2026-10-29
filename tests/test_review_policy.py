"""Tests for the human-review action policy (src/itc_sentinel/decision.py).

Prohibited actions must be rejected by the decision layer, not merely hidden
in the Streamlit UI.
"""

from __future__ import annotations

import pytest

from itc_sentinel.decision import (
    REVIEW_DECISIONS,
    allowed_review_decisions,
    decide,
    validate_review_decision,
)
from itc_sentinel.matcher import MatchResult, MatchStatus
from itc_sentinel.normalize import (
    normalize_amount,
    normalize_date,
    normalize_gstin,
    normalize_invoice_number,
)
from itc_sentinel.schemas import (
    NormalizedRecord,
    SourceType,
    ValidationIssue,
    ValidationStatus,
)


def _record(
    source_row=0,
    gstin="29ABCDE1234F1Z5",
    invoice="INV-1",
    source_type=SourceType.PURCHASE_REGISTER,
    valid=True,
):
    issues = [] if valid else [ValidationIssue("gstin", source_row, "bad", "error")]
    return NormalizedRecord(
        source_type=source_type,
        source_row=source_row,
        source_file="test.csv",
        gstin=normalize_gstin(gstin),
        invoice_number=normalize_invoice_number(invoice),
        invoice_date=normalize_date("2024-04-15"),
        taxable_value=normalize_amount("1000.00"),
        cgst=normalize_amount("90.00"),
        sgst=normalize_amount("90.00"),
        igst=normalize_amount("0.00"),
        cess=normalize_amount("0.00"),
        total_tax=normalize_amount("180.00"),
        total_amount=normalize_amount("1180.00"),
        validation_status=ValidationStatus.VALID if valid else ValidationStatus.INVALID,
        validation_issues=issues,
    )


def _match(status: MatchStatus, valid=True):
    book = _record(valid=valid)
    gstr2b = None
    if status in {
        MatchStatus.EXACT,
        MatchStatus.AMOUNT_MISMATCH,
        MatchStatus.TAX_HEAD_MISMATCH,
        MatchStatus.FUZZY,
        MatchStatus.PROBABLE,
        MatchStatus.LOW_CONFIDENCE,
    }:
        gstr2b = _record(source_type=SourceType.GSTR_2B, valid=valid)
    return MatchResult(
        purchase_record=book,
        gstr2b_record=gstr2b,
        match_status=status,
        confidence=1.0,
        reason="test",
    )


def test_every_reviewable_status_exposes_only_known_actions():
    for status in MatchStatus:
        decision = decide(_match(status))
        for action in allowed_review_decisions(decision):
            assert action in REVIEW_DECISIONS


def test_invalid_rows_cannot_be_approved():
    decision = decide(_match(MatchStatus.INVALID, valid=False))
    allowed = allowed_review_decisions(decision)

    assert "approve" not in allowed
    assert allowed == ("reject", "pending")
    with pytest.raises(ValueError, match="not permitted"):
        validate_review_decision(decision, "approve")
    assert validate_review_decision(decision, "reject") == "reject"
    assert validate_review_decision(decision, "pending") == "pending"


def test_exact_match_is_reviewable_and_has_no_special_bypass():
    decision = decide(_match(MatchStatus.EXACT))

    assert decision.review_required is True
    assert allowed_review_decisions(decision) == REVIEW_DECISIONS
    assert validate_review_decision(decision, "approve") == "approve"


def test_non_review_required_record_rejects_review_actions():
    decision = decide(_match(MatchStatus.UNMATCHED_GSTR2B))

    assert decision.review_required is False
    with pytest.raises(ValueError, match="does not require"):
        validate_review_decision(decision, "approve")


def test_unknown_action_rejected():
    decision = decide(_match(MatchStatus.EXACT))
    with pytest.raises(ValueError, match="Unknown review decision"):
        validate_review_decision(decision, "delete_everything")


def test_action_normalisation():
    decision = decide(_match(MatchStatus.AMOUNT_MISMATCH))
    assert validate_review_decision(decision, "  APPROVE ") == "approve"


def test_non_string_action_rejected():
    decision = decide(_match(MatchStatus.EXACT))
    with pytest.raises(ValueError, match="must be a string"):
        validate_review_decision(decision, 123)  # type: ignore[arg-type]


def test_every_review_required_status_accepts_all_allowed_actions():
    for status in MatchStatus:
        decision = decide(_match(status))
        if not decision.review_required:
            continue
        for action in allowed_review_decisions(decision):
            assert validate_review_decision(decision, action) == action

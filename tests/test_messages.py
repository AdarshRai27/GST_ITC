"""Tests for the messages module (src/itc_sentinel/messages.py).

Covers deterministic vendor message draft generation for all supported
discrepancy categories, traceable source values, neutral wording, and
LLM-enhanced vs template fallback behavior.
"""

from __future__ import annotations

import pytest

from itc_sentinel.matcher import MatchResult, MatchStatus
from itc_sentinel.messages import (
    DraftCategory,
    VendorDraft,
    draft_vendor_message,
)
from itc_sentinel.schemas import NormalizedRecord, SourceType, ValidationStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_normalized_record(
    source_row,
    gstin,
    invoice_number,
    source_type=SourceType.PURCHASE_REGISTER,
    taxable_value="1000.00",
    cgst="90.00",
    sgst="90.00",
    igst="0.00",
    cess="0.00",
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
    dt = normalize_date("2024-04-15")
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
        vendor_name="Acme Supplies",
    )


def _make_match_result(source_row, match_status, valid=True):
    book = _make_normalized_record(
        source_row, "29ABCDE1234F1Z5", f"INV-{source_row}", valid=valid
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
        gstr2b = _make_normalized_record(
            source_row,
            "29ABCDE1234F1Z5",
            f"INV-{source_row}",
            source_type=SourceType.GSTR_2B,
        )
        if book.taxable_value is not None and gstr2b.taxable_value is not None:
            amount_difference = book.taxable_value - gstr2b.taxable_value
    return MatchResult(
        purchase_record=book,
        gstr2b_record=gstr2b,
        match_status=match_status,
        confidence=1.0,
        reason="test reason",
        amount_difference=amount_difference,
    )


def _make_decision(match_status, valid=True, action=None, reason_code=None,
                   priority=None, exposure_amount=None, review_required=None,
                   eligibility_status=None):
    match = _make_match_result(source_row=0, match_status=match_status, valid=valid)
    from itc_sentinel.decision import decide
    return decide(match)


# ---------------------------------------------------------------------------
# Draft generation per category
# ---------------------------------------------------------------------------


def test_draft_amount_mismatch():
    decision = _make_decision(MatchStatus.AMOUNT_MISMATCH)
    draft = draft_vendor_message(decision)
    assert isinstance(draft, VendorDraft)
    assert draft.category == DraftCategory.AMOUNT_MISMATCH.value
    assert draft.editable is True
    assert draft.llm_enhanced is False
    assert "INV-0" in draft.subject or "INV-0" in draft.body_email
    assert "clarification" in draft.body_email.lower()
    assert "ITC eligibility" in draft.body_email
    assert draft.body_whatsapp != ""


def test_draft_tax_head_mismatch():
    decision = _make_decision(MatchStatus.TAX_HEAD_MISMATCH)
    draft = draft_vendor_message(decision)
    assert draft.category == DraftCategory.TAX_HEAD_MISMATCH.value
    assert "tax head" in draft.body_email.lower()
    assert "ITC eligibility" in draft.body_email


def test_draft_missing_in_2b():
    decision = _make_decision(MatchStatus.UNMATCHED_BOOKS)
    draft = draft_vendor_message(decision)
    assert draft.category == DraftCategory.MISSING_IN_2B.value
    assert "not found" in draft.body_email.lower() or "GSTR-2B" in draft.body_email


def test_draft_duplicate():
    decision = _make_decision(MatchStatus.DUPLICATE)
    draft = draft_vendor_message(decision)
    assert draft.category == DraftCategory.DUPLICATE.value
    assert "duplicate" in draft.body_email.lower()


def test_draft_invalid_data():
    decision = _make_decision(MatchStatus.INVALID, valid=False)
    draft = draft_vendor_message(decision)
    assert draft.category == DraftCategory.INVALID_DATA.value
    assert "invalid" in draft.body_email.lower()


def test_draft_low_confidence():
    decision = _make_decision(MatchStatus.LOW_CONFIDENCE)
    draft = draft_vendor_message(decision)
    assert draft.category == DraftCategory.LOW_CONFIDENCE.value
    assert "confirm" in draft.body_email.lower()


# ---------------------------------------------------------------------------
# Neutral wording / no accusations
# ---------------------------------------------------------------------------


def test_drafts_are_neutral_no_legal_claims():
    """Drafts must not make definitive ITC eligibility claims or accusations."""
    for status in (
        MatchStatus.AMOUNT_MISMATCH,
        MatchStatus.TAX_HEAD_MISMATCH,
        MatchStatus.UNMATCHED_BOOKS,
        MatchStatus.DUPLICATE,
        MatchStatus.INVALID,
        MatchStatus.LOW_CONFIDENCE,
    ):
        decision = _make_decision(status)
        draft = draft_vendor_message(decision)
        combined = (draft.subject + " " + draft.body_email + " " +
                    draft.body_whatsapp).lower()
        # No definitive eligibility claims
        assert "itc eligible" not in combined
        assert "itc ineligible" not in combined
        assert "you owe" not in combined
        assert "you must pay" not in combined
        # Contains neutral clarification/review language
        has_neutral = (
            "clarification" in combined
            or "confirm" in combined
            or "review" in combined
        )
        assert has_neutral, f"No neutral language in {status}: {combined}"


def test_drafts_preserve_source_values():
    """Drafts include traceable source values and do not invent data."""
    decision = _make_decision(MatchStatus.AMOUNT_MISMATCH)
    draft = draft_vendor_message(decision)
    assert draft.invoice_key is not None
    assert "29ABCDE1234F1Z5" in draft.invoice_key
    assert "INV-0" in draft.invoice_key
    assert isinstance(draft.source_values, dict)


# ---------------------------------------------------------------------------
# Explicit category parameter
# ---------------------------------------------------------------------------


def test_draft_with_explicit_category():
    decision = _make_decision(MatchStatus.EXACT)
    # EXACT has no supported draft category -> should raise
    from itc_sentinel.messages import _decision_to_category
    assert _decision_to_category(decision) is None
    with pytest.raises(ValueError, match="No supported draft category"):
        draft_vendor_message(decision)

    # But explicit category overrides
    draft = draft_vendor_message(decision, category=DraftCategory.DUPLICATE)
    assert draft.category == DraftCategory.DUPLICATE.value


# ---------------------------------------------------------------------------
# LLM enhanced flag
# ---------------------------------------------------------------------------


def test_draft_llm_enhanced_flag():
    decision = _make_decision(MatchStatus.AMOUNT_MISMATCH)
    draft = draft_vendor_message(decision, enhanced_by_llm=True)
    assert draft.llm_enhanced is True
    assert draft.category == DraftCategory.AMOUNT_MISMATCH.value

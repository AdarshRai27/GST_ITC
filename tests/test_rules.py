"""Tests for the rule calculations module (src/itc_sentinel/rules.py).

Covers mechanical reconciliation calculations (amount difference, tax
exposure, taxable exposure) and rule-source documentation. All calculations
use Decimal and the documented rounding policy.

No GST ITC eligibility is determined here — eligibility is a tax/legal matter
requiring CA review.
"""

from __future__ import annotations

from decimal import Decimal

from itc_sentinel.matcher import MatchResult
from itc_sentinel.rules import (
    calculate_amount_difference,
    calculate_tax_exposure,
    calculate_taxable_exposure,
    rule_sources,
)
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


def _make_match_result(
    source_row,
    gstin,
    invoice_number,
    match_status,
    gstr2b_gstin=None,
    gstr2b_invoice_number=None,
    gstr2b_taxable_value=None,
    confidence=1.0,
    valid=True,
):
    book = _make_record(
        source_row,
        gstin,
        invoice_number,
        source_type=SourceType.PURCHASE_REGISTER,
        valid=valid,
    )
    gstr2b = None
    if gstr2b_gstin is not None:
        gstr2b = _make_record(
            source_row,
            gstr2b_gstin,
            gstr2b_invoice_number,
            taxable_value=gstr2b_taxable_value or "1000.00",
            source_type=SourceType.GSTR_2B,
            valid=True,
        )
    return MatchResult(
        purchase_record=book,
        gstr2b_record=gstr2b,
        match_status=match_status,
        confidence=confidence,
        reason="test reason",
    )


# ---------------------------------------------------------------------------
# calculate_amount_difference
# ---------------------------------------------------------------------------


def test_calculate_amount_difference_exact():
    book = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value="5000.00")
    gstr2b = _make_record(
        0, "29ABCDE1234F1Z5", "INV-1", taxable_value="5000.00",
        source_type=SourceType.GSTR_2B,
    )
    result = calculate_amount_difference(book, gstr2b)
    assert result == Decimal("0.00")


def test_calculate_amount_difference_nonzero():
    book = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value="6000.00")
    gstr2b = _make_record(
        0, "29ABCDE1234F1Z5", "INV-1", taxable_value="5500.00",
        source_type=SourceType.GSTR_2B,
    )
    result = calculate_amount_difference(book, gstr2b)
    assert result == Decimal("500.00")


def test_calculate_amount_difference_negative():
    book = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value="5000.00")
    gstr2b = _make_record(
        0, "29ABCDE1234F1Z5", "INV-1", taxable_value="7000.00",
        source_type=SourceType.GSTR_2B,
    )
    result = calculate_amount_difference(book, gstr2b)
    assert result == Decimal("-2000.00")


def test_calculate_amount_difference_missing_book():
    gstr2b = _make_record(
        0, "29ABCDE1234F1Z5", "INV-1", source_type=SourceType.GSTR_2B,
    )
    assert calculate_amount_difference(None, gstr2b) is None


def test_calculate_amount_difference_missing_gstr2b():
    book = _make_record(0, "29ABCDE1234F1Z5", "INV-1")
    assert calculate_amount_difference(book, None) is None


def test_calculate_amount_difference_missing_taxable_value():
    book = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value=None)
    gstr2b = _make_record(
        0, "29ABCDE1234F1Z5", "INV-1", taxable_value="5000.00",
        source_type=SourceType.GSTR_2B,
    )
    assert calculate_amount_difference(book, gstr2b) is None


def test_calculate_amount_difference_rounding():
    # 0.005 rounds to 0.01 under ROUND_HALF_UP
    book = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value="0.005")
    gstr2b = _make_record(
        0, "29ABCDE1234F1Z5", "INV-1", taxable_value="0.000",
        source_type=SourceType.GSTR_2B,
    )
    result = calculate_amount_difference(book, gstr2b)
    assert result == Decimal("0.01")


# ---------------------------------------------------------------------------
# calculate_tax_exposure
# ---------------------------------------------------------------------------


def test_calculate_tax_exposure_sums_total_tax():
    r1 = _make_record(0, "29ABCDE1234F1Z5", "INV-1", cgst="100.00", sgst="100.00",
                      igst="0.00", cess="0.00")
    r2 = _make_record(1, "07FGHIJ5678K1Z6", "INV-2", igst="200.00",
                      cgst="0.00", sgst="0.00", cess="0.00")
    result = calculate_tax_exposure([r1, r2])
    assert result == Decimal("400.00")


def test_calculate_tax_exposure_missing_total_tax_contributes_zero():
    r1 = _make_record(0, "29ABCDE1234F1Z5", "INV-1", cgst=None, sgst=None)
    # r1 has no total_tax because components are None
    result = calculate_tax_exposure([r1])
    assert result == Decimal("0.00")


def test_calculate_tax_exposure_empty_list():
    assert calculate_tax_exposure([]) == Decimal("0.00")


# ---------------------------------------------------------------------------
# calculate_taxable_exposure
# ---------------------------------------------------------------------------


def test_calculate_taxable_exposure_sums_taxable_value():
    r1 = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value="1000.00")
    r2 = _make_record(1, "07FGHIJ5678K1Z6", "INV-2", taxable_value="2500.50")
    result = calculate_taxable_exposure([r1, r2])
    assert result == Decimal("3500.50")


def test_calculate_taxable_exposure_missing_contributes_zero():
    r1 = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value=None)
    result = calculate_taxable_exposure([r1])
    assert result == Decimal("0.00")


def test_calculate_taxable_exposure_empty_list():
    assert calculate_taxable_exposure([]) == Decimal("0.00")


# ---------------------------------------------------------------------------
# Rule sources / documentation
# ---------------------------------------------------------------------------


def test_rule_sources_returned():
    sources = rule_sources()
    assert len(sources) > 0
    ids = {s.rule_id for s in sources}
    assert "R-CALC-AMOUNT-DIFF" in ids
    assert "R-CALC-TAX-EXPOSURE" in ids
    assert "R-CALC-TAXABLE-EXPOSURE" in ids
    assert "R-ITC-ELIGIBILITY" in ids


def test_rule_sources_label_ca_verification():
    sources = {s.rule_id: s for s in rule_sources()}
    # Mechanical calculation rules do not require CA verification.
    assert sources["R-CALC-AMOUNT-DIFF"].ca_verification_required is False
    assert sources["R-MATCH-EXACT"].ca_verification_required is False
    # Exposure / eligibility rules require CA verification.
    assert sources["R-CALC-TAX-EXPOSURE"].ca_verification_required is True
    assert sources["R-CALC-TAXABLE-EXPOSURE"].ca_verification_required is True
    assert sources["R-ITC-ELIGIBILITY"].ca_verification_required is True


def test_rule_sources_have_required_fields():
    for s in rule_sources():
        assert s.rule_id
        assert s.description
        assert s.source


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_rule_calculations_deterministic():
    r1 = _make_record(0, "29ABCDE1234F1Z5", "INV-1", taxable_value="1000.00")
    r2 = _make_record(1, "07FGHIJ5678K1Z6", "INV-2", taxable_value="2000.00")
    first = calculate_tax_exposure([r1, r2])
    second = calculate_tax_exposure([r1, r2])
    assert first == second

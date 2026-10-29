"""Tests for the report module (src/itc_sentinel/report.py).

Covers Excel export, formula-injection protection, stable column names,
deterministic ordering, empty datasets, invalid rows, monetary precision,
provisional exposure labeling, and workbook re-validation by reopening.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from openpyxl import load_workbook

from itc_sentinel.audit import AuditEvent, AuditEventType
from itc_sentinel.decision import (
    Action,
    DecisionResult,
    EligibilityStatus,
    Priority,
    ReasonCode,
    decide,
)
from itc_sentinel.matcher import MatchResult, MatchStatus
from itc_sentinel.report import WorkbookExportResult, export_workbook, safe_cell_value
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


def _make_decision(match_status, valid=True):
    match = _make_match_result(source_row=0, match_status=match_status, valid=valid)
    return decide(match)


# ---------------------------------------------------------------------------
# safe_cell_value
# ---------------------------------------------------------------------------


def test_safe_cell_value_plain_text():
    assert safe_cell_value("hello") == "hello"


def test_safe_cell_value_formula_prefixes():
    assert safe_cell_value("=1+1") == "'=1+1"
    assert safe_cell_value("+1+1") == "'+1+1"
    assert safe_cell_value("-1+1") == "'-1+1"
    assert safe_cell_value("@SUM(A1)") == "'@SUM(A1)"
    assert safe_cell_value("\t=1+1") == "'\t=1+1"


def test_safe_cell_value_leading_whitespace_formula():
    # Some importers trim leading whitespace before evaluating formulas.
    assert safe_cell_value("  =1+1") == "'  =1+1"
    assert safe_cell_value("   @SUM(A1)") == "'   @SUM(A1)"


def test_safe_cell_value_empty_and_none():
    assert safe_cell_value("") == ""
    assert safe_cell_value(None) is None


def test_safe_cell_value_numbers():
    assert safe_cell_value(42) == 42
    assert safe_cell_value(Decimal("100.00")) == Decimal("100.00")


# ---------------------------------------------------------------------------
# Export: valid dataset
# ---------------------------------------------------------------------------


def test_export_workbook_creates_sheets(tmp_path):
    decisions = [_make_decision(MatchStatus.EXACT)]
    path = tmp_path / "out.xlsx"
    result = export_workbook(str(path), decisions)

    assert isinstance(result, WorkbookExportResult)
    assert result.path == str(path)
    assert "Summary" in result.sheets
    assert "Reconciliation" in result.sheets
    assert "Decisions" in result.sheets
    assert result.row_counts["Decisions"] == 1


def test_export_workbook_reopen_and_verify(tmp_path):
    decisions = [_make_decision(MatchStatus.EXACT)]
    path = tmp_path / "out.xlsx"
    export_workbook(str(path), decisions)

    wb = load_workbook(path)
    assert "Summary" in wb.sheetnames
    assert "Reconciliation" in wb.sheetnames
    assert "Decisions" in wb.sheetnames

    ws = wb["Decisions"]
    # Header row + 1 data row
    assert ws.max_row >= 2
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert "gstin" in headers
    assert "invoice_number" in headers
    assert "action" in headers
    assert "reason_code" in headers
    assert "review_required" in headers


def test_summary_uses_stable_status_codes_and_confirmed_definition(tmp_path):
    decisions = [
        _make_decision(MatchStatus.EXACT),
        _make_decision(MatchStatus.AMOUNT_MISMATCH),
    ]
    path = tmp_path / "summary.xlsx"
    export_workbook(str(path), decisions)

    wb = load_workbook(path)
    values = [
        str(value)
        for row in wb["Summary"].iter_rows(values_only=True)
        for value in row
        if value is not None
    ]

    assert "exact" in values
    assert "amount_mismatch" in values
    assert not any(value.startswith("MatchStatus.") for value in values)
    assert "Confirmed matches (exact only)" in values


def test_export_workbook_empty_decisions(tmp_path):
    path = tmp_path / "empty.xlsx"
    result = export_workbook(str(path), [])
    assert result.row_counts["Decisions"] == 0
    assert result.row_counts["Reconciliation"] == 0

    wb = load_workbook(path)
    ws = wb["Decisions"]
    assert ws.max_row == 1  # header only


# ---------------------------------------------------------------------------
# Export: drafts, review, audit sheets
# ---------------------------------------------------------------------------


def test_export_with_drafts(tmp_path):
    decision = _make_decision(MatchStatus.AMOUNT_MISMATCH)
    from itc_sentinel.messages import draft_vendor_message
    draft = draft_vendor_message(decision)
    path = tmp_path / "with_drafts.xlsx"
    result = export_workbook(str(path), [decision], drafts=[draft])

    assert "Vendor Drafts" in result.sheets
    assert result.row_counts["Vendor Drafts"] == 1

    wb = load_workbook(path)
    ws = wb["Vendor Drafts"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert "draft_id" in headers
    assert "category" in headers
    assert "subject" in headers


def test_export_with_review_records(tmp_path):
    from itc_sentinel.audit import ReviewRecord
    review = ReviewRecord(
        review_id="rev-1",
        run_id="run-1",
        invoice_key="29ABCDE1234F1Z5|INV-0",
        match_status="exact",
        suggested_action="claim_itc",
        decision="approve",
        reviewer_reason="Verified",
        reviewer_name="reviewer-1",
        timestamp="2024-04-15T11:00:00+00:00",
    )
    decision = _make_decision(MatchStatus.EXACT)
    path = tmp_path / "with_review.xlsx"
    result = export_workbook(str(path), [decision], review_records=[review])

    assert "Review" in result.sheets
    assert result.row_counts["Review"] == 1


def test_export_with_audit_events(tmp_path):
    event = AuditEvent(
        event_id="evt-1",
        timestamp="2024-04-15T10:00:00+00:00",
        event_type=AuditEventType.RUN_STARTED,
        run_id="run-1",
        summary="run started",
    )
    decision = _make_decision(MatchStatus.EXACT)
    path = tmp_path / "with_audit.xlsx"
    result = export_workbook(str(path), [decision], audit_events=[event])

    assert "Audit" in result.sheets
    assert result.row_counts["Audit"] == 1


# ---------------------------------------------------------------------------
# Formula injection in export
# ---------------------------------------------------------------------------


def test_export_protects_formula_injection(tmp_path):
    """Text cells starting with formula characters must be escaped."""
    # Create a decision whose reason contains a formula-like string.
    match = _make_match_result(source_row=0, match_status=MatchStatus.EXACT)
    # Manually set a formula-injection reason
    match.reason = "=1+1 malicious"
    decision = DecisionResult(
        match_result=match,
        action=Action.PROPOSE_ITC_CLAIM,
        priority=Priority.LOW,
        flags=[],
        reason="=1+1 malicious",
        reason_code=ReasonCode.EXACT_MATCH,
        exposure_amount=Decimal("0"),
        review_required=False,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=[],
    )
    path = tmp_path / "formula.xlsx"
    export_workbook(str(path), [decision])

    wb = load_workbook(path)
    ws = wb["Decisions"]
    # Find the reason column and verify the value starts with apostrophe
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    reason_col = headers.index("reason") + 1
    cell_value = ws.cell(row=2, column=reason_col).value
    assert cell_value == "'=1+1 malicious"


# ---------------------------------------------------------------------------
# Monetary precision
# ---------------------------------------------------------------------------


def test_export_monetary_precision(tmp_path):
    match = _make_match_result(source_row=0, match_status=MatchStatus.EXACT)
    match.amount_difference = Decimal("500.005")  # rounds to 500.01
    decision = DecisionResult(
        match_result=match,
        action=Action.PROPOSE_ITC_CLAIM,
        priority=Priority.LOW,
        flags=[],
        reason="test",
        reason_code=ReasonCode.EXACT_MATCH,
        exposure_amount=Decimal("500.005"),
        review_required=False,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=[],
    )

    path = tmp_path / "money.xlsx"
    export_workbook(str(path), [decision])

    wb = load_workbook(path)
    ws = wb["Decisions"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    exp_col = headers.index("exposure_amount") + 1
    cell_value = ws.cell(row=2, column=exp_col).value
    # Should be quantized to 2 decimal places
    assert cell_value == "500.01"


# ---------------------------------------------------------------------------
# Provisional exposure labeling
# ---------------------------------------------------------------------------


def test_export_labels_provisional_exposure(tmp_path):
    decision = _make_decision(MatchStatus.EXACT)
    path = tmp_path / "provisional.xlsx"
    export_workbook(str(path), [decision])

    wb = load_workbook(path)
    ws = wb["Summary"]
    all_values = []
    for row in ws.iter_rows(values_only=True):
        for v in row:
            if v is not None:
                all_values.append(str(v))
    combined = " ".join(all_values)
    assert "Provisional" in combined or "not confirmed" in combined


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def test_export_workbook_decisions_must_be_list(tmp_path):
    with pytest.raises(ValueError, match="decisions must be a list"):
        export_workbook(str(tmp_path / "bad.xlsx"), "not a list")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Invalid rows preserved in export
# ---------------------------------------------------------------------------


def test_export_invalid_rows_not_dropped(tmp_path):
    decision = _make_decision(MatchStatus.INVALID, valid=False)
    path = tmp_path / "invalid.xlsx"
    result = export_workbook(str(path), [decision])

    assert result.row_counts["Reconciliation"] == 1
    wb = load_workbook(path)
    ws = wb["Reconciliation"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    status_col = headers.index("match_status") + 1
    cell_value = ws.cell(row=2, column=status_col).value
    assert cell_value == "invalid"

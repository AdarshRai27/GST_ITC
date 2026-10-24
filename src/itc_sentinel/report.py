"""Excel export for Phase 4 with formula-injection protection.

Generates a downloadable Excel workbook containing reconciliation results,
decisions, discrepancy classifications, explanations, review statuses, and
summary metrics.

Design principles (per `rules.md`, `architecture.md`, `requirements.md`):
- Preserve source traceability (source file, row, GSTIN, invoice number).
- Use stable column names and deterministic ordering.
- Handle empty datasets, invalid rows, duplicate records, and missing
  optional values safely.
- Apply the documented monetary precision and rounding policy
  (``MONEY_PLACES`` / ROUND_HALF_UP).
- Clearly label provisional estimates and unverified tax-rule assumptions.
- Avoid double-counting records or exposure amounts in summaries.
- Never present an unverified tax conclusion as an authoritative determination.
- Protect exported text cells from formula injection (escape cells starting
  with ``=``, ``+``, ``-``, ``@``).

Public functions:
    export_workbook(path, decisions, drafts=None, review_records=None,
                    settings=None) -> str
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from .audit import ReviewRecord
from .decision import (
    DecisionResult,
    DecisionSettings,
    Priority,
    total_exposure,
)
from .messages import VendorDraft
from .rules import MONEY_PLACES, RuleSettings

__all__ = [
    "export_workbook",
    "safe_cell_value",
    "WorkbookExportResult",
]


@dataclass  # noqa: F821 (imported below)
class WorkbookExportResult:
    """Result of exporting a workbook.

    Attributes:
        path: Filesystem path of the written workbook.
        sheets: Names of sheets written.
        row_counts: Mapping of sheet name to data-row count (excluding header).
    """

    path: str
    sheets: list[str]
    row_counts: dict[str, int]


# ---------------------------------------------------------------------------
# Formula-injection protection
# ---------------------------------------------------------------------------

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t")


def safe_cell_value(value: Any) -> Any:
    """Return a cell value safe from formula injection.

    Text values beginning with formula-leading characters (``=``, ``+``,
    ``-``, ``@``, tab) are prefixed with a single apostrophe so Excel treats
    them as literal text. Non-string values are returned unchanged.

    Args:
        value: The raw cell value.

    Returns:
        A safe cell value.
    """
    if isinstance(value, str):
        if value and value[0] in _FORMULA_PREFIXES:
            return "'" + value
    return value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _money(value: Decimal | None) -> str | None:
    """Format a Decimal money value to 2 decimal places, or None."""
    if value is None:
        return None
    return f"{value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP):.2f}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _invoice_key(record) -> str | None:
    gstin = getattr(record, "gstin", None)
    inv = getattr(record, "invoice_number", None)
    if gstin is None and inv is None:
        return None
    return f"{gstin or ''}|{inv or ''}"


def _write_header(ws, headers: list[str]) -> None:
    for col_index, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col_index, value=header)


def _write_row(ws, row: int, values: list[Any]) -> None:
    for col_index, value in enumerate(values, start=1):
        ws.cell(row=row, column=col_index, value=safe_cell_value(value))


def _autofit(ws) -> None:
    for col_index, column_cells in enumerate(ws.columns, start=1):
        max_len = 0
        letter = get_column_letter(col_index)
        for cell in column_cells:
            try:
                val = str(cell.value) if cell.value is not None else ""
                if len(val) > max_len:
                    max_len = len(val)
            except Exception:
                pass
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 60)


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------


def _build_summary_sheet(ws, decisions: list[DecisionResult],
                         settings: DecisionSettings) -> int:
    """Write the Summary sheet. Returns the number of data rows."""
    headers = [
        "Metric", "Value", "Notes",
    ]
    _write_header(ws, headers)

    status_counts: dict[str, int] = {}
    for d in decisions:
        key = d.match_result.match_status
        status_counts[key] = status_counts.get(key, 0) + 1

    total_exposure_amt = total_exposure(decisions)
    review_required_count = sum(1 for d in decisions if d.review_required)
    high_count = sum(1 for d in decisions if d.priority == Priority.HIGH)
    medium_count = sum(1 for d in decisions if d.priority == Priority.MEDIUM)
    low_count = sum(1 for d in decisions if d.priority == Priority.LOW)

    rows = [
        ("Total reconciliation rows", len(decisions), ""),
        ("Review required", review_required_count,
         "Human review required for uncertain or high-risk records"),
        ("High priority", high_count,
         f"Exposure >= {_money(settings.high_exposure_threshold)}"),
        ("Medium priority", medium_count,
         f"Exposure >= {_money(settings.medium_exposure_threshold)}"),
        ("Low priority", low_count, ""),
        ("Provisional exposure at risk (sum)",
         _money(total_exposure_amt),
         "Provisional estimate only; not confirmed ITC impact "
         "(rule R-CALC-TAX-EXPOSURE pending CA verification)"),
        ("Unverified tax assumptions", "See rules.py rule_sources()",
         "GST rules require CA verification before being treated as reliable"),
    ]
    r = 2
    for metric, value, notes in rows:
        _write_row(ws, r, [metric, value, notes])
        r += 1

    # Status breakdown
    r += 1
    _write_row(ws, r, ["Match Status Breakdown", "", ""])
    r += 1
    _write_header(ws, ["Status", "Count", "Notes"])
    r += 1
    for status in sorted(status_counts, key=lambda s: str(s)):
        _write_row(ws, r, [str(status), status_counts[status], ""])
        r += 1

    _autofit(ws)
    return r - 2  # approximate data rows


def _build_reconciliation_sheet(ws, decisions: list[DecisionResult]) -> int:
    """Write the Reconciliation sheet. Returns data-row count."""
    headers = [
        "source_type", "source_file", "source_row", "gstin",
        "invoice_number", "invoice_date", "match_status", "confidence",
        "amount_difference", "tax_head_difference", "discrepancies",
        "reason",
    ]
    _write_header(ws, headers)

    r = 2
    for d in decisions:
        m = d.match_result
        book = m.purchase_record
        gstr2b = m.gstr2b_record
        record = book or gstr2b
        source_type = (
            book.source_type.value if book is not None else
            gstr2b.source_type.value if gstr2b is not None else ""
        )
        source_file = getattr(record, "source_file", "") if record is not None else ""
        source_row = getattr(record, "source_row", "") if record is not None else ""
        _write_row(ws, r, [
            source_type,
            source_file,
            source_row,
            record.gstin if record is not None else None,
            record.invoice_number if record is not None else None,
            str(record.invoice_date) if record is not None and record.invoice_date else None,
            str(m.match_status.value),
            m.confidence,
            _money(m.amount_difference),
            "Yes" if m.tax_head_difference else "No",
            "; ".join(m.discrepancies),
            m.reason,
        ])
        r += 1
    _autofit(ws)
    return r - 2


def _build_decisions_sheet(ws, decisions: list[DecisionResult]) -> int:
    """Write the Decisions sheet. Returns data-row count."""
    headers = [
        "source_type", "source_file", "source_row", "gstin",
        "invoice_number", "action", "priority", "flags", "reason_code",
        "reason", "exposure_amount", "review_required",
        "eligibility_status",
    ]
    _write_header(ws, headers)

    r = 2
    for d in decisions:
        m = d.match_result
        book = m.purchase_record
        gstr2b = m.gstr2b_record
        record = book or gstr2b
        source_type = (
            book.source_type.value if book is not None else
            gstr2b.source_type.value if gstr2b is not None else ""
        )
        source_file = getattr(record, "source_file", "") if record is not None else ""
        source_row = getattr(record, "source_row", "") if record is not None else ""
        _write_row(ws, r, [
            source_type,
            source_file,
            source_row,
            record.gstin if record is not None else None,
            record.invoice_number if record is not None else None,
            d.action.value,
            d.priority.value,
            "; ".join(f.value for f in d.flags),
            d.reason_code.value,
            d.reason,
            _money(d.exposure_amount),
            "Yes" if d.review_required else "No",
            d.eligibility_status.value,
        ])
        r += 1
    _autofit(ws)
    return r - 2


def _build_drafts_sheet(ws, drafts: list[VendorDraft]) -> int:
    """Write the Vendor Drafts sheet. Returns data-row count."""
    headers = [
        "draft_id", "created_at", "category", "invoice_key", "vendor_name",
        "gstin", "invoice_number", "subject", "body_email", "body_whatsapp",
        "notes", "llm_enhanced",
    ]
    _write_header(ws, headers)

    r = 2
    for d in drafts:
        _write_row(ws, r, [
            d.draft_id,
            d.created_at,
            d.category,
            d.invoice_key,
            d.vendor_name,
            d.gstin,
            d.invoice_number,
            d.subject,
            d.body_email,
            d.body_whatsapp,
            d.notes,
            "Yes" if d.llm_enhanced else "No",
        ])
        r += 1
    _autofit(ws)
    return r - 2


def _build_review_sheet(ws, review_records: list[ReviewRecord]) -> int:
    """Write the Review sheet. Returns data-row count."""
    headers = [
        "review_id", "run_id", "invoice_key", "match_status",
        "suggested_action", "decision", "reviewer_reason", "reviewer_name",
        "timestamp",
    ]
    _write_header(ws, headers)

    r = 2
    for rec in review_records:
        _write_row(ws, r, [
            rec.review_id,
            rec.run_id,
            rec.invoice_key,
            rec.match_status,
            rec.suggested_action,
            rec.decision,
            rec.reviewer_reason,
            rec.reviewer_name,
            rec.timestamp,
        ])
        r += 1
    _autofit(ws)
    return r - 2


def _build_audit_sheet(ws, events) -> int:
    """Write the Audit sheet. Returns data-row count."""
    headers = [
        "event_id", "timestamp", "event_type", "run_id", "invoice_key",
        "summary",
    ]
    _write_header(ws, headers)

    r = 2
    for e in events:
        _write_row(ws, r, [
            e.event_id,
            e.timestamp,
            e.event_type,
            e.run_id,
            e.invoice_key,
            e.summary,
        ])
        r += 1
    _autofit(ws)
    return r - 2


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_workbook(
    path: str,
    decisions: list[DecisionResult],
    drafts: list[VendorDraft] | None = None,
    review_records: list[ReviewRecord] | None = None,
    audit_events: list | None = None,
    settings: DecisionSettings | None = None,
    rule_settings: RuleSettings | None = None,
) -> WorkbookExportResult:
    """Export reconciliation results, decisions, drafts, and audit to Excel.

    Args:
        path: Output .xlsx file path.
        decisions: Decision results to export.
        drafts: Optional vendor message drafts.
        review_records: Optional human review records.
        audit_events: Optional audit events (any iterable of objects with
            attributes matching AuditEvent fields).
        settings: Decision settings; defaults used when None.
        rule_settings: Rule settings; defaults used when None.

    Returns:
        A :class:`WorkbookExportResult` describing what was written.

    Raises:
        OSError: If the workbook cannot be written.
        ValueError: If ``decisions`` is not a list.
    """
    if settings is None:
        settings = DecisionSettings()
    if drafts is None:
        drafts = []
    if review_records is None:
        review_records = []
    if audit_events is None:
        audit_events = []
    if not isinstance(decisions, list):
        raise ValueError("decisions must be a list")

    wb = Workbook()

    # Remove default sheet and create our sheets in deterministic order.
    wb.remove(wb.active)

    summary_ws = wb.create_sheet("Summary")
    recon_ws = wb.create_sheet("Reconciliation")
    decision_ws = wb.create_sheet("Decisions")

    summary_rows = _build_summary_sheet(summary_ws, decisions, settings)
    recon_rows = _build_reconciliation_sheet(recon_ws, decisions)
    decision_rows = _build_decisions_sheet(decision_ws, decisions)

    sheets = ["Summary", "Reconciliation", "Decisions"]
    row_counts = {
        "Summary": summary_rows,
        "Reconciliation": recon_rows,
        "Decisions": decision_rows,
    }

    if drafts:
        draft_ws = wb.create_sheet("Vendor Drafts")
        draft_rows = _build_drafts_sheet(draft_ws, drafts)
        sheets.append("Vendor Drafts")
        row_counts["Vendor Drafts"] = draft_rows

    if review_records:
        review_ws = wb.create_sheet("Review")
        review_rows = _build_review_sheet(review_ws, review_records)
        sheets.append("Review")
        row_counts["Review"] = review_rows

    if audit_events:
        audit_ws = wb.create_sheet("Audit")
        audit_rows = _build_audit_sheet(audit_ws, list(audit_events))
        sheets.append("Audit")
        row_counts["Audit"] = audit_rows

    wb.save(path)

    return WorkbookExportResult(
        path=str(path),
        sheets=sheets,
        row_counts=row_counts,
    )

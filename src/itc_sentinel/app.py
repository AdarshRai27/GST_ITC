"""ITC Sentinel — Streamlit MVP UI.

End-to-end workflow for GST ITC reconciliation:

- File upload for purchase register (CSV/XLSX) and GSTR-2B JSON, with safe
  temporary-file handling (see :mod:`itc_sentinel.uploads`).
- Deterministic reconciliation, decision support, human review, vendor drafts,
  and Excel export.
- Stable per-record review identity, policy-controlled review actions, and
  metrics that never count mismatches as confirmed matches.

This is a decision-support demo, not an automated GST filing system. A match
does not establish ITC eligibility; all eligibility statuses remain
provisional pending Chartered Accountant validation of the tax rules.
"""

from __future__ import annotations

import os
import re
import uuid
from decimal import Decimal, InvalidOperation
from html import escape as _html_escape
from pathlib import Path

import pandas as pd
import streamlit as st

from itc_sentinel import __version__
from itc_sentinel.audit import (
    AuditEvent,
    AuditEventType,
    ReviewRecord,
    _invoice_key,
    _utc_now_iso,
    new_audit_log,
)
from itc_sentinel.decision import (
    DecisionResult,
    DecisionSettings,
    allowed_review_decisions,
    decide,
    validate_review_decision,
)
from itc_sentinel.ingest import (
    IngestionError,
    load_gstr2b_json,
    load_purchase_register,
)
from itc_sentinel.matcher import (
    MatchResult,
    MatchStatus,
    ReconciliationResult,
    ReconciliationSettings,
    reconcile,
    record_identity,
)
from itc_sentinel.messages import _decision_to_category, draft_vendor_message
from itc_sentinel.metrics import ReconciliationMetrics, compute_metrics
from itc_sentinel.normalize import normalize_records
from itc_sentinel.report import WorkbookExportResult, export_workbook
from itc_sentinel.ui.components import (
    callout,
    chip,
    comparison_table,
    empty_state,
    footer,
    format_inr,
    key_value_table,
    kpi_card,
    page_header,
    review_header,
    secondary_stats,
    section_header,
    sidebar_brand,
    status_breakdown,
    welcome_intro,
    workflow_steps,
)
from itc_sentinel.ui.theme import apply_theme
from itc_sentinel.uploads import (
    GSTR2B_EXTENSIONS,
    PURCHASE_EXTENSIONS,
    UploadValidationError,
    cleanup_paths,
    save_uploaded_file,
)

# ---------------------------------------------------------------------------
# Page configuration and theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ITC Sentinel — GST ITC Reconciliation MVP",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

_STATUS_LABELS: dict[MatchStatus, str] = {
    MatchStatus.EXACT: "Exact match",
    MatchStatus.AMOUNT_MISMATCH: "Amount mismatch",
    MatchStatus.TAX_HEAD_MISMATCH: "Tax-head mismatch",
    MatchStatus.FUZZY: "Fuzzy candidate",
    MatchStatus.PROBABLE: "Probable candidate",
    MatchStatus.LOW_CONFIDENCE: "Low-confidence candidate",
    MatchStatus.UNMATCHED_BOOKS: "Unmatched (books)",
    MatchStatus.UNMATCHED_GSTR2B: "Unmatched (GSTR-2B)",
    MatchStatus.DUPLICATE: "Duplicate row",
    MatchStatus.INVALID: "Invalid row",
}

_STATUS_NOTES: dict[MatchStatus, str] = {
    MatchStatus.EXACT: (
        "Same GSTIN, invoice number, date, and amounts. A candidate for an ITC "
        "claim only; matching is not proof of eligibility."
    ),
    MatchStatus.AMOUNT_MISMATCH: (
        "Same GSTIN and invoice number, but monetary values differ. Requires "
        "vendor clarification."
    ),
    MatchStatus.TAX_HEAD_MISMATCH: (
        "Same GSTIN and invoice number, but tax is under a different head "
        "(domestic CGST/SGST vs IGST). Flag for review."
    ),
    MatchStatus.FUZZY: (
        "Invoice numbers share an alphanumeric core but differ in formatting. "
        "Verify invoice identity before any ITC action."
    ),
    MatchStatus.PROBABLE: (
        "Low-confidence similarity-based match. Not a confirmed match."
    ),
    MatchStatus.LOW_CONFIDENCE: (
        "Auto-detected below the confidence threshold. Requires human review."
    ),
    MatchStatus.UNMATCHED_BOOKS: (
        "No matching GSTR-2B invoice found. May affect an ITC claim; requires "
        "human review."
    ),
    MatchStatus.UNMATCHED_GSTR2B: (
        "No matching purchase-register invoice (GSTR-2B only). No books-side "
        "action required."
    ),
    MatchStatus.DUPLICATE: (
        "Duplicate purchase-register row (same GSTIN + invoice). May cause "
        "double claiming."
    ),
    MatchStatus.INVALID: (
        "Row failed Phase 1 validation. Preserved for review; no ITC action can "
        "be determined from invalid data."
    ),
}

_STATUS_TONES: dict[MatchStatus, str] = {
    MatchStatus.EXACT: "positive",
    MatchStatus.AMOUNT_MISMATCH: "error",
    MatchStatus.TAX_HEAD_MISMATCH: "error",
    MatchStatus.FUZZY: "warning",
    MatchStatus.PROBABLE: "warning",
    MatchStatus.LOW_CONFIDENCE: "warning",
    MatchStatus.UNMATCHED_BOOKS: "warning",
    MatchStatus.UNMATCHED_GSTR2B: "neutral",
    MatchStatus.DUPLICATE: "error",
    MatchStatus.INVALID: "error",
}

_ACTION_LABELS: dict[str, str] = {
    "propose_itc_claim": "Propose ITC claim (candidate only)",
    "request_clarification": "Request vendor clarification",
    "flag_for_review": "Flag for human review",
    "exclude_from_itc": "Exclude from ITC (provisional)",
    "no_action": "No action",
}

_ELIGIBILITY_LABELS: dict[str, str] = {
    "eligible": "Eligible (provisional)",
    "ineligible": "Ineligible (provisional)",
    "uncertain": "UNCERTAIN — pending CA validation",
    "not_assessed": "Not assessed",
}

_PRIORITY_LABELS: dict[str, str] = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

_REVIEW_ACTION_LABELS: dict[str, str] = {
    "approve": "Approve",
    "reject": "Reject",
    "pending": "Pending",
}

_AUDIT_EVENT_LABELS: dict[str, str] = {
    "run_started": "Run started",
    "run_completed": "Run completed",
    "decision_recorded": "Decision recorded",
    "review_action": "Review action",
    "export_created": "Export created",
    "error": "Error",
}

_DRAFT_CATEGORY_LABELS: dict[str, str] = {
    "invalid_data": "Invalid data",
    "duplicate": "Duplicate invoice",
    "amount_mismatch": "Amount mismatch",
    "tax_head_mismatch": "Tax-head mismatch",
    "missing_in_2b": "Missing in GSTR-2B",
    "fuzzy": "Fuzzy match",
    "probable": "Probable match",
    "low_confidence": "Low-confidence match",
}


def _draft_category_label(category: str) -> str:
    return _DRAFT_CATEGORY_LABELS.get(
        category, category.replace("_", " ").capitalize()
    )


# Presentation-only labels. Internal enum values, reason codes, and record
# identifiers are never changed; these labels are used for display only.
_DISCREPANCY_LABELS: dict[str, str] = {
    "taxable_value": "Taxable value",
    "cgst": "CGST",
    "sgst": "SGST",
    "igst": "IGST",
    "cess": "Cess",
    "invoice_date": "Invoice date",
    "invoice_number": "Invoice number",
    "gstin": "GSTIN",
    "vendor_name": "Vendor name",
    "duplicate_invoice": "Duplicate invoice",
    "duplicate": "Duplicate invoice",
    "amount_mismatch": "Amount mismatch",
    "tax_head_mismatch": "Tax-head mismatch",
    "missing_in_2b": "Missing in GSTR-2B",
    "invalid_data": "Invalid data",
    "fuzzy": "Fuzzy match",
    "fuzzy_match": "Fuzzy match",
    "probable": "Probable match",
    "probable_match": "Probable match",
    "low_confidence": "Low-confidence match",
    "low_confidence_match": "Low-confidence match",
    # Decision reason codes are uppercase and use the same display vocabulary.
    "ITC-EXACT-MATCH": "Exact match",
    "ITC-AMOUNT-MISMATCH": "Amount mismatch",
    "ITC-TAX-HEAD-MISMATCH": "Tax-head mismatch",
    "ITC-FUZZY-MATCH": "Fuzzy match",
    "ITC-PROBABLE-MATCH": "Probable match",
    "ITC-LOW-CONFIDENCE": "Low-confidence match",
    "ITC-UNMATCHED-BOOKS": "Unmatched — books",
    "ITC-UNMATCHED-GSTR2B": "Unmatched — GSTR-2B",
    "ITC-DUPLICATE": "Duplicate invoice",
    "ITC-INVALID-DATA": "Invalid data",
}

_DISCREPANCY_PATTERN = re.compile(
    r"\b("
    + "|".join(
        re.escape(code)
        for code in sorted(_DISCREPANCY_LABELS, key=len, reverse=True)
    )
    + r")\b"
)


def _discrepancy_label(code: str) -> str:
    """Return a human-readable label for a discrepancy or reason code."""
    return _DISCREPANCY_LABELS.get(
        code, code.replace("_", " ").strip().capitalize()
    )


def _discrepancy_text(codes: list[str], separator: str = ", ") -> str:
    return separator.join(_discrepancy_label(code) for code in codes)


def _humanize_codes(text: str) -> str:
    """Replace known machine codes in display copy, leaving other text intact."""
    if not text:
        return text
    return _DISCREPANCY_PATTERN.sub(
        lambda match: _DISCREPANCY_LABELS[match.group(1)], text
    )


# ---------------------------------------------------------------------------
# Paths and run lifecycle
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _data_root() -> Path:
    override = os.environ.get("ITC_SENTINEL_DATA_DIR")
    if override:
        return Path(override).resolve()
    return _repo_root() / "data"


def _sample_dir() -> Path:
    override = os.environ.get("ITC_SENTINEL_SAMPLE_DIR")
    if override:
        return Path(override).resolve()
    return _repo_root() / "data" / "sample"


def _runs_root() -> Path:
    return _data_root() / "runs"


def _start_new_run() -> None:
    """Rotate to a fresh run: new identity, audit log, and review state.

    Rotating on every reconciliation request keeps reviews, metrics, and audit
    events from mixing data across runs in the same browser session.
    """
    run_id = str(uuid.uuid4())
    run_dir = _runs_root() / run_id
    audit_path = run_dir / "audit.jsonl"
    audit_log = new_audit_log(audit_path)

    st.session_state.run_id = run_id
    st.session_state.audit_log_path = str(audit_path)
    st.session_state.audit_log = audit_log
    st.session_state.review_records = []
    st.session_state._pipeline_done = False
    st.session_state._input_source = None
    st.session_state._reconciliation_result = None
    st.session_state._decisions = None
    st.session_state._metrics = None
    st.session_state._drafts = []
    st.session_state._export_bytes = None
    st.session_state._export_meta = None
    st.session_state._export_audited = False
    st.session_state._review_flash = None

    audit_log.append(
        AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=_utc_now_iso(),
            event_type=AuditEventType.RUN_STARTED,
            run_id=run_id,
            summary="Reconciliation run started",
        )
    )


if "run_id" not in st.session_state:
    _start_new_run()


def _record_event(
    event_type: AuditEventType,
    summary: str,
    *,
    invoice_key: str | None = None,
    metadata: dict | None = None,
) -> None:
    audit_log = st.session_state.get("audit_log")
    if audit_log is None:
        return
    try:
        audit_log.append(
            AuditEvent(
                event_id=str(uuid.uuid4()),
                timestamp=_utc_now_iso(),
                event_type=event_type,
                run_id=st.session_state.run_id,
                invoice_key=invoice_key,
                summary=summary,
                metadata=metadata or {},
            )
        )
    except OSError:
        # Auditing must not crash the UI; the failure is surfaced separately.
        st.warning("The local audit log could not be written for this action.")


def _format_audit_timestamp(value: str) -> str:
    """Render an ISO-8601 audit timestamp compactly for the audit table."""
    text = str(value or "")
    if "T" in text and len(text) >= 19:
        return f"{text[:10]} {text[11:19]} UTC"
    return text or "—"


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------
def _execute_pipeline(
    purchase_file: str | Path,
    gstr2b_file: str | Path,
) -> tuple[ReconciliationResult, list[DecisionResult]]:
    """Run ingestion → normalization → matching → decisions.

    Raises the underlying exception (with context added by the caller) when a
    stage fails. No Streamlit calls are made here, so the function is easy to
    exercise in tests.
    """
    purchase_raw = load_purchase_register(str(purchase_file))
    gstr2b_raw = load_gstr2b_json(str(gstr2b_file))

    purchase_normalized = normalize_records(
        purchase_raw.raw_records,
        purchase_raw.source_type,
        purchase_raw.source_file,
    )
    gstr2b_normalized = normalize_records(
        gstr2b_raw.raw_records,
        gstr2b_raw.source_type,
        gstr2b_raw.source_file,
    )

    result = reconcile(
        purchase_normalized,
        gstr2b_normalized,
        ReconciliationSettings(),
    )
    decisions = [
        decide(match, decision_settings=DecisionSettings())
        for match in result.matches
    ]
    return result, decisions


def _generate_drafts(decisions: list[DecisionResult]) -> list:
    drafts = []
    for decision in decisions:
        try:
            if _decision_to_category(decision) is None:
                continue
            drafts.append(draft_vendor_message(decision, enhanced_by_llm=False))
        except ValueError:
            continue
    return drafts


def _record_to_invoice_key(match: MatchResult) -> str | None:
    record = match.purchase_record or match.gstr2b_record
    if record is None:
        return None
    return _invoice_key(record.gstin, record.invoice_number)


def _display_label(decision: DecisionResult) -> str:
    match = decision.match_result
    record = match.purchase_record or match.gstr2b_record
    invoice = (record.invoice_number or "—") if record is not None else "—"
    vendor = (
        (match.purchase_record.vendor_name or "")
        if match.purchase_record is not None
        else ""
    )
    parts = [_STATUS_LABELS[match.match_status]]
    if vendor:
        parts.append(vendor)
    # The GSTIN is available in the comparison panels and full detail view;
    # omitting it here keeps the selector readable on tablet-width screens.
    parts.append(invoice)
    # The trailing "row <record id>" keeps each option uniquely identifiable
    # and preserves the stable record identity used by reviews and audit events.
    return f"{' · '.join(parts)} · row {record_identity(match)}"


def _latest_reviews_by_record(review_records: list[ReviewRecord]) -> dict[str, str]:
    latest: dict[str, str] = {}
    for record in review_records:
        key = record.record_id or f"invoice:{record.invoice_key or ''}"
        latest[key] = record.decision
    return latest


def _latest_state_for(
    review_records: list[ReviewRecord],
    decision: DecisionResult,
) -> str:
    record_id = record_identity(decision.match_result)
    invoice_key = _record_to_invoice_key(decision.match_result)
    state = "none"
    for record in review_records:
        matches = record.record_id == record_id or (
            not record.record_id
            and record.invoice_key
            and record.invoice_key == invoice_key
        )
        if matches:
            state = record.decision
    return state


_FIELD_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("GSTIN", "gstin", False),
    ("Invoice", "invoice_number", False),
    ("Invoice date", "invoice_date", False),
    ("Taxable value", "taxable_value", True),
    ("CGST", "cgst", True),
    ("SGST", "sgst", True),
    ("IGST", "igst", True),
    ("Cess", "cess", True),
)


def _amounts_differ(left: object, right: object) -> bool:
    try:
        return Decimal(str(left)) != Decimal(str(right))
    except (InvalidOperation, ValueError, TypeError):
        return str(left) != str(right)


def _comparison_rows(record: object, counterpart: object):
    """Build aligned comparison rows for one record side.

    Differences are only flagged when both sides actually contain a value; a
    missing counterpart is shown as an em dash instead of a false difference.
    """
    rows: list[tuple[str, str, bool]] = []
    for label, attribute, is_money in _FIELD_SPECS:
        raw = getattr(record, attribute, None) if record is not None else None
        other = (
            getattr(counterpart, attribute, None)
            if counterpart is not None
            else None
        )
        if is_money:
            display = format_inr(raw)
        elif raw in (None, ""):
            display = "—"
        else:
            display = str(raw)

        differs = False
        if (
            record is not None
            and counterpart is not None
            and raw is not None
            and other is not None
        ):
            differs = (
                _amounts_differ(raw, other)
                if is_money
                else str(raw) != str(other)
            )
        rows.append((label, display, differs))
    return rows


def _status_dataframe(
    result: ReconciliationResult,
    decisions: list[DecisionResult],
) -> pd.DataFrame:
    decision_by_id = {
        record_identity(d.match_result): d for d in decisions
    }
    rows = []
    for match in result.matches:
        record_id = record_identity(match)
        decision = decision_by_id.get(record_id)
        record = match.purchase_record or match.gstr2b_record
        taxable = getattr(record, "taxable_value", None) if record else None
        rows.append(
            {
                "Record": record_id,
                "GSTIN": (record.gstin or "") if record is not None else "",
                "Invoice": (
                    record.invoice_number or ""
                    if record is not None
                    else ""
                ),
                "Source": (
                    "Books" if match.purchase_record is not None else "GSTR-2B"
                ),
                "Vendor": (
                    (match.purchase_record.vendor_name or "")
                    if match.purchase_record is not None
                    else ""
                )
                or "—",
                "Status": _STATUS_LABELS[match.match_status],
                "Review": (
                    "Required"
                    if decision is not None and decision.review_required
                    else "—"
                ),
                "Confidence": (
                    float(match.confidence) if match.confidence else None
                ),
                "Taxable value (₹)": (
                    float(taxable) if taxable is not None else None
                ),
                "Amount difference (₹)": (
                    float(match.amount_difference)
                    if match.amount_difference is not None
                    else None
                ),
                "Discrepancies": (
                    _discrepancy_text(match.discrepancies, separator="; ")
                    if match.discrepancies
                    else "—"
                ),
                "Reason": match.reason,
            }
        )
    columns = [
        "Record",
        "GSTIN",
        "Invoice",
        "Source",
        "Vendor",
        "Status",
        "Review",
        "Confidence",
        "Taxable value (₹)",
        "Amount difference (₹)",
        "Discrepancies",
        "Reason",
    ]
    return pd.DataFrame(rows, columns=columns)


def _metric_definition_rows(metrics: ReconciliationMetrics) -> list[dict]:
    return [
        {
            "KPI": "Reconciliation rows",
            "Count": metrics.total_reconciliation_rows,
            "Definition": (
                "One row per reconciliation result. A matched pair counts once, "
                "not twice."
            ),
        },
        {
            "KPI": "Source rows",
            "Count": metrics.total_source_rows,
            "Definition": "Underlying purchase-register + GSTR-2B records.",
        },
        {
            "KPI": "Confirmed matches (exact)",
            "Count": metrics.confirmed_matches,
            "Definition": (
                "Exact matches only. Amount mismatches, tax-head mismatches, "
                "fuzzy/probable matches, duplicates, invalid and unmatched rows "
                "are NOT confirmed."
            ),
        },
        {
            "KPI": "Amount mismatches",
            "Count": metrics.amount_mismatches,
            "Definition": "Monetary differences on the same GSTIN + invoice.",
        },
        {
            "KPI": "Tax-head mismatches",
            "Count": metrics.tax_head_mismatches,
            "Definition": "Domestic CGST/SGST versus IGST on the same invoice.",
        },
        {
            "KPI": "Fuzzy candidates",
            "Count": metrics.fuzzy_candidates,
            "Definition": "Invoice formatting variants; not confirmed matches.",
        },
        {
            "KPI": "Probable candidates",
            "Count": metrics.probable_candidates,
            "Definition": "Similarity-based candidates; never confirmed.",
        },
        {
            "KPI": "Low-confidence candidates",
            "Count": metrics.low_confidence_candidates,
            "Definition": "Below the confidence threshold; requires review.",
        },
        {
            "KPI": "Duplicates",
            "Count": metrics.duplicates,
            "Definition": "Purchase-register rows repeating a GSTIN + invoice.",
        },
        {
            "KPI": "Invalid rows",
            "Count": metrics.invalid_records,
            "Definition": "Rows that failed ingestion/normalization validation.",
        },
        {
            "KPI": "Unmatched (books)",
            "Count": metrics.unmatched_books,
            "Definition": "Purchase-register rows with no GSTR-2B counterpart.",
        },
        {
            "KPI": "Unmatched (GSTR-2B)",
            "Count": metrics.unmatched_gstr2b,
            "Definition": "GSTR-2B rows with no purchase-register counterpart.",
        },
        {
            "KPI": "Review required",
            "Count": metrics.review_required,
            "Definition": "Records whose decision has review_required=True.",
        },
        {
            "KPI": "Reviewed records",
            "Count": metrics.reviewed_records,
            "Definition": (
                "Unique review-required records with at least one review; the "
                "latest decision per record wins."
            ),
        },
        {
            "KPI": "Awaiting review",
            "Count": metrics.awaiting_review,
            "Definition": "Review-required records with no recorded review.",
        },
        {
            "KPI": "Accepted / Rejected / Pending",
            "Count": metrics.accepted + metrics.rejected + metrics.pending,
            "Definition": (
                f"Latest review state: {metrics.accepted} accepted, "
                f"{metrics.rejected} rejected, {metrics.pending} pending."
            ),
        },
    ]


def _generate_workbook(
    decisions: list[DecisionResult],
    review_records: list[ReviewRecord],
) -> WorkbookExportResult:
    """Build the workbook using the existing export implementation."""
    export_path = (
        _runs_root()
        / st.session_state.run_id
        / "reconciliation.xlsx"
    )
    export_result = export_workbook(
        str(export_path),
        decisions,
        drafts=st.session_state.get("_drafts", []),
        review_records=review_records,
        audit_events=st.session_state.audit_log.read_events(),
        settings=DecisionSettings(),
    )
    st.session_state._export_bytes = Path(export_result.path).read_bytes()
    st.session_state._export_meta = {
        "sheets": list(export_result.sheets),
        "row_counts": dict(export_result.row_counts),
    }
    if not st.session_state.get("_export_audited", False):
        _record_event(
            AuditEventType.EXPORT_CREATED,
            f"Excel workbook exported with {len(export_result.sheets)} sheets",
            metadata={"sheets": ",".join(export_result.sheets)},
        )
        st.session_state._export_audited = True
    return export_result


# ---------------------------------------------------------------------------
# Sidebar: compact workspace controls
# ---------------------------------------------------------------------------
with st.sidebar:
    sidebar_brand(__version__)

    st.markdown(
        '<div class="itc-side-label">Input source</div>',
        unsafe_allow_html=True,
    )
    use_sample = st.checkbox(
        "Use synthetic sample data",
        value=True,
        help="Loads the synthetic purchase register + GSTR-2B demo files.",
        key="use_sample_data",
    )

    if use_sample:
        purchase_upload = None
        gstr2b_upload = None
        st.caption(
            "Synthetic purchase register and GSTR-2B fixture. No real taxpayer "
            "data is used."
        )
    else:
        purchase_upload = st.file_uploader(
            "Purchase register (CSV or XLSX)",
            type=["csv", "xlsx"],
            help=(
                "Required columns: gstin, invoice_number, invoice_date, "
                "taxable_value. Optional: cgst, sgst, igst, cess, vendor_name."
            ),
            key="purchase_uploader",
        )
        gstr2b_upload = st.file_uploader(
            "GSTR-2B JSON",
            type=["json"],
            help=(
                "Expected: {gstin, period, invoices:[{supplier_gstin, "
                "invoice_number, invoice_date, taxable_value, cgst, sgst, "
                "igst, cess, invoice_type}]}"
            ),
            key="gstr2b_uploader",
        )
        st.caption(
            "Both files are validated before the deterministic pipeline runs. "
            "Temporary uploads are removed after processing."
        )

    run_clicked = st.button(
        "Run Reconciliation",
        type="primary",
        key="run_reconciliation",
        width="stretch",
    )

    with st.expander("About & safeguards", expanded=False):
        st.markdown(f"**ITC Sentinel** v{__version__}")
        st.markdown(
            "GST Input Tax Credit reconciliation MVP — deterministic Python "
            "pipeline, rule-based decision support, human review, "
            "template-based vendor drafts, and Excel export with an audit trail."
        )
        st.markdown("**Important disclaimers**")
        st.markdown(
            "- This is a reconciliation and decision-support *demo*, not an "
            "automated GST filing system.\n"
            "- A match does **not** establish ITC eligibility. All eligibility "
            "statuses are **UNCERTAIN** pending Chartered Accountant "
            "verification of tax rules.\n"
            "- Exact matches are *candidates* for an ITC claim and still "
            "require human review.\n"
            "- A discrepancy alone does **not** establish wrongdoing.\n"
            "- Unverified tax assumptions are explicitly provisional.\n"
            "- LLM enhancement is opt-in and disabled by default. Drafts "
            "require human review before use. No emails or messages are sent "
            "automatically.\n"
            "- The append-only audit log is a local demo trail, not "
            "tamper-proof storage.\n"
            "- Do not upload real taxpayer data containing confidential "
            "credentials."
        )

    st.markdown(
        '<div class="itc-side-footer">'
        "Deterministic pipeline · No automated filing · No messages sent"
        "</div>",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Header and first-load experience
# ---------------------------------------------------------------------------
pipeline_done = bool(st.session_state.get("_pipeline_done", False))
_source = st.session_state.get("_input_source")
_source_label = {
    "sample": "Sample data",
    "custom": "Custom files",
}.get(_source, "Not started")
_source_tone = _source or "neutral"

page_header(
    source_label=_source_label,
    source_tone=_source_tone,
    run_id=st.session_state.get("run_id") if pipeline_done else None,
)

feedback_slot = st.empty()

welcome_run_clicked = False
if not pipeline_done:
    welcome_intro()
    workflow_steps()

    if use_sample:
        welcome_run_clicked = st.button(
            "Run synthetic sample",
            key="welcome_run_sample",
            type="primary",
        )
        st.caption(
            "Synthetic fixtures only. No real taxpayer data is used or sent. "
            "The same action is available from the sidebar."
        )
    else:
        welcome_run_clicked = st.button(
            "Run reconciliation",
            key="welcome_run_custom",
            type="primary",
        )
        st.caption(
            "Both uploads are required. Files are validated and temporary "
            "copies are removed after processing."
        )


# ---------------------------------------------------------------------------
# Run reconciliation
# ---------------------------------------------------------------------------
if run_clicked or welcome_run_clicked:
    _start_new_run()
    temp_paths: list[str] = []
    try:
        if use_sample:
            purchase_file: str | Path = (
                _sample_dir() / "purchase_register_synthetic.csv"
            )
            gstr2b_file: str | Path = _sample_dir() / "gstr2b_synthetic.json"
            for candidate in (purchase_file, gstr2b_file):
                if not Path(candidate).is_file():
                    raise IngestionError(
                        f"Sample file not found: {candidate}. Run from the "
                        "repository root or set ITC_SENTINEL_SAMPLE_DIR."
                    )
        else:
            if purchase_upload is None or gstr2b_upload is None:
                raise UploadValidationError(
                    "Please upload both the purchase register and the GSTR-2B "
                    "JSON before running reconciliation."
                )
            upload_dir = _runs_root() / st.session_state.run_id / "uploads"
            purchase_file = save_uploaded_file(
                purchase_upload,
                upload_dir,
                PURCHASE_EXTENSIONS,
                kind="purchase",
            )
            temp_paths.append(purchase_file)
            gstr2b_file = save_uploaded_file(
                gstr2b_upload,
                upload_dir,
                GSTR2B_EXTENSIONS,
                kind="gstr2b",
            )
            temp_paths.append(gstr2b_file)

        with st.status(
            "Running reconciliation pipeline…", state="running"
        ) as status:
            result, decisions = _execute_pipeline(purchase_file, gstr2b_file)
            status.update(label="Pipeline complete", state="complete")

        st.session_state._reconciliation_result = result
        st.session_state._decisions = decisions
        st.session_state._metrics = compute_metrics(
            result, decisions, st.session_state.review_records
        )
        st.session_state._drafts = _generate_drafts(decisions)
        st.session_state._input_source = "sample" if use_sample else "custom"
        st.session_state._pipeline_done = True
        _record_event(
            AuditEventType.RUN_COMPLETED,
            (
                f"Reconciliation completed: {len(result.matches)} reconciliation "
                f"rows, {sum(1 for d in decisions if d.review_required)} requiring "
                "review"
            ),
            metadata={
                "row_count": len(result.matches),
                "review_required": sum(1 for d in decisions if d.review_required),
            },
        )
        st.rerun()
    except (UploadValidationError, IngestionError, OSError, ValueError) as exc:
        _record_event(
            AuditEventType.ERROR,
            f"Reconciliation failed: {type(exc).__name__}",
            metadata={"error_type": type(exc).__name__},
        )
        feedback_slot.error(f"Could not run reconciliation: {exc}")
    except Exception as exc:  # defensive: never leave a half-built run visible
        _record_event(
            AuditEventType.ERROR,
            f"Unexpected reconciliation failure: {type(exc).__name__}",
            metadata={"error_type": type(exc).__name__},
        )
        feedback_slot.error(
            "Reconciliation failed unexpectedly. Check the input files and try "
            f"again. ({type(exc).__name__})"
        )
    finally:
        cleanup_paths(temp_paths)


# ---------------------------------------------------------------------------
# Dashboard render helpers
# ---------------------------------------------------------------------------
def _render_overview(metrics: ReconciliationMetrics) -> None:
    section_header(
        "Reconciliation overview",
        "A clear view of matched invoices, discrepancies, and records awaiting "
        "human review.",
        eyebrow="Run summary",
    )
    st.caption(
        "All eligibility decisions remain provisional. Exact matches are "
        "candidates for review, not proof of ITC eligibility."
    )

    with st.container(key="itc-kpi-row"):
        col1, col2, col3, col4 = st.columns(4, gap="small")
        with col1:
            kpi_card(
                "Reconciliation rows",
                metrics.total_reconciliation_rows,
                "One row per matched pair or exception.",
            )
        with col2:
            kpi_card(
                "Confirmed matches (exact)",
                metrics.confirmed_matches,
                "Exact matches only; candidates are excluded.",
            )
        with col3:
            kpi_card(
                "Mismatches (amount + tax head)",
                metrics.amount_mismatches + metrics.tax_head_mismatches,
                "Differences on the same GSTIN and invoice.",
            )
        with col4:
            kpi_card(
                "Awaiting review",
                metrics.awaiting_review,
                "Review-required records without a decision.",
            )

    secondary_stats(
        [
            (
                "Review required",
                metrics.review_required,
                "Policy-required human reviews",
            ),
            (
                "Reviewed",
                metrics.reviewed_records,
                f"{metrics.review_completion_ratio:.0%} of review work",
            ),
            (
                "Fuzzy / probable",
                metrics.fuzzy_candidates + metrics.probable_candidates,
                "Candidates only — never confirmed",
            ),
            (
                "Data quality",
                metrics.duplicates + metrics.invalid_records,
                "Duplicate or invalid rows",
            ),
            (
                "Source rows",
                metrics.total_source_rows,
                "Purchase register + GSTR-2B",
            ),
        ]
    )

    if metrics.total_reconciliation_rows == 0:
        empty_state(
            "No reconciliation rows were produced",
            "The pipeline completed, but the inputs did not yield any "
            "reconciliation results. Check that both files contain invoice "
            "rows and that required columns are populated.",
            "Nothing is being inferred or fabricated to fill this view.",
        )

    with st.container(key="itc-overview-row"):
        left, right = st.columns([1.55, 1], gap="medium")
        with left:
            with st.container(border=True, key="itc-card-breakdown"):
                section_header(
                    "Match status breakdown",
                    "Counts by reconciliation result row. A matched pair is one "
                    "row. Candidates are never treated as confirmed matches.",
                    level=3,
                )
                status_breakdown(
                    [
                        (
                            "Exact matches (confirmed)",
                            metrics.confirmed_matches,
                            "positive",
                        ),
                        (
                            "Amount mismatches",
                            metrics.amount_mismatches,
                            "error",
                        ),
                        (
                            "Tax-head mismatches",
                            metrics.tax_head_mismatches,
                            "error",
                        ),
                        (
                            "Fuzzy candidates",
                            metrics.fuzzy_candidates,
                            "warning",
                        ),
                        (
                            "Probable candidates",
                            metrics.probable_candidates,
                            "warning",
                        ),
                        (
                            "Low-confidence candidates",
                            metrics.low_confidence_candidates,
                            "warning",
                        ),
                        ("Duplicate rows", metrics.duplicates, "critical"),
                        ("Invalid rows", metrics.invalid_records, "critical"),
                        (
                            "Unmatched — books",
                            metrics.unmatched_books,
                            "neutral",
                        ),
                        (
                            "Unmatched — GSTR-2B",
                            metrics.unmatched_gstr2b,
                            "neutral",
                        ),
                    ]
                )

        with right:
            with st.container(border=True, key="itc-card-review-progress"):
                section_header(
                    "Review progress",
                    "Latest review state per review-required record.",
                    level=3,
                )
                if metrics.review_required == 0:
                    st.progress(
                        0.0, text="No review-required records in this run"
                    )
                else:
                    st.progress(
                        metrics.review_completion_ratio,
                        text=(
                            f"{metrics.reviewed_records} of "
                            f"{metrics.review_required} review-required records "
                            "reviewed"
                        ),
                    )
                key_value_table(
                    "Latest state",
                    [
                        ("Reviewed", str(metrics.reviewed_records)),
                        ("Awaiting review", str(metrics.awaiting_review)),
                        ("Accepted", str(metrics.accepted)),
                        ("Rejected", str(metrics.rejected)),
                        ("Pending", str(metrics.pending)),
                    ],
                    plain=True,
                )

                if metrics.review_required == 0:
                    action_value = "No review work"
                    action_note = (
                        "Continue to Reports & audit to generate the Excel "
                        "workbook for this run."
                    )
                    action_tone = "neutral"
                elif metrics.awaiting_review > 0:
                    action_value = f"Review {metrics.awaiting_review} record(s)"
                    action_note = (
                        "Open Exceptions → Review queue to record a decision. "
                        "Permitted actions are enforced by the decision policy."
                    )
                    action_tone = "warning"
                else:
                    action_value = "Review complete"
                    action_note = (
                        "All review-required records have a decision. Generate "
                        "the workbook in Reports & audit."
                    )
                    action_tone = "neutral"
                callout(
                    "Next action",
                    action_value,
                    action_note,
                    tone=action_tone,
                )

    with st.container(key="itc-exposure-row"):
        exposure_col, safeguard_col = st.columns([1, 1.35], gap="medium")
        with exposure_col:
            callout(
                "Provisional exposure",
                format_inr(metrics.provisional_exposure),
                "Sum of decision exposure amounts. This is an estimate only — "
                "not a confirmed ITC impact. GST rules require CA verification.",
            )
        with safeguard_col:
            with st.container(border=True, key="itc-card-safeguards"):
                section_header("Safeguards in force", level=3)
                st.markdown(
                    '<ul class="itc-list">'
                    "<li>A match does not establish ITC eligibility; statuses "
                    "remain uncertain pending CA validation.</li>"
                    "<li>Exact matches are candidates and still require human "
                    "review.</li>"
                    "<li>Review actions are limited by the decision policy; "
                    "invalid rows cannot be approved.</li>"
                    "<li>No filing, payment hold, or vendor message is sent "
                    "automatically.</li>"
                    "<li>Vendor drafts are unapproved templates and remain "
                    "editable.</li>"
                    "<li>The local audit log is a demo trail, not tamper-proof "
                    "storage.</li>"
                    "</ul>",
                    unsafe_allow_html=True,
                )

    with st.expander("Metric definitions"):
        st.dataframe(
            pd.DataFrame(_metric_definition_rows(metrics)),
            width="stretch",
            hide_index=True,
            column_config={
                "KPI": st.column_config.TextColumn("KPI", width="medium"),
                "Count": st.column_config.NumberColumn(
                    "Count", format="%d", width="small"
                ),
                "Definition": st.column_config.TextColumn(
                    "Definition", width="large"
                ),
            },
        )

    with st.expander("Status definitions"):
        for status in MatchStatus:
            st.markdown(
                f"**{_STATUS_LABELS[status]}** — {_STATUS_NOTES[status]}"
            )


def _render_reconciliation_table(
    result: ReconciliationResult,
    decisions: list[DecisionResult],
) -> None:
    section_header(
        "Reconciliation results",
        "Every reconciliation row is listed, including invalid and unmatched "
        "records. Review-required rows are marked explicitly. Probable and "
        "low-confidence matches are never treated as confirmed.",
        eyebrow="Reconciliation",
    )

    df = _status_dataframe(result, decisions)
    if df.empty:
        empty_state(
            "No rows to display",
            "This run produced no reconciliation rows, so there is nothing to "
            "filter or inspect.",
        )
        return

    with st.container(key="itc-table-filters"):
        filter_col, review_col = st.columns(
            [1, 1], gap="medium", vertical_alignment="bottom"
        )
        with filter_col:
            available_statuses = list(dict.fromkeys(df["Status"]))
            selected_status = st.selectbox(
                "Match status",
                ["All statuses", *available_statuses],
                key="exception_status_filter_select",
                width=320,
            )
        with review_col:
            only_review = st.checkbox(
                "Review-required only",
                value=False,
                key="exception_review_only",
            )

    filtered = (
        df
        if selected_status == "All statuses"
        else df[df["Status"] == selected_status]
    )
    if only_review:
        filtered = filtered[filtered["Review"] == "Required"]

    if filtered.empty:
        empty_state(
            "No rows match these filters",
            "Adjust the status selection or clear the review-required filter "
            "to see the rest of the run.",
        )
    else:
        st.caption(
            f"Showing {len(filtered)} of {len(df)} reconciliation rows. "
            "Open the detail view for record IDs, confidence, and reasons."
        )
        # Present currency with the same Indian grouping used everywhere else
        # while keeping the raw numeric columns in the full detail view.
        display = filtered.copy()
        display["Taxable value (₹)"] = display["Taxable value (₹)"].map(
            format_inr
        )
        display["Amount difference (₹)"] = display[
            "Amount difference (₹)"
        ].map(format_inr)
        table_height = min(430, 40 + 35 * len(filtered))
        st.dataframe(
            display,
            width="stretch",
            height=table_height,
            hide_index=True,
            column_order=[
                "Invoice",
                "Vendor",
                "Status",
                "Review",
                "Taxable value (₹)",
                "Amount difference (₹)",
                "Discrepancies",
            ],
            column_config={
                "Invoice": st.column_config.TextColumn("Invoice", width=95),
                "Vendor": st.column_config.TextColumn("Vendor", width=145),
                "Status": st.column_config.TextColumn("Status", width=140),
                "Review": st.column_config.TextColumn("Review", width=85),
                "Taxable value (₹)": st.column_config.TextColumn(
                    "Taxable value", width=120, alignment="right"
                ),
                "Amount difference (₹)": st.column_config.TextColumn(
                    "Amount difference", width=135, alignment="right"
                ),
                "Discrepancies": st.column_config.TextColumn(
                    "Discrepancies", width=240
                ),
            },
        )
        with st.expander("Full row detail (all columns)"):
            st.dataframe(
                filtered,
                width="stretch",
                height=min(360, 40 + 35 * len(filtered)),
                hide_index=True,
            )

    st.caption(
        "A match does not establish ITC eligibility. All statuses map to "
        "eligibility_status = UNCERTAIN (except GSTR-2B-only rows, which are "
        "NOT_ASSESSED) pending CA verification."
    )


def _render_review_queue(
    decisions: list[DecisionResult],
    review_records: list[ReviewRecord],
    metrics: ReconciliationMetrics,
) -> None:
    flash = st.session_state.pop("_review_flash", None)
    if flash:
        st.success(flash)

    section_header(
        "Review queue",
        "Resolve policy-required exceptions. The permitted actions come from "
        "the decision layer; recording a review does not establish legal ITC "
        "eligibility.",
        eyebrow="Human review",
    )

    secondary_stats(
        [
            (
                "Review required",
                metrics.review_required,
                "Policy-required reviews",
            ),
            (
                "Reviewed",
                metrics.reviewed_records,
                f"{metrics.review_completion_ratio:.0%} complete",
            ),
            ("Awaiting", metrics.awaiting_review, "No decision recorded"),
            (
                "Latest state",
                f"{metrics.accepted} / {metrics.rejected} / {metrics.pending}",
                "Accepted / rejected / pending",
            ),
        ]
    )

    worklist = [d for d in decisions if d.review_required]
    if not worklist:
        empty_state(
            "No records require review",
            "Every record in this run is outside the human-review worklist "
            "defined by the decision policy.",
            "Continue to Reports & audit when you are ready to export.",
        )
        return

    decision_by_id = {
        record_identity(d.match_result): d for d in worklist
    }
    options = list(decision_by_id)
    default_index = next(
        (
            index
            for index, record_id in enumerate(options)
            if decision_by_id[record_id].match_result.purchase_record is not None
            and decision_by_id[record_id].match_result.gstr2b_record is not None
            and decision_by_id[record_id].match_result.discrepancies
        ),
        0,
    )

    selected_id = st.selectbox(
        "Select a record to review",
        options,
        index=default_index,
        format_func=lambda record_id: _display_label(
            decision_by_id[record_id]
        ),
        key="review_record_selector",
    )
    selected = decision_by_id[selected_id]
    match = selected.match_result
    book = match.purchase_record
    gstr2b = match.gstr2b_record

    previous_state = _latest_state_for(review_records, selected)
    chips: list[tuple[str, str]] = [
        (_STATUS_LABELS[match.match_status], _STATUS_TONES[match.match_status]),
        (f"Priority: {_PRIORITY_LABELS[selected.priority.value]}", "neutral"),
        (
            f"Eligibility: {selected.eligibility_status.value.upper()}",
            "warning",
        ),
    ]
    if previous_state != "none":
        state_tone = {
            "approve": "positive",
            "reject": "error",
            "pending": "warning",
        }.get(previous_state, "neutral")
        chips.append(
            (
                f"Current: {_REVIEW_ACTION_LABELS.get(previous_state, previous_state)}",
                state_tone,
            )
        )

    review_header(selected_id, chips)
    st.caption(_humanize_codes(match.reason))

    book_rows = _comparison_rows(book, gstr2b)
    gstr2b_rows = _comparison_rows(gstr2b, book)
    with st.container(key="itc-compare-row"):
        left, right = st.columns(2, gap="medium")
        with left:
            comparison_table(
                "Purchase register"
                if book is not None
                else "Purchase register (not present)",
                book_rows,
            )
        with right:
            comparison_table(
                "GSTR-2B" if gstr2b is not None else "GSTR-2B (not present)",
                gstr2b_rows,
            )

    with st.container(key="itc-detail-row"):
        detail_left, detail_right = st.columns(2, gap="medium")
        with detail_left:
            key_value_table(
                "Decision support",
                [
                    (
                        "Suggested action",
                        _ACTION_LABELS.get(
                            selected.action.value, selected.action.value
                        ),
                    ),
                    (
                        "Eligibility",
                        _ELIGIBILITY_LABELS.get(
                            selected.eligibility_status.value,
                            selected.eligibility_status.value,
                        ),
                    ),
                    ("Priority", _PRIORITY_LABELS[selected.priority.value]),
                    (
                        "Flags",
                        _discrepancy_text(
                            [flag.value for flag in selected.flags]
                        )
                        or "None",
                    ),
                    (
                        "Reason code",
                        _discrepancy_label(selected.reason_code.value),
                    ),
                ],
            )
        with detail_right:
            permitted = allowed_review_decisions(selected)
            invoice_key = _record_to_invoice_key(match) or "—"
            key_value_table(
                "Policy and traceability",
                [
                    (
                        "Review required",
                        "Yes" if selected.review_required else "No",
                    ),
                    (
                        "Permitted decisions",
                        ", ".join(
                            _REVIEW_ACTION_LABELS.get(item, item)
                            for item in permitted
                        ),
                    ),
                    (
                        "Current state",
                        _REVIEW_ACTION_LABELS.get(
                            previous_state, "Not reviewed"
                        ),
                    ),
                    ("Invoice key", invoice_key),
                    (
                        "Amount difference",
                        format_inr(match.amount_difference)
                        if match.amount_difference is not None
                        else "—",
                    ),
                ],
            )

    if match.discrepancies:
        st.markdown(
            "**Discrepancies:** "
            + _html_escape(_discrepancy_text(match.discrepancies))
        )
    st.caption(
        "Highlighted values differ between the purchase register and GSTR-2B. "
        "A difference is a review prompt, not proof of wrongdoing."
    )

    action_labels = {
        "approve": "✅ Approve",
        "reject": "❌ Reject",
        "pending": "⏳ Pending",
    }

    section_header("Record decision", level=3)
    st.caption(
        "Only decisions permitted by the policy are shown. Invalid rows cannot "
        "be approved. The outcome is an operational review state, not a legal "
        "eligibility determination."
    )

    with st.form(key=f"review_form_{selected_id}"):
        review_decision = st.radio(
            "Your decision",
            options=list(permitted),
            format_func=lambda value: action_labels[value],
            key=f"decision_radio_{selected_id}",
            horizontal=True,
        )
        with st.container(key="itc-form-row"):
            reason_col, name_col = st.columns([1.6, 1], gap="medium")
            with reason_col:
                reviewer_reason = st.text_area(
                    "Reviewer reason (optional)",
                    help="Recorded in the audit trail. Do not include secrets.",
                    height=120,
                    key=f"reason_{selected_id}",
                )
            with name_col:
                reviewer_name = st.text_input(
                    "Your name / identifier (optional)",
                    help="For audit traceability. Do not include secrets.",
                    key=f"reviewer_{selected_id}",
                )
        submitted = st.form_submit_button(
            "Record decision",
            key=f"submit_review_{selected_id}",
            type="primary",
        )

    if submitted:
        try:
            normalized = validate_review_decision(
                selected, review_decision
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            invoice_key = _record_to_invoice_key(match)
            review = ReviewRecord(
                review_id=str(uuid.uuid4()),
                run_id=st.session_state.run_id,
                invoice_key=invoice_key,
                match_status=match.match_status.value,
                suggested_action=selected.action.value,
                decision=normalized,
                reviewer_reason=reviewer_reason,
                reviewer_name=reviewer_name,
                timestamp=_utc_now_iso(),
                decision_metadata={
                    "record_id": selected_id,
                    "eligibility_status": selected.eligibility_status.value,
                    "priority": selected.priority.value,
                    "flags": [flag.value for flag in selected.flags],
                },
                record_id=selected_id,
                previous_state=previous_state,
                new_state=normalized,
            )
            st.session_state.review_records.append(review)
            # The previous workbook no longer reflects the review state.
            st.session_state._export_bytes = None
            st.session_state._export_meta = None
            st.session_state._export_audited = False
            _record_event(
                AuditEventType.REVIEW_ACTION,
                (
                    f"Review decision '{normalized}' for "
                    f"{match.match_status.value} record {selected_id} "
                    f"(previous: {previous_state})"
                ),
                invoice_key=invoice_key,
                metadata={
                    "review_id": review.review_id,
                    "record_id": selected_id,
                    "decision": normalized,
                    "previous_state": previous_state,
                    "new_state": normalized,
                    "match_status": match.match_status.value,
                },
            )
            st.session_state._review_flash = (
                f"Decision recorded: {_REVIEW_ACTION_LABELS.get(normalized, normalized)}. "
                "It is an operational review outcome, not a legal eligibility "
                "determination."
            )
            st.rerun()

    record_history = [
        record
        for record in review_records
        if record.record_id == selected_id
        or (
            not record.record_id
            and record.invoice_key
            and record.invoice_key == _record_to_invoice_key(match)
        )
    ]
    with st.expander(
        f"History for this record ({len(record_history)} action(s))"
    ):
        if record_history:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Decision": _REVIEW_ACTION_LABELS.get(
                                record.decision, record.decision
                            ),
                            "Previous": _REVIEW_ACTION_LABELS.get(
                                record.previous_state or "none",
                                record.previous_state or "none",
                            ),
                            "New": _REVIEW_ACTION_LABELS.get(
                                record.new_state or record.decision,
                                record.new_state or record.decision,
                            ),
                            "Reviewer": record.reviewer_name or "—",
                            "Reason": record.reviewer_reason or "—",
                            "Timestamp": record.timestamp,
                        }
                        for record in record_history
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.caption("No review actions have been recorded for this record.")

    section_header("Recorded review decisions", level=3)
    if review_records:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Review ID": rec.review_id[:8] + "…",
                        "Record ID": rec.record_id or "—",
                        "Invoice Key": rec.invoice_key or "—",
                        "Match Status": _STATUS_LABELS.get(
                            MatchStatus(rec.match_status)
                            if rec.match_status in MatchStatus._value2member_map_
                            else MatchStatus.INVALID,
                            rec.match_status,
                        ),
                        "Suggested Action": _ACTION_LABELS.get(
                            rec.suggested_action, rec.suggested_action
                        ),
                        "Previous": _REVIEW_ACTION_LABELS.get(
                            rec.previous_state or "none",
                            rec.previous_state or "none",
                        ),
                        "New": _REVIEW_ACTION_LABELS.get(
                            rec.new_state or rec.decision,
                            rec.new_state or rec.decision,
                        ),
                        "Reviewer": rec.reviewer_name or "—",
                        "Reason": rec.reviewer_reason or "—",
                        "Timestamp": rec.timestamp,
                    }
                    for rec in review_records
                ]
            ),
            width="stretch",
            height=260,
            hide_index=True,
        )
    else:
        empty_state(
            "No review decisions recorded",
            "Record a decision above to build the audit trail for this run.",
        )

    st.caption(
        "Reviews are scoped to this run. Each reconciliation request rotates "
        "the run ID and audit log, so data from different runs is not mixed. "
        "Closing the browser resets session state."
    )


def _render_vendor_drafts() -> None:
    section_header(
        "Vendor message drafts",
        "Deterministic templates based on reconciliation findings. Drafts "
        "require human review and editing; no email or message is sent "
        "automatically.",
        eyebrow="Communications",
    )

    drafts = st.session_state.get("_drafts", [])
    if not drafts:
        empty_state(
            "No vendor drafts for this run",
            "Drafts are created only for findings that map to a vendor "
            "communication category. This run produced none.",
            "Nothing is generated or sent in the background.",
        )
    else:
        secondary_stats(
            [
                ("Drafts created", len(drafts), "Unapproved templates"),
                (
                    "LLM enhanced",
                    sum(1 for draft in drafts if draft.llm_enhanced),
                    "Disabled by default",
                ),
                ("Delivery", "None", "Manual review required"),
            ]
        )

        for draft in drafts:
            category_label = _draft_category_label(draft.category)
            context = " · ".join(
                part
                for part in (
                    draft.vendor_name or "",
                    f"GSTIN {draft.gstin}" if draft.gstin else "",
                    f"Invoice {draft.invoice_number}"
                    if draft.invoice_number
                    else "",
                )
                if part
            )
            with st.expander(
                f"{category_label} · {context or 'Vendor draft'}"
            ):
                st.markdown(
                    f'<div class="itc-chip-row" style="justify-content:flex-start">'
                    f'{chip(category_label, "neutral")}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("**Subject**")
                st.code(draft.subject, language=None)
                st.text_area(
                    "Email body",
                    draft.body_email,
                    height=210,
                    key=f"email_{draft.draft_id}",
                )
                st.text_area(
                    "WhatsApp body",
                    draft.body_whatsapp,
                    height=120,
                    key=f"whatsapp_{draft.draft_id}",
                )
                st.markdown(f"**Notes:** {_html_escape(draft.notes)}")
                st.caption(
                    f"Draft ID: {draft.draft_id} · Template only · Editable · "
                    "LLM enhanced: No"
                )

    st.caption(
        "Drafts preserve the provisional, uncertain nature of the underlying "
        "reconciliation. They are not legal advice and must not be sent "
        "without human review."
    )


def _render_export_and_audit(
    decisions: list[DecisionResult],
    review_records: list[ReviewRecord],
) -> None:
    section_header(
        "Reports & audit",
        "Generate one workbook for this run, then download it. The audit trail "
        "is a local demo log, not durable or tamper-proof storage.",
        eyebrow="Reporting",
    )

    with st.container(key="itc-export-row"):
        export_col, contents_col = st.columns([1.3, 1], gap="medium")
        with export_col:
            with st.container(border=True, key="itc-card-export"):
                section_header("Excel workbook", level=3)
                st.markdown(
                    "The workbook uses the existing export implementation and "
                    "includes reconciliation results, decisions, review records, "
                    "vendor drafts, audit events, and metric definitions. Text "
                    "cells are protected against formula injection."
                )
                if st.button(
                    "Generate Excel workbook",
                    key="generate_export",
                    type=(
                        "secondary"
                        if st.session_state.get("_export_bytes")
                        else "primary"
                    ),
                ):
                    try:
                        _generate_workbook(decisions, review_records)
                    except Exception as exc:
                        st.error(f"Excel export failed: {exc}")

                export_meta = st.session_state.get("_export_meta")
                if export_meta:
                    st.success("Workbook generated for this run.")
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Sheet": sheet,
                                    "Rows": export_meta["row_counts"].get(
                                        sheet, 0
                                    ),
                                }
                                for sheet in export_meta["sheets"]
                            ]
                        ),
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Sheet": st.column_config.TextColumn(
                                "Sheet", width="medium"
                            ),
                            "Rows": st.column_config.NumberColumn(
                                "Rows", format="%d", width="small"
                            ),
                        },
                    )

                export_bytes = st.session_state.get("_export_bytes")
                if export_bytes:
                    st.download_button(
                        label="Download Excel workbook",
                        data=export_bytes,
                        file_name="ITC_Sentinel_Reconciliation.xlsx",
                        mime=(
                            "application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                        key="download_export",
                        type="primary",
                    )
                else:
                    st.caption(
                        "The download action appears after a workbook has been "
                        "generated for this run."
                    )

        with contents_col:
            with st.container(border=True, key="itc-card-contents"):
                section_header("What the workbook covers", level=3)
                st.markdown(
                    '<ul class="itc-list">'
                    "<li>Reconciliation rows and match statuses.</li>"
                    "<li>Decision support with provisional eligibility.</li>"
                    "<li>Human review records for this run.</li>"
                    "<li>Vendor drafts marked as unapproved templates.</li>"
                    "<li>Audit events and metric definitions.</li>"
                    "</ul>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "A workbook export does not establish ITC eligibility and does "
                    "not file anything with GST authorities."
                )

    section_header(
        "Audit trail",
        "Append-only local JSONL events for this run. No uploaded file "
        "contents are stored in the audit log.",
        eyebrow="Audit",
    )

    try:
        events = st.session_state.audit_log.read_events()
    except (FileNotFoundError, ValueError) as exc:
        events = []
        st.warning(f"Audit log could not be read: {exc}")

    if events:
        audit_rows = [
            {
                "Timestamp (UTC)": _format_audit_timestamp(event.timestamp),
                "Event": _AUDIT_EVENT_LABELS.get(
                    getattr(event.event_type, "value", event.event_type),
                    str(getattr(event.event_type, "value", event.event_type))
                    .replace("_", " ")
                    .title(),
                ),
                "Run": event.run_id[:8],
                "Invoice key": event.invoice_key or "—",
                "Summary": event.summary,
            }
            for event in events
        ]
        st.dataframe(
            pd.DataFrame(audit_rows),
            width="stretch",
            height=min(300, 40 + 34 * len(audit_rows)),
            hide_index=True,
            column_config={
                "Timestamp (UTC)": st.column_config.TextColumn(
                    "Timestamp (UTC)", width=160
                ),
                "Event": st.column_config.TextColumn("Event", width=120),
                "Run": st.column_config.TextColumn("Run", width=80),
                "Invoice key": st.column_config.TextColumn(
                    "Invoice key", width=170
                ),
                "Summary": st.column_config.TextColumn(
                    "Summary", width=420
                ),
            },
        )
    else:
        empty_state(
            "No audit events recorded",
            "Events appear as the run starts, completes, records reviews, or "
            "generates an export.",
        )

    st.caption(
        "The audit log is an append-only local JSONL file for demo purposes. "
        "It is not tamper-proof or legally compliant storage, and it contains "
        "no uploaded file contents. It may not survive a hosting restart."
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
if (
    st.session_state.get("_pipeline_done", False)
    and st.session_state.get("_reconciliation_result") is not None
):
    result: ReconciliationResult = st.session_state._reconciliation_result
    decisions: list[DecisionResult] = st.session_state._decisions
    review_records: list[ReviewRecord] = st.session_state.review_records
    metrics: ReconciliationMetrics = compute_metrics(
        result, decisions, review_records
    )
    st.session_state._metrics = metrics

    tab_summary, tab_exceptions, tab_messages, tab_export = st.tabs(
        [
            "📊 Summary",
            "⚠️ Exceptions",
            "📨 Vendor Messages",
            "📄 Export & Audit",
        ]
    )

    with tab_summary:
        _render_overview(metrics)

    with tab_exceptions:
        _render_reconciliation_table(result, decisions)
        st.markdown(
            '<div class="itc-section-divider"></div>',
            unsafe_allow_html=True,
        )
        _render_review_queue(decisions, review_records, metrics)

    with tab_messages:
        _render_vendor_drafts()

    with tab_export:
        _render_export_and_audit(decisions, review_records)


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
footer(__version__)

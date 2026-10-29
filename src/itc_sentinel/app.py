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
import uuid
from decimal import Decimal
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
from itc_sentinel.report import export_workbook
from itc_sentinel.uploads import (
    GSTR2B_EXTENSIONS,
    PURCHASE_EXTENSIONS,
    UploadValidationError,
    cleanup_paths,
    save_uploaded_file,
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ITC Sentinel — GST ITC Reconciliation MVP",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
    st.session_state._reconciliation_result = None
    st.session_state._decisions = None
    st.session_state._metrics = None
    st.session_state._drafts = []
    st.session_state._export_bytes = None
    st.session_state._export_audited = False

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
    gstin = (record.gstin or "—") if record is not None else "—"
    invoice = (record.invoice_number or "—") if record is not None else "—"
    side = "books" if match.purchase_record is not None else "2B"
    return (
        f"{_STATUS_LABELS[match.match_status]} · {gstin} | {invoice} "
        f"· {side} row {record_identity(match)}"
    )


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


def _status_dataframe(result: ReconciliationResult, decisions: list[DecisionResult]):
    decision_by_id = {
        record_identity(d.match_result): d for d in decisions
    }
    rows = []
    for match in result.matches:
        record_id = record_identity(match)
        decision = decision_by_id.get(record_id)
        record = match.purchase_record or match.gstr2b_record
        rows.append(
            {
                "Record ID": record_id,
                "GSTIN": (record.gstin or "") if record is not None else "",
                "Invoice #": (
                    record.invoice_number or ""
                    if record is not None
                    else ""
                ),
                "Source": "books" if match.purchase_record is not None else "2B",
                "Vendor": (
                    (match.purchase_record.vendor_name or "")
                    if match.purchase_record is not None
                    else ""
                ),
                "Match Status": match.match_status.value,
                "Confidence": (
                    f"{match.confidence:.2f}" if match.confidence else "N/A"
                ),
                "Amount Difference": (
                    str(match.amount_difference)
                    if match.amount_difference is not None
                    else "—"
                ),
                "Tax Head Mismatch": "Yes" if match.tax_head_difference else "No",
                "Discrepancies": (
                    "; ".join(match.discrepancies) if match.discrepancies else "—"
                ),
                "Review Required": (
                    "Yes" if decision is not None and decision.review_required else "No"
                ),
                "Reason": match.reason,
            }
        )
    columns = [
        "Record ID",
        "GSTIN",
        "Invoice #",
        "Source",
        "Vendor",
        "Match Status",
        "Confidence",
        "Amount Difference",
        "Tax Head Mismatch",
        "Discrepancies",
        "Review Required",
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


# ---------------------------------------------------------------------------
# Sidebar: input selection
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("ℹ️ About ITC Sentinel")
    st.markdown(
        f"""
        **ITC Sentinel** v{__version__}

        GST Input Tax Credit reconciliation MVP — deterministic Python pipeline,
        rule-based decision support, human review, template-based vendor drafts,
        and Excel export with audit trail.

        ⚠️ **Important disclaimers:**
        - This is a reconciliation and decision-support *demo*, not an automated
          GST filing system.
        - A match does **not** establish ITC eligibility. All eligibility statuses
          are **UNCERTAIN** pending Chartered Accountant verification of tax rules.
        - Exact matches are *candidates* for an ITC claim and still require
          human review.
        - A discrepancy alone does **not** establish wrongdoing.
        - Unverified tax assumptions are explicitly provisional.
        - LLM enhancement is opt-in and disabled by default. Drafts require human
          review before use. No emails or messages are sent automatically.
        - The append-only audit log is a local demo trail, not tamper-proof storage.
        - Do not upload real taxpayer data containing confidential credentials.
        """
    )

    st.title("📥 Input Data")
    use_sample = st.checkbox(
        "Use synthetic sample data",
        value=True,
        help="Loads the synthetic purchase register + GSTR-2B demo files.",
        key="use_sample_data",
    )

    if use_sample:
        purchase_upload = None
        gstr2b_upload = None
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

    run_clicked = st.button(
        "▶️ Run Reconciliation", type="primary", key="run_reconciliation"
    )


# ---------------------------------------------------------------------------
# Run reconciliation
# ---------------------------------------------------------------------------
if run_clicked:
    _start_new_run()
    temp_paths: list[str] = []
    try:
        if use_sample:
            purchase_file: str | Path = _sample_dir() / "purchase_register_synthetic.csv"
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
            "🔎 Running reconciliation pipeline…", state="running"
        ) as status:
            result, decisions = _execute_pipeline(purchase_file, gstr2b_file)
            status.update(label="Pipeline complete", state="complete")

        st.session_state._reconciliation_result = result
        st.session_state._decisions = decisions
        st.session_state._metrics = compute_metrics(
            result, decisions, st.session_state.review_records
        )
        st.session_state._drafts = _generate_drafts(decisions)
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
        st.error(f"Could not run reconciliation: {exc}")
    except Exception as exc:  # defensive: never leave a half-built run visible
        _record_event(
            AuditEventType.ERROR,
            f"Unexpected reconciliation failure: {type(exc).__name__}",
            metadata={"error_type": type(exc).__name__},
        )
        st.error(
            "Reconciliation failed unexpectedly. Check the input files and try "
            f"again. ({type(exc).__name__})"
        )
    finally:
        cleanup_paths(temp_paths)


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
        ["📊 Summary", "⚠️ Exceptions", "📨 Vendor Messages", "📄 Export & Audit"]
    )

    # ==================================================================
    # Summary
    # ==================================================================
    with tab_summary:
        st.title("📊 Reconciliation Summary")
        st.caption(
            "Counts are by reconciliation result row unless stated otherwise. "
            "A matched pair is one row. Mismatches are never counted as "
            "confirmed matches."
        )

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Reconciliation rows", metrics.total_reconciliation_rows)
        with col2:
            st.metric("Confirmed matches (exact)", metrics.confirmed_matches)
        with col3:
            st.metric(
                "Mismatches (amount + tax head)",
                metrics.amount_mismatches + metrics.tax_head_mismatches,
            )
        with col4:
            st.metric("Awaiting review", metrics.awaiting_review)

        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric(
                f"Reviewed ({metrics.review_completion_ratio:.0%})",
                metrics.reviewed_records,
            )
        with col6:
            st.metric("Review required", metrics.review_required)
        with col7:
            st.metric("Fuzzy / probable", metrics.fuzzy_candidates + metrics.probable_candidates)
        with col8:
            st.metric(
                "Exposure (provisional)",
                f"₹{metrics.provisional_exposure.quantize(Decimal('0.01'))}",
            )

        st.markdown("#### Match Status Breakdown")
        cols = st.columns(2)
        for index, status in enumerate(MatchStatus):
            with cols[index % 2]:
                count = (
                    metrics.confirmed_matches
                    if status == MatchStatus.EXACT
                    else {
                        MatchStatus.AMOUNT_MISMATCH: metrics.amount_mismatches,
                        MatchStatus.TAX_HEAD_MISMATCH: metrics.tax_head_mismatches,
                        MatchStatus.FUZZY: metrics.fuzzy_candidates,
                        MatchStatus.PROBABLE: metrics.probable_candidates,
                        MatchStatus.LOW_CONFIDENCE: metrics.low_confidence_candidates,
                        MatchStatus.UNMATCHED_BOOKS: metrics.unmatched_books,
                        MatchStatus.UNMATCHED_GSTR2B: metrics.unmatched_gstr2b,
                        MatchStatus.DUPLICATE: metrics.duplicates,
                        MatchStatus.INVALID: metrics.invalid_records,
                    }[status]
                )
                st.markdown(f"**{_STATUS_LABELS[status]}** ({count})")
                st.caption(_STATUS_NOTES[status])

        st.markdown("#### Metric Definitions")
        st.dataframe(
            pd.DataFrame(_metric_definition_rows(metrics)),
            width="stretch",
            hide_index=True,
        )

        st.markdown("#### Provisional Exposure Estimate")
        st.info(
            f"Sum of provisional exposure amounts across all decisions: "
            f"₹{metrics.provisional_exposure.quantize(Decimal('0.01'))}. "
            "This is a *provisional estimate only* — not a confirmed ITC impact. "
            "GST rules require CA verification before being treated as reliable "
            "(rule R-CALC-TAX-EXPOSURE pending CA verification)."
        )

        st.warning(
            "- A match does **not** establish ITC eligibility. All eligibility "
            "statuses are **UNCERTAIN** pending CA review of tax rules.\n"
            "- An exact match is only a *candidate* for an ITC claim and still "
            "requires human review.\n"
            "- A discrepancy alone does **not** establish wrongdoing.\n"
            "- No automated filing, payment holds, or vendor message sending is "
            "performed."
        )

    # ==================================================================
    # Exceptions / worklist
    # ==================================================================
    with tab_exceptions:
        st.title("⚠️ Exception Worklist")
        st.markdown(
            "Every reconciliation row is listed below, including invalid and "
            "unmatched records. Review-required rows are marked explicitly. "
            "Probable and low-confidence matches are never treated as confirmed."
        )

        df = _status_dataframe(result, decisions)
        st.dataframe(df, width="stretch", height=420)

        available_statuses = sorted(df["Match Status"].unique()) if not df.empty else []
        selected_statuses = st.multiselect(
            "Filter by match status",
            available_statuses,
            default=available_statuses,
            key="exception_status_filter",
        )
        if selected_statuses:
            st.dataframe(
                df[df["Match Status"].isin(selected_statuses)],
                width="stretch",
                height=360,
            )
        else:
            st.info("No statuses selected.")

        only_review = st.checkbox(
            "Show only review-required rows",
            value=False,
            key="exception_review_only",
        )
        if only_review:
            st.dataframe(
                df[df["Review Required"] == "Yes"],
                width="stretch",
                height=360,
            )

        st.caption(
            "A match does not establish ITC eligibility. All statuses map to "
            "`eligibility_status = UNCERTAIN` (except GSTR-2B-only rows, which "
            "are NOT_ASSESSED) pending CA verification."
        )

    # ==================================================================
    # Vendor messages
    # ==================================================================
    with tab_messages:
        st.title("📨 Vendor Message Drafts")
        st.markdown(
            "Deterministic templates based on reconciliation findings. Drafts "
            "require human review and editing. No emails or messages are sent "
            "automatically. LLM enhancement is disabled by default."
        )

        drafts = st.session_state.get("_drafts", [])
        if not drafts:
            st.info("No vendor drafts available for the current results.")
        else:
            st.write(
                f"Created {len(drafts)} draft(s). Each requires human review and "
                "editing before use."
            )
            for draft in drafts:
                with st.expander(
                    f"{draft.category} · GSTIN {draft.gstin or '—'} · "
                    f"Invoice {draft.invoice_number or '—'}"
                ):
                    st.markdown(f"**Subject:** {draft.subject}")
                    st.text_area(
                        "Email body",
                        draft.body_email,
                        height=220,
                        key=f"email_{draft.draft_id}",
                    )
                    st.text_area(
                        "WhatsApp body",
                        draft.body_whatsapp,
                        height=120,
                        key=f"whatsapp_{draft.draft_id}",
                    )
                    st.markdown(f"**Notes:** {draft.notes}")
                    st.caption(
                        f"Draft ID: {draft.draft_id} · Template only · "
                        "Editable · LLM enhanced: No"
                    )

        st.warning(
            "- Drafts are templates only and must be reviewed and edited.\n"
            "- No external communication is sent.\n"
            "- Drafts preserve the provisional, uncertain nature of the "
            "underlying reconciliation."
        )

    # ==================================================================
    # Export & audit
    # ==================================================================
    with tab_export:
        st.title("📄 Export & Audit")

        st.subheader("Excel Workbook Export")
        if st.button("Generate Excel workbook", key="generate_export"):
            export_path = (
                _runs_root()
                / st.session_state.run_id
                / "reconciliation.xlsx"
            )
            try:
                export_result = export_workbook(
                    str(export_path),
                    decisions,
                    drafts=st.session_state.get("_drafts", []),
                    review_records=review_records,
                    audit_events=st.session_state.audit_log.read_events(),
                    settings=DecisionSettings(),
                )
                st.session_state._export_bytes = Path(export_result.path).read_bytes()
                if not st.session_state.get("_export_audited", False):
                    _record_event(
                        AuditEventType.EXPORT_CREATED,
                        f"Excel workbook exported with {len(export_result.sheets)} sheets",
                        metadata={"sheets": ",".join(export_result.sheets)},
                    )
                    st.session_state._export_audited = True
                st.success(f"Workbook generated: {export_result.path}")
                st.caption(
                    "Sheets: "
                    + ", ".join(
                        f"{name} ({export_result.row_counts.get(name, 0)} rows)"
                        for name in export_result.sheets
                    )
                )
            except Exception as exc:
                st.error(f"Excel export failed: {exc}")

        export_bytes = st.session_state.get("_export_bytes")
        if export_bytes:
            st.download_button(
                label="▶️ Download Excel workbook",
                data=export_bytes,
                file_name="ITC_Sentinel_Reconciliation.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                key="download_export",
            )

        st.subheader("🗂️ Audit Trail (Local Demo)")
        try:
            events = st.session_state.audit_log.read_events()
        except (FileNotFoundError, ValueError) as exc:
            events = []
            st.warning(f"Audit log could not be read: {exc}")

        if events:
            audit_rows = [
                {
                    "Event ID": event.event_id[:8] + "…",
                    "Timestamp": event.timestamp,
                    "Event Type": event.event_type,
                    "Run ID": event.run_id[:8] + "…",
                    "Invoice Key": event.invoice_key or "—",
                    "Summary": event.summary,
                }
                for event in events
            ]
            st.dataframe(
                pd.DataFrame(audit_rows),
                width="stretch",
                height=300,
            )
        else:
            st.info("No audit events recorded yet.")

        st.caption(
            "The audit log is an append-only local JSONL file for demo purposes. "
            "It is not tamper-proof or legally compliant storage, and it contains "
            "no uploaded file contents."
        )

        # --- Review decisions -----------------------------------------
        st.subheader("✏️ Record Review Decision")
        st.markdown(
            "Only records whose decision sets `review_required=True` appear here. "
            "The action list is controlled by the decision policy. Recording an "
            "approval does not establish legal ITC eligibility."
        )

        worklist = [d for d in decisions if d.review_required]
        if not worklist:
            st.info("No records currently require review.")
        else:
            decision_by_id = {
                record_identity(d.match_result): d for d in worklist
            }
            options = list(decision_by_id)

            selected_id = st.selectbox(
                "Select a record to review",
                options,
                format_func=lambda record_id: _display_label(
                    decision_by_id[record_id]
                ),
                key="review_record_selector",
            )
            selected = decision_by_id[selected_id]
            match = selected.match_result
            book = match.purchase_record
            gstr2b = match.gstr2b_record

            st.markdown(
                f"**Record {selected_id}** · "
                f"Status: `{match.match_status.value}` · "
                f"Suggested action: `{selected.action.value}` · "
                f"Eligibility: `{selected.eligibility_status.value}`"
            )
            st.caption(match.reason)

            evidence_col1, evidence_col2 = st.columns(2)
            with evidence_col1:
                st.markdown("**Purchase register**")
                if book is None:
                    st.write("— (GSTR-2B only record)")
                else:
                    st.write(
                        {
                            "gstin": book.gstin,
                            "invoice": book.invoice_number,
                            "date": str(book.invoice_date) if book.invoice_date else None,
                            "taxable_value": str(book.taxable_value)
                            if book.taxable_value is not None
                            else None,
                            "cgst": str(book.cgst) if book.cgst is not None else None,
                            "sgst": str(book.sgst) if book.sgst is not None else None,
                            "igst": str(book.igst) if book.igst is not None else None,
                            "cess": str(book.cess) if book.cess is not None else None,
                        }
                    )
            with evidence_col2:
                st.markdown("**GSTR-2B**")
                if gstr2b is None:
                    st.write("— (no GSTR-2B counterpart)")
                else:
                    st.write(
                        {
                            "gstin": gstr2b.gstin,
                            "invoice": gstr2b.invoice_number,
                            "date": str(gstr2b.invoice_date)
                            if gstr2b.invoice_date
                            else None,
                            "taxable_value": str(gstr2b.taxable_value)
                            if gstr2b.taxable_value is not None
                            else None,
                            "cgst": str(gstr2b.cgst)
                            if gstr2b.cgst is not None
                            else None,
                            "sgst": str(gstr2b.sgst)
                            if gstr2b.sgst is not None
                            else None,
                            "igst": str(gstr2b.igst)
                            if gstr2b.igst is not None
                            else None,
                            "cess": str(gstr2b.cess)
                            if gstr2b.cess is not None
                            else None,
                        }
                    )

            if match.discrepancies:
                st.markdown(
                    "**Discrepancies:** " + ", ".join(match.discrepancies)
                )
            if match.amount_difference is not None:
                st.markdown(
                    f"**Amount difference (books − 2B):** "
                    f"{match.amount_difference}"
                )

            previous_state = _latest_state_for(review_records, selected)
            if previous_state != "none":
                st.info(f"Current review state for this record: `{previous_state}`")
            else:
                st.caption("This record has not been reviewed yet.")

            permitted = allowed_review_decisions(selected)
            action_labels = {
                "approve": "✅ Approve",
                "reject": "❌ Reject",
                "pending": "⏳ Pending",
            }

            with st.form(key=f"review_form_{selected_id}"):
                review_decision = st.radio(
                    "Your decision",
                    options=list(permitted),
                    format_func=lambda value: action_labels[value],
                    key=f"decision_radio_{selected_id}",
                )
                reviewer_reason = st.text_area(
                    "Reviewer reason (optional)",
                    help="Recorded in the audit trail. Do not include secrets.",
                    key=f"reason_{selected_id}",
                )
                reviewer_name = st.text_input(
                    "Your name / identifier (optional)",
                    help="For audit traceability. Do not include secrets.",
                    key=f"reviewer_{selected_id}",
                )
                submitted = st.form_submit_button(
                    "💾 Record decision", key=f"submit_review_{selected_id}"
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
                    st.success(
                        f"Review decision recorded: {normalized}. It is an "
                        "operational review outcome, not a legal eligibility "
                        "determination."
                    )
                    st.rerun()

        st.markdown("#### Recorded Review Decisions")
        if review_records:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Review ID": rec.review_id[:8] + "…",
                            "Record ID": rec.record_id or "—",
                            "Invoice Key": rec.invoice_key or "—",
                            "Match Status": rec.match_status,
                            "Suggested Action": rec.suggested_action,
                            "Previous": rec.previous_state or "none",
                            "New": rec.new_state or rec.decision,
                            "Reviewer": rec.reviewer_name or "—",
                            "Reason": rec.reviewer_reason,
                            "Timestamp": rec.timestamp,
                        }
                        for rec in review_records
                    ]
                ),
                width="stretch",
                height=260,
            )
        else:
            st.info("No review decisions recorded for this run.")

        st.caption(
            "Reviews are scoped to this run. Each reconciliation request rotates "
            "the run ID and audit log, so data from different runs is not mixed. "
            "Closing the browser resets session state."
        )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.caption(
    f"ITC Sentinel v{__version__} · Synthetic-data MVP · "
    "Decision support only — not a GST filing system"
)

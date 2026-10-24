"""ITC Sentinel — Streamlit MVP UI (Phase 5).

Provides the complete end-to-end user workflow for GST ITC reconciliation:
- File upload for purchase register (CSV/XLSX) and GSTR-2B JSON
- Deterministic reconciliation using existing pipeline modules
- Decision support, review workflow, vendor drafts, and Excel export
- Clear disclaimers and uncertainty labeling throughout
"""

from __future__ import annotations

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
from itc_sentinel.decision import DecisionSettings, decide
from itc_sentinel.ingest import load_gstr2b_json, load_purchase_register
from itc_sentinel.matcher import MatchStatus, ReconciliationSettings, reconcile
from itc_sentinel.messages import _decision_to_category, draft_vendor_message
from itc_sentinel.normalize import normalize_records
from itc_sentinel.report import export_workbook

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ITC Sentinel — GST ITC Reconciliation MVP",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session-state initialisation (once per Streamlit run)
# ---------------------------------------------------------------------------
if "run_id" not in st.session_state:
    st.session_state.run_id = str(uuid.uuid4())

if "audit_log_path" not in st.session_state:
    runs_dir = Path("data/runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    st.session_state.audit_log_path = str(
        runs_dir / f"{st.session_state.run_id}/audit.jsonl"
    )
    st.session_state.audit_log = new_audit_log(st.session_state.audit_log_path)

    st.session_state.review_records: list[ReviewRecord] = []

    # Audit: record run start
    st.session_state.audit_log.append(
        AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=_utc_now_iso(),
            event_type=AuditEventType.RUN_STARTED,
            run_id=st.session_state.run_id,
            summary="Streamlit session started",
        )
    )


# ---------------------------------------------------------------------------
# Disclaimer banner (sidebar)
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
        - A discrepancy alone does **not** establish wrongdoing.
        - Unverified tax assumptions are explicitly provisional.
        - LLM enhancement is opt-in and disabled by default. Drafts require human
          review before use. No emails or messages are sent automatically.
        - The append-only audit log is a local demo trail, not tamper-proof storage.
        - Do not upload real taxpayer data containing confidential credentials.
        """
    )


# ---------------------------------------------------------------------------
# Sidebar: file input / sample data selector
# ---------------------------------------------------------------------------
st.sidebar.title("📥 Input Data")

use_sample = st.sidebar.checkbox(
    "Use synthetic sample data", value=True,
    help="Loads synthetic purchase_register + GSTR-2B for demo purposes."
)

if use_sample:
    purchase_path = "data/sample/purchase_register_synthetic.csv"
    gstr2b_path = "data/sample/gstr2b_synthetic.json"
else:
    purchase_path = st.sidebar.file_uploader(
        "Purchase register (CSV or XLSX)",
        type=["csv", "xlsx"],
        help="Supported columns: gstin, invoice_number, invoice_date, taxable_value, cgst, sgst, igst, cess, vendor_name",
    )
    gstr2b_path = st.sidebar.file_uploader(
        "GSTR-2B JSON",
        type=["json"],
        help="Supported structure: {gstin, period, invoices:[{supplier_gstin, invoice_number, invoice_date, taxable_value, cgst, sgst, igst, cess, invoice_type}]}",
    )

# ---------------------------------------------------------------------------
# Run reconciliation action
# ---------------------------------------------------------------------------
if st.sidebar.button("▶️ Run Reconciliation", type="primary"):

    purchase_file = (
        purchase_path if use_sample else str(purchase_path)
        if isinstance(purchase_path, str) else None
    )
    gstr2b_file = (
        gstr2b_path if use_sample else str(gstr2b_path)
        if isinstance(gstr2b_path, str) else None
    )

    if purchase_file is None or gstr2b_file is None:
        st.sidebar.error("Please select/upload both files before running reconciliation.")
    else:
        with st.status("🔎 Running reconciliation pipeline…", state="running") as status:

            # 1. Ingest
            try:
                pr_result = load_purchase_register(purchase_file)
                gb_result = load_gstr2b_json(gstr2b_file)
                st.write(f"Purchase register: {pr_result.row_count} raw records")
                st.write(f"GSTR-2B: {gb_result.row_count} raw records")
            except Exception as e:
                st.sidebar.error(f"Ingestion failed: {e}")
                status.update(label="Ingestion failed", state="error")
                st.stop()

            # 2. Normalize
            try:
                purchase_normalized = normalize_records(
                    pr_result.raw_records,
                    pr_result.source_type,
                    pr_result.source_file,
                )
                gstr2b_normalized = normalize_records(
                    gb_result.raw_records,
                    gb_result.source_type,
                    gb_result.source_file,
                )
            except Exception as e:
                st.sidebar.error(f"Normalization failed: {e}")
                status.update(label="Normalization failed", state="error")
                st.stop()

            st.write(f"Purchase normalized: {len(purchase_normalized)} records")
            st.write(f"GSTR-2B normalized: {len(gstr2b_normalized)} records")

            # 3. Reconcile
            try:
                result = reconcile(
                    purchase_normalized,
                    gstr2b_normalized,
                    ReconciliationSettings(),
                )
            except Exception as e:
                st.sidebar.error(f"Reconciliation failed: {e}")
                status.update(label="Reconciliation failed", state="error")
                st.stop()

            # 4. Decide
            try:
                decisions = [
                    decide(m, decision_settings=DecisionSettings())
                    for m in result.matches
                ]
            except Exception as e:
                st.sidebar.error(f"Decision support failed: {e}")
                status.update(label="Decision support failed", state="error")
                st.stop()

            # 5. Audit: record run completion
            st.session_state.audit_log.append(
                AuditEvent(
                    event_id=str(uuid.uuid4()),
                    timestamp=_utc_now_iso(),
                    event_type=AuditEventType.RUN_COMPLETED,
                    run_id=st.session_state.run_id,
                    summary="Reconciliation run completed",
                )
            )

            # 6. Store everything in session state
            st.session_state._reconciliation_result = result
            st.session_state._decisions = decisions
            st.session_state._pipeline_done = True

            status.update(label="Pipeline complete", state="complete")

        st.rerun()


# ---------------------------------------------------------------------------
# If pipeline has completed, show the dashboard tabs
# ---------------------------------------------------------------------------
if st.session_state.get("_pipeline_done", False) and st.session_state.get("_reconciliation_result", None) is not None:

    result = st.session_state._reconciliation_result
    decisions = st.session_state._decisions

    # ---- Build summary stats ----
    summary = result.summary
    total_rows = len(result.matches)
    review_required_count = sum(1 for d in decisions if d.review_required)
    exposure_total = sum(
        (d.exposure_amount for d in decisions if d.exposure_amount is not None),
        Decimal("0"),
    )

    # ------------------------------------------------------------------
    # TAB LAYOUT
    # ------------------------------------------------------------------
    tab_summary, tab_exceptions, tab_messages, tab_export = st.tabs(
        ["📊 Summary", "⚠️ Exceptions", "📨 Vendor Messages", "📄 Export & Audit"]
    )

    # ==================================================================
    # TAB 1: SUMMARY
    # ==================================================================
    with tab_summary:
        st.title("📊 Reconciliation Summary")

        # KPI row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Records", total_rows)
        with col2:
            confirmed = (
                summary.get("exact", 0)
                + summary.get("amount_mismatch", 0)
                + summary.get("tax_head_mismatch", 0)
                + summary.get("fuzzy", 0)
            )
            st.metric("Confirmed Matches", confirmed)
        with col3:
            st.metric("Under Review", review_required_count)
        with col4:
            st.metric(
                "Exposure (provisional)",
                f"₹{exposure_total.quantize(Decimal('0.01'))}",
            )

        st.markdown("#### Match Status Breakdown")
        status_labels = {
            "exact": (
                "Exact Matches",
                "Same GSTIN, invoice number, date, and amounts. ITC claim is "
                "*provisional*—matching is not proof of eligibility.",
            ),
            "amount_mismatch": (
                "Amount Mismatches",
                "Same GSTIN and invoice number, but monetary values differ. "
                "Requires vendor clarification.",
            ),
            "tax_head_mismatch": (
                "Tax-Head Mismatches",
                "Same GSTIN and invoice number, but tax is under a different head "
                "(domestic CGST/SGST vs IGST). Flag for review.",
            ),
            "fuzzy": (
                "Fuzzy Matches",
                "Invoice numbers share an alphanumeric core but differ in formatting. "
                "Verify invoice identity before claiming ITC.",
            ),
            "probable": (
                "Probable Matches",
                "Low-confidence similarity-based match. **Not a confirmed match**—"
                "requires human review before any ITC action.",
            ),
            "low_confidence": (
                "Low-Confidence Matches",
                "Auto-detected below confidence threshold. **Requires human review**—"
                "do not treat as certain.",
            ),
            "duplicate": (
                "Duplicates",
                "Duplicate purchase-register row (same GSTIN + invoice). May cause "
                "double claiming.",
            ),
            "invalid": (
                "Invalid Records",
                "Row failed Phase 1 validation. Preserved for review; no ITC action "
                "possible.",
            ),
            "unmatched_books": (
                "Unmatched (Books)",
                "No matching GSTR-2B invoice found. May affect ITC claim; requires "
                "human review.",
            ),
            "unmatched_gstr2b": (
                "Unmatched (GSTR-2B)",
                "No matching purchase-register invoice (GSTR-2B only). No books-side "
                "action required.",
            ),
        }

        cols = st.columns(2)
        for idx, (status_key, (label, note)) in enumerate(status_labels.items()):
            with cols[idx % 2]:
                count = summary.get(status_key, 0)
                st.markdown(f"**{label}** ({count})")
                st.caption(note)

        st.markdown("#### Provisional Exposure Estimate")
        st.info(
            f"Sum of provisional exposure amounts across all decisions: "
            f"₹{exposure_total.quantize(Decimal('0.01'))}. "
            "This is a *provisional estimate only*—not a confirmed ITC impact. "
            "GST rules require CA verification before being treated as reliable "
            "(rule R-CALC-TAX-EXPOSURE pending CA verification)."
        )

        st.markdown("#### Uncertainty & Disclaimer")
        st.warning(
            "- A match does **not** establish ITC eligibility. All eligibility statuses are "
            "**UNCERTAIN** pending CA review of tax rules.\n"
            "- A discrepancy alone does **not** establish wrongdoing.\n"
            "- All decision outputs are provisional and advisory. No automated filing, "
            "payment holds, or vendor message sending is performed."
        )

    # ==================================================================
    # TAB 2: EXCEPTIONS / WORKLIST
    # ==================================================================
    with tab_exceptions:
        st.title("⚠️ Exception Worklist")

        st.markdown(
            "Filter and inspect reconciliation exceptions. "
            "Probable and low-confidence matches are never treated as confirmed. "
            "Keep uncertain and invalid records visible for review."
        )

        # Build rows for the data table
        rows = []
        for m in result.matches:
            book = m.purchase_record
            gstr2b = m.gstr2b_record

            if book is not None:
                gstin = book.gstin or ""
                inv = book.invoice_number or ""
                source = "books"
                vendor = book.vendor_name or ""
            else:
                gstin = gstr2b.gstin or ""
                inv = gstr2b.invoice_number or ""
                source = "2b"
                vendor = ""

            rows.append({
                "GSTIN": gstin,
                "Invoice #": inv,
                "Source": source,
                "Vendor": vendor,
                "Match Status": m.match_status.value,
                "Confidence": f"{m.confidence:.2f}" if m.confidence else "N/A",
                "Amount Difference": str(m.amount_difference) if m.amount_difference else "—",
                "Tax Head Mismatch": "Yes" if m.tax_head_difference else "No",
                "Discrepancies": "; ".join(m.discrepancies) if m.discrepancies else "—",
                "Reason": m.reason,
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, height=500)

        st.markdown("#### Filter by match status")
        available_statuses = sorted(df["Match Status"].unique())
        selected_statuses = st.multiselect(
            "Show only",
            available_statuses,
            default=[s for s in available_statuses if s not in {"probable", "low_confidence"}],
        )
        filtered_df = df[df["Match Status"].isin(selected_statuses)] if selected_statuses else df
        st.dataframe(filtered_df, use_container_width=True, height=400)

        st.caption(
            "Note: 'probable' and 'low_confidence' matches are uncertain by design. "
            "A match does not establish ITC eligibility. All statuses map to "
            "`eligibility_status = UNCERTAIN` pending CA verification."
        )

    # ==================================================================
    # TAB 3: VENDOR MESSAGES
    # ==================================================================
    with tab_messages:
        st.title("📨 Vendor Message Drafts")

        st.markdown(
            "Draft messages for vendors based on reconciliation findings. "
            "Drafts are **deterministic templates**—they require human review and "
            "editing before use. No emails or messages are sent automatically. "
            "LLM enhancement is disabled by default; template fallback is used."
        )

        # Build drafts for all decisions that have a supported category
        drafts_created: list = []

        for d in decisions:
            try:
                category = _decision_to_category(d)
                if category is None:
                    continue
                draft = draft_vendor_message(d, enhanced_by_llm=False)
                drafts_created.append(draft)
            except ValueError:
                # Skip unsupported categories
                continue

        if not drafts_created:
            st.info("No vendor drafts available for the current reconciliation results.")
        else:
            st.write(f"Created {len(drafts_created)} draft(s). Each requires human review and editing.")
            for draft in drafts_created:
                with st.expander(
                    f"Category: {draft.category} | GSTIN: {draft.gstin or '—'} | "
                    f"Invoice: {draft.invoice_number or '—'}"
                ):
                    st.markdown(f"**Subject:** {draft.subject}")
                    st.markdown("**Email body:**")
                    st.text_area(
                        f"email_{draft.draft_id}",
                        draft.body_email,
                        height=250,
                        key=f"email_{draft.draft_id}",
                    )
                    st.markdown("**WhatsApp body:**")
                    st.text_area(
                        f"whatsapp_{draft.draft_id}",
                        draft.body_whatsapp,
                        height=150,
                        key=f"whatsapp_{draft.draft_id}",
                    )
                    st.markdown(f"**Notes:** {draft.notes}")
                    st.caption(
                        f"Draft ID: {draft.draft_id} | "
                        f"Category: {draft.category} | "
                        f"LLM Enhanced: {draft.llm_enhanced} (disabled by default) | "
                        f"Editable: {draft.editable} — always edit before use."
                    )

        st.markdown("#### Disclaimer")
        st.warning(
            "- Drafts are **templates only** — they require human review and editing. "
            "- No emails, WhatsApp messages, or other external communications are sent "
            "automatically.\n"
            "- LLM enhancement is opt-in and disabled by default. Template fallback is used. "
            "- Drafts must not be sent without independent verification of invoice details. "
            "- All drafts preserve the provisional, uncertain nature of the underlying "
            "reconciliation."
        )

    # ==================================================================
    # TAB 4: EXPORT & AUDIT
    # ==================================================================
    with tab_export:
        st.title("📄 Export & Audit")

        st.markdown(
            "Download the Excel workbook and review the audit trail for the current run."
        )

        # --- Excel Export ---
        st.subheader("Excel Workbook Export")

        if decisions:
            export_path = f"data/runs/{st.session_state.run_id}/reconciliation.xlsx"

            with st.spinner("📊 Generating Excel workbook…"):
                try:
                    export_result = export_workbook(
                        export_path,
                        decisions,
                        drafts=None,
                        review_records=st.session_state.review_records,
                        audit_events=st.session_state.audit_log.read_events(),
                        settings=DecisionSettings(),
                    )
                    st.success(f"Workbook exported: {export_result.path}")

                    # Download button
                    import base64
                    with open(export_result.path, "rb") as f:
                        wb_bytes = f.read()
                    b64 = base64.b64encode(wb_bytes).decode()
                    mime = (
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    )
                    st.download_button(
                        label="▶️ Download Excel Workbook",
                        data=wb_bytes,
                        file_name="ITC_Sentinel_Reconciliation.xlsx",
                        mime=mime,
                    )

                    # Sheet summary
                    st.markdown("#### Workbook Sheets")
                    for sheet_name in export_result.sheets:
                        st.markdown(
                            f"- **{sheet_name}** "
                            f"({export_result.row_counts.get(sheet_name, 0)} data rows)"
                        )

                except Exception as e:
                    st.error(f"Excel export failed: {e}")
        else:
            st.info("No decisions to export. Run reconciliation first.")

        # --- Audit Log ---
        st.subheader("🗂️ Audit Trail (Local Demo)")

        if st.session_state.audit_log:
            events = st.session_state.audit_log.read_events()
            audit_rows = []
            for e in events:
                invoice_key_str = (
                    f"{e.invoice_key}" if e.invoice_key else "-"
                )
                audit_rows.append({
                    "Event ID": e.event_id[:8] + "...",
                    "Timestamp": e.timestamp,
                    "Event Type": e.event_type,
                    "Run ID": e.run_id,
                    "Invoice Key": invoice_key_str,
                    "Summary": e.summary,
                })

            adf = pd.DataFrame(audit_rows)
            st.dataframe(adf, use_container_width=True, height=400)

            st.caption(
                "The audit log is an append-only local JSONL file for demo purposes. "
                "It is **not** tamper-proof or legally compliant storage. "
                "No secrets or real taxpayer data are included."
            )

        # --- Review Decision Recording ---
        st.subheader("✏️ Record Review Decision")

        st.markdown(
            "Select a reconciliation record and record your human decision. "
            "This preserves the original machine-generated result and adds your "
            "review judgment with required identifiers."
        )

        if st.session_state.get("_reconciliation_result", None) is not None:
            result = st.session_state._reconciliation_result

            # Build selector options from reviewable records
            reviewable = []
            for m in result.matches:
                if m.match_status in {
                    MatchStatus.UNMATCHED_BOOKS,
                    MatchStatus.LOW_CONFIDENCE,
                    MatchStatus.AMOUNT_MISMATCH,
                    MatchStatus.TAX_HEAD_MISMATCH,
                    MatchStatus.DUPLICATE,
                    MatchStatus.INVALID,
                }:
                    gstin = ""
                    inv = ""
                    if m.purchase_record is not None:
                        gstin = m.purchase_record.gstin or ""
                        inv = m.purchase_record.invoice_number or ""
                    elif m.gstr2b_record is not None:
                        gstin = m.gstr2b_record.gstin or ""
                        inv = m.gstr2b_record.invoice_number or ""
                    reviewable.append((f"{gstin} | {inv}", m.match_status.value))

            if reviewable:
                # Use session state to persist selection
                if "review_selector_idx" not in st.session_state:
                    st.session_state.review_selector_idx = 0

                # Find index safely
                try:
                    indices = [r[0] for r in reviewable]
                    if st.session_state.review_selector_idx < len(indices):
                        selected_idx = st.selectbox(
                            "Select a record to review",
                            range(len(reviewable)),
                            format_func=lambda i: reviewable[i][0],
                            index=min(st.session_state.review_selector_idx, len(indices) - 1),
                            key="review_selector",
                        )
                    else:
                        selected_idx = 0
                        st.session_state.review_selector_idx = 0
                except (ValueError, IndexError):
                    selected_idx = 0

                selected_key, selected_status = reviewable[selected_idx]
                st.session_state.review_selector_idx = selected_idx

                st.markdown(f"**Selected:** GSTIN {selected_key.split('|')[0]} | "
                            f"Status: {selected_status}")

                # Get the match result details
                # Find the matching MatchResult
                selected_match = None
                for m in result.matches:
                    book = m.purchase_record
                    gstr2b = m.gstr2b_record
                    check_gstin = book.gstin if book else (gstr2b.gstin if gstr2b else "")
                    check_inv = book.invoice_number if book else (gstr2b.invoice_number if gstr2b else "")
                    if f"{check_gstin}|{check_inv}" == selected_key:
                        selected_match = m
                        break

                if selected_match is not None:
                    with st.form(key="review_decision_form"):
                        review_decision = st.radio(
                            "Your decision:",
                            options=["approve", "reject", "pending"],
                            format_func=lambda x: {
                                "approve": "✅ Approve",
                                "reject": "❌ Reject",
                                "pending": "⏳ Pending",
                            }[x],
                            key="decision_radio",
                        )
                        reviewer_reason = st.text_area(
                            "Reviewer reason (optional)",
                            help="Describe why you made this decision. This is recorded in the audit trail.",
                        )
                        reviewer_name = st.text_input(
                            "Your name / identifier (optional)",
                            help="For audit traceability. No secrets or real taxpayer data.",
                        )

                        submit_review = st.form_submit_button("💾 Record Decision")

                        if submit_review:
                            invoice_key_val = _invoice_key(
                                selected_match.purchase_record.gstin if selected_match.purchase_record else None,
                                selected_match.purchase_record.invoice_number if selected_match.purchase_record else (
                                    selected_match.gstr2b_record.invoice_number if selected_match.gstr2b_record else None)
                            )

                            # Hmm, this is getting complicated. Let me simplify.
                            # Actually, let me just use the gstin and invoice from the selected record.

                            new_review = ReviewRecord(
                                review_id=str(uuid.uuid4()),
                                run_id=st.session_state.run_id,
                                invoice_key=_invoice_key(
                                    selected_match.purchase_record.gstin
                                    if selected_match.purchase_record
                                    else (
                                        selected_match.gstr2b_record.gstin
                                        if selected_match.gstr2b_record
                                        else None
                                    ),
                                    selected_match.purchase_record.invoice_number
                                    if selected_match.purchase_record
                                    else (
                                        selected_match.gstr2b_record.invoice_number
                                        if selected_match.gstr2b_record
                                        else None)
                                ),
                                match_status=selected_match.match_status.value,
                                suggested_action=selected_match.match_status.value,
                                decision=review_decision,
                                reviewer_reason=reviewer_reason,
                                reviewer_name=reviewer_name or "",
                                timestamp=_utc_now_iso(),
                                decision_metadata={},
                            )

                            # Append to audit log
                            st.session_state.audit_log.append(
                                AuditEvent(
                                    event_id=str(uuid.uuid4()),
                                    timestamp=_utc_now_iso(),
                                    event_type=AuditEventType.REVIEW_ACTION,
                                    run_id=st.session_state.run_id,
                                    invoice_key=invoice_key_val,
                                    summary=f"Review decision: {review_decision} for {selected_match.match_status.value}",
                                    metadata={
                                        "review_id": new_review.review_id,
                                        "decision": review_decision,
                                        "match_status": selected_match.match_status.value,
                                    },
                                )
                            )

                            # Store review record
                            st.session_state.review_records.append(new_review)

                            st.success(f"✅ Review decision recorded: {review_decision}")
                            st.rerun()

                else:
                    st.info("Record selected but match details not found.")

            # Display existing review records
            if st.session_state.review_records:
                st.markdown("#### Recorded Review Decisions")
                review_rows = []
                for rec in st.session_state.review_records:
                    review_rows.append({
                        "Review ID": rec.review_id[:8] + "...",
                        "Run ID": rec.run_id[:8] + "...",
                        "Invoice Key": rec.invoice_key or "-",
                        "Match Status": rec.match_status,
                        "Decision": rec.decision,
                        "Reviewer Reason": (
                            rec.reviewer_reason[:60] + "..." if len(rec.reviewer_reason) > 60
                            else rec.reviewer_reason
                        ),
                        "Reviewer": rec.reviewer_name or "—",
                        "Timestamp": rec.timestamp,
                    })

                rdf = pd.DataFrame(review_rows)
                st.dataframe(rdf, use_container_width=True, height=300)

                st.caption(
                    "Review decisions are preserved across reruns for this session. "
                    "Each run has its own run_id and audit log file in "
                    "data/runs/<run_id>/. Closing the browser resets the session state."
                )
            else:
                st.info("No review decisions recorded yet.")
        else:
            st.info("Run reconciliation first to enable review recording.")


# ---------------------------------------------------------------------------
# Footer / sidebar note
# ---------------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.caption(
    f"Iteration: {__version__} | "
    "Phase 5: Streamlit MVP | "
    "No Phase 6 work started"
)
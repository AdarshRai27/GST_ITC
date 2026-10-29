"""Streamlit workflow tests for the ITC Sentinel MVP.

These tests exercise the real Streamlit script with ``AppTest``: sample-data
selection, uploads, reconciliation, exception inspection, review actions,
export, and audit events.

All data is synthetic; no real taxpayer data is used.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from itc_sentinel.audit import AuditEventType, AuditLog

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "itc_sentinel" / "app.py"
SAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"


def _purchase_bytes() -> bytes:
    return (SAMPLE_DIR / "purchase_register_synthetic.csv").read_bytes()


def _gstr2b_bytes() -> bytes:
    return (SAMPLE_DIR / "gstr2b_synthetic.json").read_bytes()


def _new_app(monkeypatch, tmp_path) -> AppTest:
    monkeypatch.setenv("ITC_SENTINEL_DATA_DIR", str(tmp_path / "data"))
    app = AppTest.from_file(str(APP_PATH), default_timeout=60)
    app.run()
    return app


def _run_sample(app: AppTest) -> AppTest:
    app.get_by_key("run_reconciliation").click().run()
    assert not app.exception
    assert app.session_state["_pipeline_done"] is True
    return app


def _select_uploads(app: AppTest, purchase: bytes, gstr2b: bytes) -> AppTest:
    app.checkbox(key="use_sample_data").uncheck().run()
    assert not app.exception
    app.get_by_key("purchase_uploader").upload(
        "purchase.csv", purchase, "text/csv"
    )
    app.get_by_key("gstr2b_uploader").upload(
        "gstr2b.json", gstr2b, "application/json"
    )
    app.run()
    assert not app.exception
    return app


def _audit_events(app: AppTest):
    path = Path(app.session_state["audit_log_path"])
    return AuditLog(path).read_events()


# ---------------------------------------------------------------------------
# Load and sample workflow
# ---------------------------------------------------------------------------


def test_app_loads_without_exceptions(monkeypatch, tmp_path):
    app = _new_app(monkeypatch, tmp_path)

    assert not app.exception
    assert app.checkbox(key="use_sample_data").value is True
    assert app.button(key="run_reconciliation").label.endswith(
        "Run Reconciliation"
    )


def test_sample_run_builds_expected_dashboard(monkeypatch, tmp_path):
    app = _run_sample(_new_app(monkeypatch, tmp_path))

    assert len(app.session_state["_decisions"]) == 10
    metrics = app.session_state["_metrics"]
    assert metrics.total_reconciliation_rows == 10
    assert metrics.confirmed_matches == 2
    assert metrics.amount_mismatches == 1
    assert metrics.tax_head_mismatches == 1
    assert metrics.fuzzy_candidates == 1
    assert metrics.probable_candidates == 1
    assert metrics.review_required == 9

    labels = [metric.label for metric in app.metric]
    values = [metric.value for metric in app.metric]
    assert "Confirmed matches (exact)" in labels
    assert values[labels.index("Confirmed matches (exact)")] == "2"
    assert "Mismatches (amount + tax head)" in labels
    assert values[labels.index("Mismatches (amount + tax head)")] == "2"

    assert [tab.label for tab in app.tabs] == [
        "📊 Summary",
        "⚠️ Exceptions",
        "📨 Vendor Messages",
        "📄 Export & Audit",
    ]

    event_types = [event.event_type for event in _audit_events(app)]
    assert AuditEventType.RUN_STARTED.value in event_types
    assert AuditEventType.RUN_COMPLETED.value in event_types


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def test_uploaded_csv_and_json_run_pipeline_and_temp_files_are_removed(
    monkeypatch, tmp_path
):
    app = _new_app(monkeypatch, tmp_path)
    _select_uploads(app, _purchase_bytes(), _gstr2b_bytes())
    _run_sample(app)

    assert len(app.session_state["_decisions"]) == 10
    upload_dir = (
        Path(app.session_state["audit_log_path"]).parent / "uploads"
    )
    assert upload_dir.exists()
    assert list(upload_dir.glob("*")) == []


def test_invalid_csv_shows_actionable_error(monkeypatch, tmp_path):
    app = _new_app(monkeypatch, tmp_path)
    _select_uploads(
        app,
        b"gstin,invoice_number\n29ABCDE1234F1Z5,INV-1\n",
        _gstr2b_bytes(),
    )
    app.get_by_key("run_reconciliation").click().run()

    assert not app.exception
    assert app.session_state["_pipeline_done"] is False
    messages = " | ".join(error.value for error in app.error)
    assert "column validation" in messages
    assert "invoice_date" in messages
    assert len(app.tabs) == 0


def test_invalid_json_shows_actionable_error(monkeypatch, tmp_path):
    app = _new_app(monkeypatch, tmp_path)
    _select_uploads(app, _purchase_bytes(), b"{not valid json")
    app.get_by_key("run_reconciliation").click().run()

    assert not app.exception
    assert app.session_state["_pipeline_done"] is False
    messages = " | ".join(error.value for error in app.error)
    assert "Malformed JSON" in messages


def test_failed_upload_can_be_followed_by_a_successful_run(monkeypatch, tmp_path):
    app = _new_app(monkeypatch, tmp_path)
    _select_uploads(app, b"gstin,invoice_number\nX,Y\n", _gstr2b_bytes())
    app.get_by_key("run_reconciliation").click().run()
    assert app.session_state["_pipeline_done"] is False

    app.get_by_key("purchase_uploader").clear()
    app.get_by_key("gstr2b_uploader").clear()
    app.get_by_key("purchase_uploader").upload(
        "purchase.csv", _purchase_bytes(), "text/csv"
    )
    app.get_by_key("gstr2b_uploader").upload(
        "gstr2b.json", _gstr2b_bytes(), "application/json"
    )
    app.run()
    _run_sample(app)

    assert len(app.session_state["_decisions"]) == 10


def test_empty_dataset_is_handled(monkeypatch, tmp_path):
    app = _new_app(monkeypatch, tmp_path)
    empty_csv = (
        b"gstin,invoice_number,invoice_date,taxable_value,cgst,sgst,igst,cess\n"
    )
    empty_json = (
        b'{"gstin":"29ABCDE1234F1Z5","period":"042024","invoices":[]}'
    )
    _select_uploads(app, empty_csv, empty_json)
    app.get_by_key("run_reconciliation").click().run()

    assert not app.exception
    assert app.session_state["_pipeline_done"] is True
    metrics = app.session_state["_metrics"]
    assert metrics.total_reconciliation_rows == 0
    assert metrics.confirmed_matches == 0
    assert metrics.review_required == 0
    assert [tab.label for tab in app.tabs][0] == "📊 Summary"


# ---------------------------------------------------------------------------
# Review workflow
# ---------------------------------------------------------------------------


def test_review_exact_match_updates_correct_record_and_audit(monkeypatch, tmp_path):
    app = _run_sample(_new_app(monkeypatch, tmp_path))

    app.selectbox(key="review_record_selector").set_value("books:0").run()
    assert not app.exception

    radio = app.radio(key="decision_radio_books:0")
    assert radio.options == ["✅ Approve", "❌ Reject", "⏳ Pending"]

    app.radio(key="decision_radio_books:0").set_value("approve")
    app.text_area(key="reason_books:0").set_value("Synthetic review")
    app.text_input(key="reviewer_books:0").set_value("tester")
    app.button(key="submit_review_books:0").click().run()
    assert not app.exception

    reviews = app.session_state["review_records"]
    assert len(reviews) == 1
    assert reviews[0].record_id == "books:0"
    assert reviews[0].decision == "approve"
    assert reviews[0].previous_state == "none"
    assert reviews[0].new_state == "approve"
    assert reviews[0].reviewer_name == "tester"

    metrics = app.session_state["_metrics"]
    assert metrics.reviewed_records == 1
    assert metrics.accepted == 1
    assert metrics.awaiting_review == 8

    review_events = [
        event
        for event in _audit_events(app)
        if event.event_type == AuditEventType.REVIEW_ACTION.value
    ]
    assert len(review_events) == 1
    assert review_events[0].metadata["record_id"] == "books:0"
    assert review_events[0].metadata["new_state"] == "approve"


def test_duplicate_invoice_rows_keep_distinct_review_identities(
    monkeypatch, tmp_path
):
    app = _run_sample(_new_app(monkeypatch, tmp_path))

    # Books row 5 is a duplicate of row 0: both share GSTIN + INV-1001.
    app.selectbox(key="review_record_selector").set_value("books:5").run()
    app.radio(key="decision_radio_books:5").set_value("pending")
    app.button(key="submit_review_books:5").click().run()
    assert not app.exception

    app.selectbox(key="review_record_selector").set_value("books:0").run()
    app.radio(key="decision_radio_books:0").set_value("approve")
    app.button(key="submit_review_books:0").click().run()
    assert not app.exception

    reviews = app.session_state["review_records"]
    assert [review.record_id for review in reviews] == ["books:5", "books:0"]
    assert [review.decision for review in reviews] == ["pending", "approve"]

    metrics = app.session_state["_metrics"]
    assert metrics.reviewed_records == 2
    assert metrics.accepted == 1
    assert metrics.pending == 1


def test_invalid_record_offers_no_approve_action(monkeypatch, tmp_path):
    app = _run_sample(_new_app(monkeypatch, tmp_path))

    app.selectbox(key="review_record_selector").set_value("books:6").run()
    assert not app.exception

    radio = app.radio(key="decision_radio_books:6")
    assert radio.options == ["❌ Reject", "⏳ Pending"]
    assert "Approve" not in " ".join(radio.options)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_generates_workbook_and_audit_event(monkeypatch, tmp_path):
    app = _run_sample(_new_app(monkeypatch, tmp_path))

    app.button(key="generate_export").click().run()
    assert not app.exception

    export_bytes = app.session_state["_export_bytes"]
    assert export_bytes
    assert export_bytes[:2] == b"PK"  # XLSX is a zip archive

    assert app.download_button(key="download_export").label.endswith(
        "Download Excel workbook"
    )

    event_types = [event.event_type for event in _audit_events(app)]
    assert AuditEventType.EXPORT_CREATED.value in event_types


# ---------------------------------------------------------------------------
# Run isolation
# ---------------------------------------------------------------------------


def test_rerun_rotates_run_and_clears_reviews(monkeypatch, tmp_path):
    app = _run_sample(_new_app(monkeypatch, tmp_path))
    first_run_id = app.session_state["run_id"]

    app.selectbox(key="review_record_selector").set_value("books:0").run()
    app.radio(key="decision_radio_books:0").set_value("approve")
    app.button(key="submit_review_books:0").click().run()
    assert len(app.session_state["review_records"]) == 1

    app.get_by_key("run_reconciliation").click().run()
    assert not app.exception

    assert app.session_state["run_id"] != first_run_id
    assert app.session_state["review_records"] == []
    assert app.session_state["_metrics"].reviewed_records == 0
    assert app.session_state["_metrics"].confirmed_matches == 2


@pytest.mark.parametrize(
    "record_id",
    [
        "books:0",
        "books:1",
        "books:2",
        "books:3",
        "books:4",
        "books:5",
        "books:6",
        "books:7",
        "books:8",
    ],
)
def test_every_review_required_row_is_selectable(
    monkeypatch, tmp_path, record_id
):
    app = _run_sample(_new_app(monkeypatch, tmp_path))
    options = app.selectbox(key="review_record_selector").options

    assert record_id in [option.split("row ")[-1] for option in options]

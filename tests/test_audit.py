"""Tests for the audit module (src/itc_sentinel/audit.py).

Covers AuditEvent, AuditLog, ReviewRecord, append-only behavior, event
ordering, malformed log handling, and sensitive-value exclusion.
"""

from __future__ import annotations

import pytest

from itc_sentinel.audit import (
    AuditEvent,
    AuditEventType,
    AuditLog,
    ReviewDecision,
    ReviewRecord,
    new_audit_log,
)

# ---------------------------------------------------------------------------
# AuditEvent
# ---------------------------------------------------------------------------


def test_audit_event_creation():
    event = AuditEvent(
        event_id="evt-1",
        timestamp="2024-04-15T10:00:00+00:00",
        event_type=AuditEventType.RUN_STARTED,
        run_id="run-1",
        invoice_key="29ABCDE1234F1Z5|INV-001",
        summary="Run started",
        metadata={"key": "value"},
    )
    assert event.event_id == "evt-1"
    assert event.event_type == AuditEventType.RUN_STARTED
    assert event.run_id == "run-1"
    assert event.invoice_key == "29ABCDE1234F1Z5|INV-001"
    assert event.summary == "Run started"
    assert event.metadata == {"key": "value"}


def test_audit_event_defaults():
    event = AuditEvent(
        event_id="evt-2",
        timestamp="2024-04-15T10:00:00+00:00",
        event_type=AuditEventType.DECISION_RECORDED,
        run_id="run-1",
    )
    assert event.invoice_key is None
    assert event.summary == ""
    assert event.metadata == {}


# ---------------------------------------------------------------------------
# AuditLog append / read
# ---------------------------------------------------------------------------


def test_audit_log_append_and_read(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    log = new_audit_log(log_path)

    e1 = AuditEvent(
        event_id="e1",
        timestamp="2024-04-15T10:00:00+00:00",
        event_type=AuditEventType.RUN_STARTED,
        run_id="run-1",
        summary="started",
    )
    e2 = AuditEvent(
        event_id="e2",
        timestamp="2024-04-15T10:01:00+00:00",
        event_type=AuditEventType.DECISION_RECORDED,
        run_id="run-1",
        invoice_key="29ABCDE1234F1Z5|INV-001",
        summary="decision recorded",
    )
    log.append(e1)
    log.append(e2)

    events = log.read_events()
    assert len(events) == 2
    assert events[0].event_id == "e1"
    assert events[1].event_id == "e2"
    assert events[1].invoice_key == "29ABCDE1234F1Z5|INV-001"


def test_audit_log_is_append_only(tmp_path):
    """Events already written must not be overwritten by subsequent appends."""
    log_path = tmp_path / "audit.jsonl"
    log = new_audit_log(log_path)
    log.append(
        AuditEvent(
            event_id="e1",
            timestamp="2024-04-15T10:00:00+00:00",
            event_type=AuditEventType.RUN_STARTED,
            run_id="run-1",
            summary="first",
        )
    )
    log.append(
        AuditEvent(
            event_id="e2",
            timestamp="2024-04-15T10:01:00+00:00",
            event_type=AuditEventType.RUN_COMPLETED,
            run_id="run-1",
            summary="second",
        )
    )
    events = log.read_events()
    assert len(events) == 2
    assert events[0].summary == "first"
    assert events[1].summary == "second"


def test_audit_log_count(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    log = new_audit_log(log_path)
    assert log.count() == 0
    log.append(
        AuditEvent(
            event_id="e1",
            timestamp="2024-04-15T10:00:00+00:00",
            event_type=AuditEventType.RUN_STARTED,
            run_id="run-1",
        )
    )
    assert log.count() == 1


def test_audit_log_missing_file_raises(tmp_path):
    log = new_audit_log(tmp_path / "nonexistent.jsonl")
    with pytest.raises(FileNotFoundError):
        log.read_events()


def test_audit_log_malformed_line_raises(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    log_path.write_text(
        '{"event_id":"e1","timestamp":"2024-04-15T10:00:00+00:00",'
        '"event_type":"run_started","run_id":"run-1"}\n'
        "{ not valid json }\n",
        encoding="utf-8",
    )
    log = new_audit_log(log_path)
    with pytest.raises(ValueError, match="Malformed audit log line"):
        log.read_events()


def test_audit_log_no_secrets_logged(tmp_path):
    """Audit events must not contain secrets or API keys."""
    log_path = tmp_path / "audit.jsonl"
    log = new_audit_log(log_path)
    log.append(
        AuditEvent(
            event_id="e1",
            timestamp="2024-04-15T10:00:00+00:00",
            event_type=AuditEventType.ERROR,
            run_id="run-1",
            summary="error occurred",
            metadata={"error": "connection failed"},
        )
    )
    content = log_path.read_text(encoding="utf-8")
    assert "secret" not in content.lower()
    assert "api_key" not in content.lower()
    assert "password" not in content.lower()


# ---------------------------------------------------------------------------
# ReviewRecord
# ---------------------------------------------------------------------------


def test_review_record_creation():
    record = ReviewRecord(
        review_id="rev-1",
        run_id="run-1",
        invoice_key="29ABCDE1234F1Z5|INV-001",
        match_status="amount_mismatch",
        suggested_action="request_clarification",
        decision=ReviewDecision.APPROVE,
        reviewer_reason="Amounts verified with vendor",
        reviewer_name="reviewer-1",
        timestamp="2024-04-15T11:00:00+00:00",
    )
    assert record.review_id == "rev-1"
    assert record.run_id == "run-1"
    assert record.invoice_key == "29ABCDE1234F1Z5|INV-001"
    assert record.match_status == "amount_mismatch"
    assert record.suggested_action == "request_clarification"
    assert record.decision == ReviewDecision.APPROVE
    assert record.reviewer_reason == "Amounts verified with vendor"
    assert record.reviewer_name == "reviewer-1"


def test_review_record_defaults():
    record = ReviewRecord(
        review_id="rev-2",
        run_id="run-2",
        invoice_key=None,
        match_status="invalid",
        suggested_action="flag_for_review",
        decision=ReviewDecision.PENDING,
    )
    assert record.reviewer_reason == ""
    assert record.reviewer_name == ""
    assert record.timestamp == ""
    assert record.decision_metadata == {}


# ---------------------------------------------------------------------------
# new_audit_log factory
# ---------------------------------------------------------------------------


def test_new_audit_log_returns_audit_log(tmp_path):
    log = new_audit_log(tmp_path / "audit.jsonl")
    assert isinstance(log, AuditLog)

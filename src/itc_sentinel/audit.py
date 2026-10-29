"""Append-only file-based audit logging and review records for Phase 4.

This module implements the audit trail required by `phases.md` Phase 4:
- Human approve/reject decisions with optional reason, recorded with run and
  invoice identifiers.
- Append-only local audit events (JSONL) with per-run metadata.
- Honest about limitations: this is a demo audit trail, not tamper-proof
  or legally compliant storage.

Design principles (per `rules.md` and `architecture.md`):
- Append-only: events are never overwritten or erased.
- Stable identifiers and timestamps in ISO 8601 format.
- No secrets, API keys, or unnecessary sensitive taxpayer data in audit logs.
- Actionable errors for missing, malformed, or inaccessible audit files.
- File-based persistence only; no database introduced.

Public classes:
    AuditEvent
    AuditLog
    ReviewRecord

Public functions:
    new_audit_log(path) -> AuditLog
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "AuditEvent",
    "AuditEventType",
    "AuditLog",
    "ReviewDecision",
    "ReviewRecord",
    "new_audit_log",
]


class AuditEventType(str, Enum):
    """Stable audit event types."""

    RUN_STARTED = "run_started"
    RUN_COMPLETED = "run_completed"
    DECISION_RECORDED = "decision_recorded"
    REVIEW_ACTION = "review_action"
    EXPORT_CREATED = "export_created"
    ERROR = "error"


class ReviewDecision(str, Enum):
    """Human review actions. Advisory only; nothing is executed externally."""

    APPROVE = "approve"
    REJECT = "reject"
    PENDING = "pending"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditEvent:
    """A single append-only audit event.

    Attributes:
        event_id: Stable UUID v4 identifier.
        timestamp: ISO 8601 UTC timestamp.
        event_type: Stable event type.
        run_id: Run identifier this event belongs to.
        invoice_key: Optional (gstin, invoice_number) tuple for traceability.
        summary: Human-readable summary of the event.
        metadata: Additional structured data (no secrets).
    """

    event_id: str
    timestamp: str
    event_type: str
    run_id: str
    invoice_key: str | None = None
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewRecord:
    """A human review decision on a reconciliation result.

    Attributes:
        review_id: Stable UUID v4 identifier.
        run_id: Run identifier.
        invoice_key: (gstin, invoice_number) for traceability.
        match_status: The reconciliation match status being reviewed.
        suggested_action: The machine-suggested action (not overwritten).
        decision: Human decision (approve/reject/pending).
        reviewer_reason: Optional reason recorded by the reviewer.
        reviewer_name: Optional reviewer identifier (no secrets).
        timestamp: ISO 8601 UTC timestamp when the decision was recorded.
        decision_metadata: Additional structured data.
        record_id: Stable internal record identifier (preferred over
            ``invoice_key`` for associating a review with a reconciliation
            result, because duplicate invoice identifiers can repeat).
        previous_state: Review state before this action (``"none"`` for a
            first review).
        new_state: Review state recorded by this action.
    """

    review_id: str
    run_id: str
    invoice_key: str | None
    match_status: str
    suggested_action: str
    decision: str
    reviewer_reason: str = ""
    reviewer_name: str = ""
    timestamp: str = ""
    decision_metadata: dict[str, Any] = field(default_factory=dict)
    record_id: str = ""
    previous_state: str = ""
    new_state: str = ""


# ---------------------------------------------------------------------------
# Audit log (append-only JSONL)
# ---------------------------------------------------------------------------


class AuditLog:
    """Append-only audit log backed by a JSONL file.

    Each event is appended as one JSON line. Events are never overwritten or
    erased. The file is created on first write if it does not exist.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._ensure_parent()

    def _ensure_parent(self) -> None:
        """Ensure the parent directory exists."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _serialize(self, event: AuditEvent) -> str:
        """Serialize an event to a single JSON line."""
        return json.dumps(asdict(event), sort_keys=True, separators=(",", ":"))

    def append(self, event: AuditEvent) -> None:
        """Append an event to the log.

        Args:
            event: The audit event to append.

        Raises:
            OSError: If the file cannot be written.
            ValueError: If the event is invalid.
        """
        if not isinstance(event, AuditEvent):
            raise ValueError("event must be an AuditEvent instance")
        line = self._serialize(event)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def read_events(self) -> list[AuditEvent]:
        """Read all events from the log in append order.

        Returns:
            List of AuditEvent objects. Malformed lines raise ValueError.

        Raises:
            FileNotFoundError: If the log file does not exist.
            ValueError: If any line is malformed JSON or missing fields.
        """
        if not self.path.exists():
            raise FileNotFoundError(f"Audit log not found: {self.path}")
        events: list[AuditEvent] = []
        with open(self.path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Malformed audit log line {line_number} in "
                        f"{self.path}: {exc}"
                    ) from exc
                try:
                    events.append(AuditEvent(**obj))
                except TypeError as exc:
                    raise ValueError(
                        f"Invalid audit event on line {line_number} in "
                        f"{self.path}: {exc}"
                    ) from exc
        return events

    def count(self) -> int:
        """Return the number of events in the log."""
        if not self.path.exists():
            return 0
        return len(self.read_events())


def new_audit_log(path: str | Path) -> AuditLog:
    """Create an :class:`AuditLog` for the given path.

    Args:
        path: Filesystem path for the JSONL audit log.

    Returns:
        A new :class:`AuditLog` instance.
    """
    return AuditLog(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _invoice_key(gstin: str | None, invoice_number: str | None) -> str | None:
    """Return a stable invoice key string for audit traceability."""
    if gstin is None and invoice_number is None:
        return None
    return f"{gstin or ''}|{invoice_number or ''}"

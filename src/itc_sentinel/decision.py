"""Deterministic decision support for the ITC Sentinel pipeline.

Produces, for every reconciliation result, a suggested operational action,
ITC exposure estimate, priority, flags, reason code, and human-review
requirement.

Design principles (per `rules.md:§4` and `requirements.md:§5`):
- Matching status, eligibility status, and suggested operational action are
  distinct and NOT interchangeable.
- A matched invoice is NOT automatically eligible for ITC. All match
  statuses map to ``eligibility_status UNCERTAIN`` unless a CA-validated
  rule states otherwise.
- An unmatched invoice is NOT automatically proof of ITC ineligibility.
- Exposure figures are provisional estimates, not confirmed tax liabilities.
- Decisions are deterministic: identical inputs and settings produce
  identical outputs.
- No external action is executed (no filing, payment holds, vendor messages).

Public functions:
    decide(match_result, rule_settings, decision_settings) -> DecisionResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any

from .matcher import MatchResult, MatchStatus
from .rules import DEFAULT_RULE_SETTINGS, RuleSettings
from .schemas import MONEY_PLACES

__all__ = [
    "Action",
    "DecisionResult",
    "DecisionSettings",
    "EligibilityStatus",
    "Flag",
    "Priority",
    "ReasonCode",
    "REVIEW_DECISIONS",
    "allowed_review_decisions",
    "decide",
    "validate_review_decision",
]


class Action(str, Enum):
    """Suggested operational action (advisory only; nothing is executed).

    ``PROPOSE_ITC_CLAIM`` deliberately avoids implying that a claim has been
    approved. A matching invoice is only a *candidate* for an ITC claim until
    eligibility is established and a human has reviewed it.
    """

    PROPOSE_ITC_CLAIM = "propose_itc_claim"
    REQUEST_CLARIFICATION = "request_clarification"
    FLAG_FOR_REVIEW = "flag_for_review"
    EXCLUDE_FROM_ITC = "exclude_from_itc"
    NO_ACTION = "no_action"


class Priority(str, Enum):
    """Review priority."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EligibilityStatus(str, Enum):
    """ITC eligibility status.

    Distinct from match status. All values are provisional pending CA
    verification of tax rules.
    """

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    UNCERTAIN = "uncertain"
    NOT_ASSESSED = "not_assessed"


class Flag(str, Enum):
    """Stable flags attached to a decision."""

    AMOUNT_MISMATCH = "amount_mismatch"
    TAX_HEAD_MISMATCH = "tax_head_mismatch"
    FUZZY_MATCH = "fuzzy_match"
    PROBABLE_MATCH = "probable_match"
    LOW_CONFIDENCE_MATCH = "low_confidence_match"
    MISSING_IN_2B = "missing_in_2b"
    DUPLICATE = "duplicate"
    INVALID_DATA = "invalid_data"


class ReasonCode(str, Enum):
    """Stable reason codes for each decision."""

    EXACT_MATCH = "ITC-EXACT-MATCH"
    AMOUNT_MISMATCH = "ITC-AMOUNT-MISMATCH"
    TAX_HEAD_MISMATCH = "ITC-TAX-HEAD-MISMATCH"
    FUZZY_MATCH = "ITC-FUZZY-MATCH"
    PROBABLE_MATCH = "ITC-PROBABLE-MATCH"
    LOW_CONFIDENCE_MATCH = "ITC-LOW-CONFIDENCE"
    UNMATCHED_BOOKS = "ITC-UNMATCHED-BOOKS"
    UNMATCHED_GSTR2B = "ITC-UNMATCHED-GSTR2B"
    DUPLICATE = "ITC-DUPLICATE"
    INVALID_DATA = "ITC-INVALID-DATA"


@dataclass(frozen=True)
class DecisionSettings:
    """Configuration for decision support.

    Thresholds are configurable business assumptions pending CA validation;
    they are not statutory values.
    """

    # Exposure amount above which a record is treated as high priority.
    high_exposure_threshold: Decimal = Decimal("50000.00")
    # Exposure amount above which a record is treated as medium priority.
    medium_exposure_threshold: Decimal = Decimal("10000.00")


DEFAULT_DECISION_SETTINGS = DecisionSettings()


@dataclass
class DecisionResult:
    """Outcome of applying decision rules to one match result.

    Attributes:
        match_result: The reconciliation result this decision is based on.
        action: Suggested operational action (advisory only).
        priority: Review priority.
        flags: Stable flags attached to the decision.
        reason: Human-readable explanation.
        reason_code: Stable reason code.
        exposure_amount: Provisional ITC exposure estimate (Decimal), or 0
            when no exposure can be attributed.
        review_required: True when a human must review this record.
        eligibility_status: Provisional ITC eligibility status (UNCERTAIN by
            design; matching is not proof of eligibility).
        rule_sources_applied: Rule sources referenced by this decision.
    """

    match_result: MatchResult
    action: Action
    priority: Priority
    flags: list[Flag] = field(default_factory=list)
    reason: str = ""
    reason_code: ReasonCode = ReasonCode.EXACT_MATCH
    exposure_amount: Decimal = Decimal("0")
    review_required: bool = False
    eligibility_status: EligibilityStatus = EligibilityStatus.UNCERTAIN
    rule_sources_applied: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-status decision mapping
# ---------------------------------------------------------------------------


def _decide_exact(match: MatchResult, settings: DecisionSettings) -> DecisionResult:
    return DecisionResult(
        match_result=match,
        action=Action.PROPOSE_ITC_CLAIM,
        priority=Priority.LOW,
        flags=[],
        reason=(
            "Exact match on GSTIN, invoice number, date, and amounts. This is "
            "a candidate for an ITC claim only. Matching is not proof of "
            "eligibility, so human review is still required before any claim "
            "(rule R-ITC-ELIGIBILITY)."
        ),
        reason_code=ReasonCode.EXACT_MATCH,
        exposure_amount=Decimal("0"),
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=["R-MATCH-EXACT", "R-ITC-ELIGIBILITY"],
    )


def _decide_amount_mismatch(
    match: MatchResult, settings: DecisionSettings
) -> DecisionResult:
    diff = match.amount_difference
    exposure = abs(diff) if diff is not None else Decimal("0")
    flags = [Flag.AMOUNT_MISMATCH]
    return DecisionResult(
        match_result=match,
        action=Action.REQUEST_CLARIFICATION,
        priority=_priority_for_exposure(exposure, settings),
        flags=flags,
        reason=(
            f"Amount mismatch between books and GSTR-2B "
            f"(difference {diff}). Request vendor clarification before "
            "claiming ITC. Exposure estimate = |difference|."
        ),
        reason_code=ReasonCode.AMOUNT_MISMATCH,
        exposure_amount=exposure,
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=[
            "R-MATCH-AMOUNT-MISMATCH",
            "R-CALC-AMOUNT-DIFF",
            "R-ITC-ELIGIBILITY",
        ],
    )


def _decide_tax_head_mismatch(
    match: MatchResult, settings: DecisionSettings
) -> DecisionResult:
    book = match.purchase_record
    exposure = Decimal("0")
    if book is not None and book.total_tax is not None:
        exposure = book.total_tax
    return DecisionResult(
        match_result=match,
        action=Action.FLAG_FOR_REVIEW,
        priority=Priority.HIGH,
        flags=[Flag.TAX_HEAD_MISMATCH],
        reason=(
            "Same GSTIN and invoice number, but tax is under a different "
            "head (domestic CGST/SGST vs IGST). Flag for review before "
            "claiming ITC."
        ),
        reason_code=ReasonCode.TAX_HEAD_MISMATCH,
        exposure_amount=exposure,
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=[
            "R-MATCH-TAX-HEAD",
            "R-CALC-TAX-EXPOSURE",
            "R-ITC-ELIGIBILITY",
        ],
    )


def _decide_fuzzy(match: MatchResult, settings: DecisionSettings) -> DecisionResult:
    return DecisionResult(
        match_result=match,
        action=Action.REQUEST_CLARIFICATION,
        priority=Priority.MEDIUM,
        flags=[Flag.FUZZY_MATCH],
        reason=(
            "Fuzzy invoice-number match. Verify invoice identity before "
            "claiming ITC; fuzzy similarity alone does not confirm a match."
        ),
        reason_code=ReasonCode.FUZZY_MATCH,
        exposure_amount=Decimal("0"),
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=["R-MATCH-FUZZY", "R-ITC-ELIGIBILITY"],
    )


def _decide_probable(match: MatchResult, settings: DecisionSettings) -> DecisionResult:
    return DecisionResult(
        match_result=match,
        action=Action.FLAG_FOR_REVIEW,
        priority=Priority.MEDIUM,
        flags=[Flag.PROBABLE_MATCH],
        reason=(
            "Probable invoice-number match. Low confidence; requires human "
            "review before claiming ITC."
        ),
        reason_code=ReasonCode.PROBABLE_MATCH,
        exposure_amount=Decimal("0"),
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=["R-MATCH-PROBABLE", "R-ITC-ELIGIBILITY"],
    )


def _decide_low_confidence(
    match: MatchResult, settings: DecisionSettings
) -> DecisionResult:
    return DecisionResult(
        match_result=match,
        action=Action.FLAG_FOR_REVIEW,
        priority=Priority.MEDIUM,
        flags=[Flag.LOW_CONFIDENCE_MATCH],
        reason=(
            "Low-confidence match. Requires human review before claiming ITC."
        ),
        reason_code=ReasonCode.LOW_CONFIDENCE_MATCH,
        exposure_amount=Decimal("0"),
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=["R-ITC-ELIGIBILITY"],
    )


def _decide_unmatched_books(
    match: MatchResult, settings: DecisionSettings
) -> DecisionResult:
    book = match.purchase_record
    exposure = Decimal("0")
    if book is not None and book.total_amount is not None:
        exposure = book.total_amount
    elif book is not None and book.taxable_value is not None:
        exposure = book.taxable_value
    return DecisionResult(
        match_result=match,
        action=Action.FLAG_FOR_REVIEW,
        priority=_priority_for_exposure(exposure, settings),
        flags=[Flag.MISSING_IN_2B],
        reason=(
            "No matching GSTR-2B invoice found (missing in 2B). May affect "
            "ITC claim; requires human review."
        ),
        reason_code=ReasonCode.UNMATCHED_BOOKS,
        exposure_amount=exposure,
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=["R-ITC-ELIGIBILITY", "R-CALC-TAXABLE-EXPOSURE"],
    )


def _decide_unmatched_gstr2b(
    match: MatchResult, settings: DecisionSettings
) -> DecisionResult:
    return DecisionResult(
        match_result=match,
        action=Action.NO_ACTION,
        priority=Priority.LOW,
        flags=[],
        reason=(
            "No matching purchase-register invoice (GSTR-2B only). "
            "No books-side action required."
        ),
        reason_code=ReasonCode.UNMATCHED_GSTR2B,
        exposure_amount=Decimal("0"),
        review_required=False,
        eligibility_status=EligibilityStatus.NOT_ASSESSED,
        rule_sources_applied=["R-ITC-ELIGIBILITY"],
    )


def _decide_duplicate(match: MatchResult, settings: DecisionSettings) -> DecisionResult:
    book = match.purchase_record
    exposure = Decimal("0")
    if book is not None and book.total_amount is not None:
        exposure = book.total_amount
    elif book is not None and book.taxable_value is not None:
        exposure = book.taxable_value
    return DecisionResult(
        match_result=match,
        action=Action.FLAG_FOR_REVIEW,
        priority=Priority.HIGH,
        flags=[Flag.DUPLICATE],
        reason=(
            "Duplicate purchase-register row (same GSTIN and invoice number "
            "already seen). May cause double claiming; requires review."
        ),
        reason_code=ReasonCode.DUPLICATE,
        exposure_amount=exposure,
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=["R-ITC-ELIGIBILITY"],
    )


def _decide_invalid(match: MatchResult, settings: DecisionSettings) -> DecisionResult:
    return DecisionResult(
        match_result=match,
        action=Action.FLAG_FOR_REVIEW,
        priority=Priority.HIGH,
        flags=[Flag.INVALID_DATA],
        reason=(
            "Row failed Phase 1 validation. Preserved for review; no ITC "
            "action can be determined from invalid data."
        ),
        reason_code=ReasonCode.INVALID_DATA,
        exposure_amount=Decimal("0"),
        review_required=True,
        eligibility_status=EligibilityStatus.UNCERTAIN,
        rule_sources_applied=["R-ITC-ELIGIBILITY"],
    )


_STATUS_DECIDERS: dict[MatchStatus, Any] = {
    MatchStatus.EXACT: _decide_exact,
    MatchStatus.AMOUNT_MISMATCH: _decide_amount_mismatch,
    MatchStatus.TAX_HEAD_MISMATCH: _decide_tax_head_mismatch,
    MatchStatus.FUZZY: _decide_fuzzy,
    MatchStatus.PROBABLE: _decide_probable,
    MatchStatus.LOW_CONFIDENCE: _decide_low_confidence,
    MatchStatus.UNMATCHED_BOOKS: _decide_unmatched_books,
    MatchStatus.UNMATCHED_GSTR2B: _decide_unmatched_gstr2b,
    MatchStatus.DUPLICATE: _decide_duplicate,
    MatchStatus.INVALID: _decide_invalid,
}


def _priority_for_exposure(
    exposure: Decimal, settings: DecisionSettings
) -> Priority:
    """Return priority based on exposure amount (configurable assumption)."""
    if exposure >= settings.high_exposure_threshold:
        return Priority.HIGH
    if exposure >= settings.medium_exposure_threshold:
        return Priority.MEDIUM
    return Priority.LOW


# ---------------------------------------------------------------------------
# Human-review action policy
# ---------------------------------------------------------------------------

# The complete set of review decisions supported by the MVP.
REVIEW_DECISIONS: tuple[str, ...] = ("approve", "reject", "pending")

# Invalid rows cannot be approved: there is nothing valid to approve until the
# underlying data is corrected. They may still be rejected or left pending.
_STATUSES_WITHOUT_APPROVAL = frozenset({MatchStatus.INVALID})


def allowed_review_decisions(decision: DecisionResult) -> tuple[str, ...]:
    """Return the review decisions permitted for *decision*.

    The policy lives here, in the decision layer, so the UI cannot invent its
    own rules. Invalid rows may not be approved; every other reviewable row
    supports approve, reject, and pending.
    """
    if decision.match_result.match_status in _STATUSES_WITHOUT_APPROVAL:
        return tuple(d for d in REVIEW_DECISIONS if d != "approve")
    return REVIEW_DECISIONS


def validate_review_decision(
    decision: DecisionResult,
    review_decision: str,
) -> str:
    """Validate and normalise a human review decision.

    Returns the normalised decision string (``"approve"``, ``"reject"`` or
    ``"pending"``).

    Raises:
        ValueError: If the record does not require review, the decision is
            unknown, or the decision is not permitted for this record's
            status.
    """
    if not decision.review_required:
        raise ValueError(
            "This record does not require human review under the current "
            "decision policy."
        )
    if not isinstance(review_decision, str):
        raise ValueError("Review decision must be a string.")

    normalized = review_decision.strip().lower()
    if normalized not in REVIEW_DECISIONS:
        raise ValueError(
            f"Unknown review decision {review_decision!r}; expected one of "
            f"{', '.join(REVIEW_DECISIONS)}."
        )

    allowed = allowed_review_decisions(decision)
    if normalized not in allowed:
        raise ValueError(
            f"Review decision {normalized!r} is not permitted for match "
            f"status {decision.match_result.match_status.value!r}; allowed: "
            f"{', '.join(allowed)}."
        )
    return normalized


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def decide(
    match_result: MatchResult,
    rule_settings: RuleSettings | None = None,
    decision_settings: DecisionSettings | None = None,
) -> DecisionResult:
    """Apply decision rules to a single match result.

    Args:
        match_result: A reconciliation result from :func:`itc_sentinel.matcher.reconcile`.
        rule_settings: Rule calculation settings; defaults are used when None.
        decision_settings: Decision threshold settings; defaults are used when
            None.

    Returns:
        A :class:`DecisionResult` with suggested action, priority, flags,
        reason, exposure estimate, and review requirement.

    Raises:
        ValueError: If ``match_result.match_status`` is not a known status.
    """
    if rule_settings is None:
        rule_settings = DEFAULT_RULE_SETTINGS
    if decision_settings is None:
        decision_settings = DEFAULT_DECISION_SETTINGS

    status = match_result.match_status
    decider = _STATUS_DECIDERS.get(status)
    if decider is None:
        raise ValueError(f"Unknown match status: {status!r}")

    return decider(match_result, decision_settings)


def decide_all(
    results: Any,
    rule_settings: RuleSettings | None = None,
    decision_settings: DecisionSettings | None = None,
) -> list[DecisionResult]:
    """Apply decision rules to every match result in a reconciliation.

    Args:
        results: A :class:`itc_sentinel.matcher.ReconciliationResult` or an
            iterable of :class:`MatchResult`.
        rule_settings: Rule calculation settings.
        decision_settings: Decision threshold settings.

    Returns:
        A list of :class:`DecisionResult`, one per input match result, in
        input order.
    """
    if rule_settings is None:
        rule_settings = DEFAULT_RULE_SETTINGS
    if decision_settings is None:
        decision_settings = DEFAULT_DECISION_SETTINGS

    if hasattr(results, "matches"):
        match_results = list(results.matches)
    else:
        match_results = list(results)

    return [
        decide(m, rule_settings, decision_settings) for m in match_results
    ]


def total_exposure(decisions: list[DecisionResult]) -> Decimal:
    """Return the sum of exposure_amount across all decisions.

    This is a mechanical sum of provisional exposure estimates; it is not a
    confirmed ITC impact (rule R-CALC-TAX-EXPOSURE pending CA verification).
    """
    total = Decimal("0")
    for d in decisions:
        if d.exposure_amount is not None:
            total += d.exposure_amount
    return total.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)

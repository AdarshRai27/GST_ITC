"""Isolated GST / ITC rule calculations for the ITC Sentinel pipeline.

This module contains only mechanical, verifiable calculations plus a registry of
rule-source documentation. It does NOT determine GST ITC eligibility, which is
a tax/legal matter requiring Chartered Accountant (CA) review.

Design principles (per `rules.md:§4`):
- GST rule calculations are isolated here, each with a source / assumption and
  effective-date note.
- Monetary values use `Decimal` with the documented rounding policy
  (`MONEY_PLACES`); rounding/tolerance rules are explicit and tested.
- Unverified tax assumptions are visibly labelled as requiring CA verification;
  they are never presented as legal certainty.
- No LLM output can change amounts or decisions.

Public functions:
    calculate_amount_difference(book, gstr2b) -> Decimal | None
    calculate_tax_exposure(records) -> Decimal
    calculate_taxable_exposure(records) -> Decimal
    rule_sources() -> list[RuleSource]
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .schemas import MONEY_PLACES, NormalizedRecord

__all__ = [
    "RuleSource",
    "RuleSettings",
    "calculate_amount_difference",
    "calculate_tax_exposure",
    "calculate_taxable_exposure",
    "rule_sources",
]


@dataclass(frozen=True)
class RuleSource:
    """Documentation for a single rule or assumption.

    Attributes:
        rule_id: Stable identifier for the rule.
        description: Human-readable description of what the rule does.
        source: Origin of the rule (e.g. "documented assumption", "CA review
            pending", "mechanical calculation").
        assumption: The underlying assumption, if any.
        effective_date: Date from which the rule is assumed to apply, or None.
        ca_verification_required: True when the rule depends on tax law and
            must be validated by a qualified CA before being treated as
            reliable.
    """

    rule_id: str
    description: str
    source: str
    assumption: str | None = None
    effective_date: str | None = None
    ca_verification_required: bool = False


@dataclass(frozen=True)
class RuleSettings:
    """Configuration for rule calculations.

    All monetary thresholds and tolerances here are configurable assumptions
    pending CA validation; they are not statutory values.
    """

    # Amount-at-risk threshold above which a discrepancy is flagged as high
    # exposure. Configurable business assumption, not a statutory limit.
    amount_at_risk_threshold: Decimal = Decimal("10000.00")
    # Rounding quantum for monetary results (paise precision).
    money_places: Decimal = MONEY_PLACES


DEFAULT_RULE_SETTINGS = RuleSettings()


# ---------------------------------------------------------------------------
# Rule-source registry (documentation of assumptions)
# ---------------------------------------------------------------------------

_RULE_SOURCES: list[RuleSource] = [
    RuleSource(
        rule_id="R-CALC-AMOUNT-DIFF",
        description=(
            "Reconciliation difference = books taxable_value minus GSTR-2B "
            "taxable_value."
        ),
        source="mechanical calculation",
        assumption=None,
        effective_date=None,
        ca_verification_required=False,
    ),
    RuleSource(
        rule_id="R-CALC-TAX-EXPOSURE",
        description=(
            "ITC exposure at risk = sum of total_tax (CGST + SGST + IGST + "
            "cess) for flagged records."
        ),
        source="documented business assumption",
        assumption=(
            "Summing tax components estimates exposure; the actual ITC "
            "impact depends on eligibility rules outside this module."
        ),
        effective_date=None,
        ca_verification_required=True,
    ),
    RuleSource(
        rule_id="R-CALC-TAXABLE-EXPOSURE",
        description=(
            "Taxable-value exposure = sum of taxable_value for flagged "
            "records."
        ),
        source="documented business assumption",
        assumption=(
            "Taxable value is used as a proxy for exposure when tax "
            "components are unavailable."
        ),
        effective_date=None,
        ca_verification_required=True,
    ),
    RuleSource(
        rule_id="R-MATCH-EXACT",
        description=(
            "Same GSTIN, same invoice number, same date, same amounts => "
            "EXACT match."
        ),
        source="mechanical calculation",
        assumption=None,
        effective_date=None,
        ca_verification_required=False,
    ),
    RuleSource(
        rule_id="R-MATCH-AMOUNT-MISMATCH",
        description=(
            "Same GSTIN and invoice number, but monetary values differ => "
            "AMOUNT_MISMATCH."
        ),
        source="mechanical calculation",
        assumption=None,
        effective_date=None,
        ca_verification_required=False,
    ),
    RuleSource(
        rule_id="R-MATCH-TAX-HEAD",
        description=(
            "Same GSTIN and invoice number, but tax under a different head "
            "(domestic CGST/SGST vs IGST) => TAX_HEAD_MISMATCH."
        ),
        source="mechanical calculation",
        assumption=None,
        effective_date=None,
        ca_verification_required=False,
    ),
    RuleSource(
        rule_id="R-MATCH-FUZZY",
        description=(
            "Same GSTIN and same invoice-number core, but formatted "
            "differently => FUZZY match."
        ),
        source="mechanical calculation",
        assumption=None,
        effective_date=None,
        ca_verification_required=False,
    ),
    RuleSource(
        rule_id="R-MATCH-PROBABLE",
        description=(
            "Same GSTIN and high rapidfuzz invoice-number similarity, but "
            "different invoice-number core => PROBABLE match (uncertain)."
        ),
        source="mechanical calculation",
        assumption=(
            "Rapidfuzz similarity is a text-similarity heuristic, not an "
            "identity proof."
        ),
        effective_date=None,
        ca_verification_required=False,
    ),
    RuleSource(
        rule_id="R-ITC-ELIGIBILITY",
        description=(
            "Matching an invoice to GSTR-2B is NOT proof of ITC eligibility; "
            "eligibility is a tax/legal determination outside this module."
        ),
        source="documented business assumption",
        assumption=(
            "All match statuses map to eligibility_status UNCERTAIN unless a "
            "CA-validated rule states otherwise."
        ),
        effective_date=None,
        ca_verification_required=True,
    ),
]


def rule_sources() -> list[RuleSource]:
    """Return the documented rule sources and assumptions.

    Each entry identifies whether CA verification is required. Consumers
    should treat rules with ``ca_verification_required=True`` as provisional
    until validated against current official GST guidance.
    """
    return list(_RULE_SOURCES)


# ---------------------------------------------------------------------------
# Mechanical calculations
# ---------------------------------------------------------------------------


def calculate_amount_difference(
    book: NormalizedRecord | None,
    gstr2b: NormalizedRecord | None,
    settings: RuleSettings | None = None,
) -> Decimal | None:
    """Return books taxable_value minus GSTR-2B taxable_value.

    Returns None when either record is missing or either taxable_value is
    None. The result is quantized to two decimal places (paise precision)
    using ROUND_HALF_UP.

    This is a mechanical reconciliation difference. It is NOT a confirmed tax
    liability or ITC ineligibility determination.
    """
    if settings is None:
        settings = DEFAULT_RULE_SETTINGS
    if book is None or gstr2b is None:
        return None
    if book.taxable_value is None or gstr2b.taxable_value is None:
        return None
    return (book.taxable_value - gstr2b.taxable_value).quantize(
        settings.money_places
    )


def calculate_tax_exposure(
    records: list[NormalizedRecord],
    settings: RuleSettings | None = None,
) -> Decimal:
    """Return the sum of total_tax (CGST + SGST + IGST + cess) for *records*.

    Records with missing tax components contribute 0. The result is quantized
    to two decimal places using ROUND_HALF_UP.

    This is a mechanical sum of observed tax components. Calling it "ITC
    exposure at risk" is a business assumption (see rule R-CALC-TAX-EXPOSURE)
    pending CA verification; it is not a confirmed ITC impact.
    """
    if settings is None:
        settings = DEFAULT_RULE_SETTINGS
    total = Decimal("0")
    for r in records:
        if r.total_tax is not None:
            total += r.total_tax
    return total.quantize(settings.money_places)


def calculate_taxable_exposure(
    records: list[NormalizedRecord],
    settings: RuleSettings | None = None,
) -> Decimal:
    """Return the sum of taxable_value for *records*.

    Records with missing taxable_value contribute 0. The result is quantized
    to two decimal places using ROUND_HALF_UP.

    This is a mechanical sum of observed taxable values. Calling it exposure
    is a business assumption (see rule R-CALC-TAXABLE-EXPOSURE) pending CA
    verification; it is not a confirmed ITC impact.
    """
    if settings is None:
        settings = DEFAULT_RULE_SETTINGS
    total = Decimal("0")
    for r in records:
        if r.taxable_value is not None:
            total += r.taxable_value
    return total.quantize(settings.money_places)

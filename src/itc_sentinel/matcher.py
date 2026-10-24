"""Deterministic reconciliation for the ITC Sentinel pipeline.

Matches normalized purchase-register records against normalized GSTR-2B
records using deterministic rules: exact matching, constrained fuzzy
matching, and probable matching. Enforces same-GSTIN and one-to-one
constraints. Invalid records are preserved and classified separately.

All matching is deterministic: identical inputs and settings produce
identical results. No randomization is used. Matching is kept separate
from GST eligibility rules and financial decision recommendations
(those belong in Phase 3).

Public functions:
    reconcile(purchase_records, gstr2b_records, settings) -> ReconciliationResult
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from rapidfuzz import fuzz

from .schemas import (
    MONEY_PLACES,
    NormalizedRecord,
    ValidationStatus,
)

__all__ = [
    "MatchStatus",
    "ReconciliationSettings",
    "MatchResult",
    "ReconciliationResult",
    "reconcile",
]


class MatchStatus(str, Enum):
    """Classification of a reconciliation outcome.

    EXACT, AMOUNT_MISMATCH, TAX_HEAD_MISMATCH, FUZZY, PROBABLE and
    LOW_CONFIDENCE describe matched pairs. UNMATCHED_BOOKS and
    UNMATCHED_GSTR2B describe records with no counterpart. DUPLICATE
    describes a purchase-register row that repeats a GSTIN + invoice
    number already seen. INVALID describes a row that failed Phase 1
    validation and is preserved for review.
    """

    EXACT = "exact"
    AMOUNT_MISMATCH = "amount_mismatch"
    TAX_HEAD_MISMATCH = "tax_head_mismatch"
    FUZZY = "fuzzy"
    PROBABLE = "probable"
    LOW_CONFIDENCE = "low_confidence"
    UNMATCHED_BOOKS = "unmatched_books"
    UNMATCHED_GSTR2B = "unmatched_gstr2b"
    DUPLICATE = "duplicate"
    INVALID = "invalid"


# ---------------------------------------------------------------------------
# Default settings (documented assumptions pending validation)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationSettings:
    """Configuration for deterministic reconciliation.

    All thresholds are configurable assumptions. They are intentionally
    conservative: a match below LOW_CONFIDENCE_THRESHOLD is never treated
    as confirmed.
    """

    # Minimum rapidfuzz similarity (0-100) for a fuzzy match candidate.
    fuzzy_threshold: float = 85.0
    # Minimum rapidfuzz similarity (0-100) for a probable match candidate.
    probable_threshold: float = 70.0
    # Below this confidence (0.0-1.0), a match is never auto-confirmed; it
    # requires human review.
    low_confidence_threshold: float = 0.60
    # Amount tolerance for considering two monetary values equal.
    # Decimal("0.00") means exact match required.
    amount_tolerance: Decimal = Decimal("0.00")


DEFAULT_SETTINGS = ReconciliationSettings()


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class MatchResult:
    """Outcome for one purchase-register record in the reconciliation.

    Exactly one of ``purchase_record`` or ``gstr2b_record`` may be None
    for unmatched records. For matched pairs, both are present.

    Attributes:
        purchase_record: The purchase-register record, or None if this
            result describes an unmatched GSTR-2B record.
        gstr2b_record: The GSTR-2B record, or None if this result
            describes an unmatched purchase-register record.
        match_status: Classification of the outcome.
        confidence: Confidence score from 0.0 to 1.0.
        reason: Human-readable explanation of the match or non-match.
        discrepancies: List of field names that differ between the two
            records (empty when there are no discrepancies).
        amount_difference: Difference in taxable_value (books minus 2B),
            or None when not applicable or either amount is missing.
        tax_head_difference: True when tax is under a different head
            (e.g. CGST+SGST vs IGST) between the two records.
    """

    purchase_record: NormalizedRecord | None
    gstr2b_record: NormalizedRecord | None
    match_status: MatchStatus
    confidence: float
    reason: str
    discrepancies: list[str] = field(default_factory=list)
    amount_difference: Decimal | None = None
    tax_head_difference: bool = False


@dataclass
class ReconciliationResult:
    """Aggregated outcome of reconciling two datasets.

    Attributes:
        matches: One MatchResult per processed record (matched pairs,
            unmatched records, duplicates, invalid records).
        matched_pairs: Subset of matches with a counterpart on both sides.
        unmatched_books: Purchase-register records with no GSTR-2B match.
        unmatched_gstr2b: GSTR-2B records with no purchase-register match.
        invalid_records: Records that failed Phase 1 validation.
        duplicate_records: Duplicate purchase-register rows.
        summary: Counts by match status for reporting.
        settings: The settings used for this run.
    """

    matches: list[MatchResult] = field(default_factory=list)
    settings: ReconciliationSettings = field(
        default_factory=lambda: DEFAULT_SETTINGS
    )

    @property
    def matched_pairs(self) -> list[MatchResult]:
        return [
            m
            for m in self.matches
            if m.purchase_record is not None
            and m.gstr2b_record is not None
            and m.match_status
            in (
                MatchStatus.EXACT,
                MatchStatus.AMOUNT_MISMATCH,
                MatchStatus.TAX_HEAD_MISMATCH,
                MatchStatus.FUZZY,
                MatchStatus.PROBABLE,
                MatchStatus.LOW_CONFIDENCE,
            )
        ]

    @property
    def unmatched_books(self) -> list[NormalizedRecord]:
        return [
            m.purchase_record
            for m in self.matches
            if m.purchase_record is not None
            and m.gstr2b_record is None
            and m.match_status
            in (MatchStatus.UNMATCHED_BOOKS, MatchStatus.DUPLICATE)
        ]

    @property
    def unmatched_gstr2b(self) -> list[NormalizedRecord]:
        return [
            m.gstr2b_record
            for m in self.matches
            if m.gstr2b_record is not None
            and m.purchase_record is None
            and m.match_status == MatchStatus.UNMATCHED_GSTR2B
        ]

    @property
    def invalid_records(self) -> list[NormalizedRecord]:
        return [
            m.purchase_record
            for m in self.matches
            if m.purchase_record is not None
            and m.match_status == MatchStatus.INVALID
        ] + [
            m.gstr2b_record
            for m in self.matches
            if m.gstr2b_record is not None
            and m.match_status == MatchStatus.INVALID
        ]

    @property
    def duplicate_records(self) -> list[NormalizedRecord]:
        return [
            m.purchase_record
            for m in self.matches
            if m.purchase_record is not None
            and m.match_status == MatchStatus.DUPLICATE
        ]

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for m in self.matches:
            key = m.match_status.value
            counts[key] = counts.get(key, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _same_gstin(a: NormalizedRecord, b: NormalizedRecord) -> bool:
    """Return True when both records share a non-None, equal GSTIN."""
    return a.gstin is not None and b.gstin is not None and a.gstin == b.gstin


def _amounts_equal(
    a: Decimal | None,
    b: Decimal | None,
    tolerance: Decimal,
) -> bool:
    """Return True when two amounts are equal within tolerance."""
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


def _tax_head_mismatch(a: NormalizedRecord, b: NormalizedRecord) -> bool:
    """Return True when tax is under a different head between two records.

    A tax-head mismatch occurs when one record has domestic tax
    (CGST/SGST) with no IGST, and the other has IGST with no domestic tax.
    """
    a_domestic = (a.cgst or Decimal("0")) > 0 or (a.sgst or Decimal("0")) > 0
    a_igst = (a.igst or Decimal("0")) > 0
    b_domestic = (b.cgst or Decimal("0")) > 0 or (b.sgst or Decimal("0")) > 0
    b_igst = (b.igst or Decimal("0")) > 0
    return (a_domestic and not a_igst and b_igst and not b_domestic) or (
        b_domestic and not b_igst and a_igst and not a_domestic
    )


def _discrepancies(
    a: NormalizedRecord,
    b: NormalizedRecord,
    settings: ReconciliationSettings,
) -> list[str]:
    """Return the list of fields that differ between two records."""
    diffs: list[str] = []
    if not _amounts_equal(a.taxable_value, b.taxable_value, settings.amount_tolerance):
        diffs.append("taxable_value")
    if not _amounts_equal(a.cgst, b.cgst, settings.amount_tolerance):
        diffs.append("cgst")
    if not _amounts_equal(a.sgst, b.sgst, settings.amount_tolerance):
        diffs.append("sgst")
    if not _amounts_equal(a.igst, b.igst, settings.amount_tolerance):
        diffs.append("igst")
    if not _amounts_equal(a.cess, b.cess, settings.amount_tolerance):
        diffs.append("cess")
    if a.invoice_date != b.invoice_date:
        diffs.append("invoice_date")
    return diffs


def _amount_difference(
    a: NormalizedRecord,
    b: NormalizedRecord,
) -> Decimal | None:
    """Return books taxable_value minus 2B taxable_value, or None."""
    if a.taxable_value is None or b.taxable_value is None:
        return None
    return (a.taxable_value - b.taxable_value).quantize(
        MONEY_PLACES
    )


def _invoice_similarity(a: str, b: str) -> float:
    """Return rapidfuzz similarity (0-100) between two invoice numbers."""
    return fuzz.ratio(a or "", b or "")


# Non-alphanumeric characters stripped when comparing invoice "cores" for
# fuzzy matching. This prevents unrelated invoice numbers like
# "INV-5001" and "INV-8001" from matching solely on rapidfuzz similarity.
_INVOICE_CORE_RE = re.compile(r"[^A-Za-z0-9]")


def _invoice_core(value: str) -> str:
    """Return the alphanumeric core of an invoice number.

    "INV-3001" and "INV 3001" both reduce to "INV3001", enabling formatting
    differences to be detected without matching unrelated invoice numbers.
    """
    return _INVOICE_CORE_RE.sub("", value or "").upper()


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------


@dataclass
class _Candidate:
    """A potential match between one book record and one GSTR-2B record."""

    purchase_record: NormalizedRecord
    gstr2b_record: NormalizedRecord
    status: MatchStatus
    confidence: float
    reason: str
    discrepancies: list[str]
    amount_difference: Decimal | None
    tax_head_difference: bool


def _generate_candidates(
    books: list[NormalizedRecord],
    gstr2b: list[NormalizedRecord],
    settings: ReconciliationSettings,
) -> list[_Candidate]:
    """Generate all candidate matches within shared GSTIN groups.

    Candidates are only generated between records sharing the same
    normalized GSTIN (same-GSTIN constraint).
    """
    # Group by GSTIN for deterministic, same-GSTIN-only comparison.
    books_by_gstin: dict[str, list[NormalizedRecord]] = {}
    for r in books:
        if r.gstin is not None:
            books_by_gstin.setdefault(r.gstin, []).append(r)

    gstr2b_by_gstin: dict[str, list[NormalizedRecord]] = {}
    for r in gstr2b:
        if r.gstin is not None:
            gstr2b_by_gstin.setdefault(r.gstin, []).append(r)

    candidates: list[_Candidate] = []

    for gstin in sorted(set(books_by_gstin) & set(gstr2b_by_gstin)):
        group_books = sorted(books_by_gstin[gstin], key=lambda r: r.source_row)
        group_gstr2b = sorted(gstr2b_by_gstin[gstin], key=lambda r: r.source_row)

        for b in group_books:
            for g in group_gstr2b:
                cand = _evaluate_pair(b, g, settings)
                if cand is not None:
                    candidates.append(cand)

    # Sort deterministically: match-status priority first (exact matches
    # before fuzzy/probable), then highest confidence, then source rows.
    # This prevents a lower-quality probable match to the wrong invoice
    # from beating a higher-quality mismatch match to the correct invoice.
    _STATUS_PRIORITY = {
        MatchStatus.EXACT: 0,
        MatchStatus.AMOUNT_MISMATCH: 1,
        MatchStatus.TAX_HEAD_MISMATCH: 2,
        MatchStatus.FUZZY: 3,
        MatchStatus.PROBABLE: 4,
    }

    candidates.sort(
        key=lambda c: (
            _STATUS_PRIORITY[c.status],
            -c.confidence,
            c.purchase_record.source_row,
            c.gstr2b_record.source_row,
        )
    )
    return candidates


def _evaluate_pair(
    book: NormalizedRecord,
    gstr: NormalizedRecord,
    settings: ReconciliationSettings,
) -> _Candidate | None:
    """Evaluate one book/GSTR-2B pair and return a candidate, or None.

    Returns None when the pair cannot match at any confidence level
    (e.g. invoice numbers are too dissimilar).
    """
    b_inv = book.invoice_number or ""
    g_inv = gstr.invoice_number or ""

    # Exact invoice-number match.
    if b_inv and g_inv and b_inv == g_inv:
        discrepancies = _discrepancies(book, gstr, settings)
        tax_head = _tax_head_mismatch(book, gstr)
        amt_diff = _amount_difference(book, gstr)

        if not discrepancies and not tax_head:
            return _Candidate(
                book,
                gstr,
                MatchStatus.EXACT,
                1.0,
                "Exact match: same GSTIN, invoice number, date, and amounts.",
                [],
                None,
                False,
            )
        if tax_head:
            return _Candidate(
                book,
                gstr,
                MatchStatus.TAX_HEAD_MISMATCH,
                0.85,
                "Same GSTIN and invoice number, but tax is under a different "
                "head (domestic CGST/SGST vs IGST).",
                discrepancies,
                amt_diff,
                True,
            )
        return _Candidate(
            book,
            gstr,
            MatchStatus.AMOUNT_MISMATCH,
            0.9,
            "Same GSTIN and invoice number, but monetary values differ.",
            discrepancies,
            amt_diff,
            False,
        )

    # Fuzzy / probable match on invoice number.
    # Fuzzy requires the invoice "cores" (alphanumeric only) to be equal,
    # which constrains matching to formatting differences (e.g. "INV-3001"
    # vs "INV 3001") and prevents unrelated numbers like "INV-5001" vs
    # "INV-8001" from matching on rapidfuzz similarity alone.
    if b_inv and g_inv:
        b_core = _invoice_core(b_inv)
        g_core = _invoice_core(g_inv)
        if b_core and g_core and b_core == g_core and b_inv != g_inv:
            similarity = _invoice_similarity(b_inv, g_inv)
            discrepancies = _discrepancies(book, gstr, settings)
            tax_head = _tax_head_mismatch(book, gstr)
            amt_diff = _amount_difference(book, gstr)
            conf = similarity / 100.0
            return _Candidate(
                book,
                gstr,
                MatchStatus.FUZZY,
                conf,
                f"Fuzzy invoice-number match (similarity {similarity:.0f}).",
                discrepancies,
                amt_diff,
                tax_head,
            )
        similarity = _invoice_similarity(b_inv, g_inv)
        if similarity >= settings.probable_threshold:
            return _Candidate(
                book,
                gstr,
                MatchStatus.PROBABLE,
                similarity / 100.0,
                f"Probable invoice-number match (similarity {similarity:.0f}).",
                [],
                None,
                False,
            )

    return None


# ---------------------------------------------------------------------------
# Main reconciliation
# ---------------------------------------------------------------------------


def reconcile(
    purchase_records: list[NormalizedRecord],
    gstr2b_records: list[NormalizedRecord],
    settings: ReconciliationSettings | None = None,
) -> ReconciliationResult:
    """Reconcile purchase-register records against GSTR-2B records.

    Args:
        purchase_records: Normalized purchase-register records (from
            :func:`itc_sentinel.normalize.normalize_records`).
        gstr2b_records: Normalized GSTR-2B records.
        settings: Reconciliation settings; defaults are used when None.

    Returns:
        A :class:`ReconciliationResult` with one MatchResult per input
        record, classified as matched, unmatched, duplicate, or invalid.
    """
    if settings is None:
        settings = DEFAULT_SETTINGS

    matches: list[MatchResult] = []

    # --- Invalid records (failed Phase 1 validation) ---------------------
    invalid_books = [
        r
        for r in purchase_records
        if r.validation_status == ValidationStatus.INVALID
    ]
    invalid_gstr2b = [
        r
        for r in gstr2b_records
        if r.validation_status == ValidationStatus.INVALID
    ]
    for r in invalid_books:
        matches.append(
            MatchResult(
                purchase_record=r,
                gstr2b_record=None,
                match_status=MatchStatus.INVALID,
                confidence=0.0,
                reason="Row failed Phase 1 validation; preserved for review.",
                discrepancies=[
                    i.field for i in r.validation_issues
                ],
            )
        )
    for r in invalid_gstr2b:
        matches.append(
            MatchResult(
                purchase_record=None,
                gstr2b_record=r,
                match_status=MatchStatus.INVALID,
                confidence=0.0,
                reason="Row failed Phase 1 validation; preserved for review.",
                discrepancies=[
                    i.field for i in r.validation_issues
                ],
            )
        )

    # --- Valid records ---------------------------------------------------
    valid_books = [
        r for r in purchase_records if r.validation_status == ValidationStatus.VALID
    ]
    valid_gstr2b = [
        r for r in gstr2b_records if r.validation_status == ValidationStatus.VALID
    ]

    # --- Duplicate detection (purchase register only) -------------------
    seen_keys: set[tuple[str, str]] = set()
    duplicate_books: list[NormalizedRecord] = []
    unique_books: list[NormalizedRecord] = []
    for r in sorted(valid_books, key=lambda x: x.source_row):
        key = (r.gstin or "", r.invoice_number or "")
        if key in seen_keys:
            duplicate_books.append(r)
        else:
            seen_keys.add(key)
            unique_books.append(r)

    for r in duplicate_books:
        matches.append(
            MatchResult(
                purchase_record=r,
                gstr2b_record=None,
                match_status=MatchStatus.DUPLICATE,
                confidence=0.0,
                reason=(
                    f"Duplicate purchase-register row: GSTIN {r.gstin}, "
                    f"invoice {r.invoice_number} already seen."
                ),
                discrepancies=["duplicate_invoice"],
            )
        )

    # --- Candidate generation (same GSTIN only) -------------------------
    candidates = _generate_candidates(unique_books, valid_gstr2b, settings)

    # --- Greedy one-to-one matching -------------------------------------
    used_books: set[int] = set()
    used_gstr2b: set[int] = set()

    for cand in candidates:
        b_id = id(cand.purchase_record)
        g_id = id(cand.gstr2b_record)
        if b_id in used_books or g_id in used_gstr2b:
            continue  # one-to-one constraint: each record used at most once
        used_books.add(b_id)
        used_gstr2b.add(g_id)

        status = cand.status
        conf = cand.confidence
        reason = cand.reason
        if conf < settings.low_confidence_threshold:
            status = MatchStatus.LOW_CONFIDENCE
            reason = (
                f"Low-confidence match (score {conf:.2f}); requires human review. "
                + reason
            )

        matches.append(
            MatchResult(
                purchase_record=cand.purchase_record,
                gstr2b_record=cand.gstr2b_record,
                match_status=status,
                confidence=conf,
                reason=reason,
                discrepancies=cand.discrepancies,
                amount_difference=cand.amount_difference,
                tax_head_difference=cand.tax_head_difference,
            )
        )

    # --- Unmatched records ----------------------------------------------
    for r in unique_books:
        if id(r) not in used_books:
            matches.append(
                MatchResult(
                    purchase_record=r,
                    gstr2b_record=None,
                    match_status=MatchStatus.UNMATCHED_BOOKS,
                    confidence=0.0,
                    reason="No matching GSTR-2B invoice found for this GSTIN and invoice.",
                )
            )

    for r in valid_gstr2b:
        if id(r) not in used_gstr2b:
            matches.append(
                MatchResult(
                    purchase_record=None,
                    gstr2b_record=r,
                    match_status=MatchStatus.UNMATCHED_GSTR2B,
                    confidence=0.0,
                    reason="No matching purchase-register invoice found for this GSTIN and invoice.",
                )
            )

    return ReconciliationResult(matches=matches, settings=settings)

"""Deterministic vendor message drafts for Phase 4.

Generates editable draft vendor follow-up messages based on reconciliation
findings. Drafts are drafts only: they are never sent, and no external
communication is executed.

Design principles (per `requirements.md`, `architecture.md`, `rules.md`):
- Generate drafts only for supported, documented discrepancy categories.
- Include only relevant, traceable invoice details; never invent amounts,
  dates, invoice numbers, or vendor details.
- Use clear, professional and neutral wording.
- Distinguish missing information from confirmed discrepancies.
- Avoid unsupported accusations, legal claims, or definitive statements about
  ITC eligibility.
- Preserve drafts for human review and editing before use.
- LLM enhancement is optional and isolated behind `llm.py`; a deterministic
  template fallback works without an API key or network connection.

Public classes:
    VendorDraft
    DraftCategory

Public functions:
    draft_vendor_message(decision, category) -> VendorDraft
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .audit import _utc_now_iso
from .decision import DecisionResult, ReasonCode

__all__ = [
    "DraftCategory",
    "VendorDraft",
    "draft_vendor_message",
]


class DraftCategory(str, Enum):
    """Supported draft categories (documented discrepancy categories only)."""

    AMOUNT_MISMATCH = "amount_mismatch"
    TAX_HEAD_MISMATCH = "tax_head_mismatch"
    MISSING_IN_2B = "missing_in_2b"
    DUPLICATE = "duplicate"
    INVALID_DATA = "invalid_data"
    LOW_CONFIDENCE = "low_confidence_match"


@dataclass
class VendorDraft:
    """A single editable vendor message draft.

    Attributes:
        draft_id: Stable UUID v4 identifier.
        created_at: ISO 8601 UTC timestamp when the draft was created.
        category: Draft category.
        invoice_key: (gstin, invoice_number) for traceability, or None.
        vendor_name: Vendor name if known, else None.
        gstin: Supplier GSTIN if known, else None.
        invoice_number: Invoice number if known, else None.
        subject: Email subject line.
        body_email: Full email body draft.
        body_whatsapp: Short WhatsApp draft.
        source_values: Traceable source values used to build the draft.
        notes: Human-readable notes on what is missing vs confirmed.
        editable: True (drafts are always editable before use).
        llm_enhanced: True if an LLM enhanced the wording; False for template.
    """

    draft_id: str
    created_at: str
    category: str
    invoice_key: str | None
    vendor_name: str | None
    gstin: str | None
    invoice_number: str | None
    subject: str
    body_email: str
    body_whatsapp: str
    source_values: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    editable: bool = True
    llm_enhanced: bool = False


# ---------------------------------------------------------------------------
# Template builders
# ---------------------------------------------------------------------------


def _template_amount_mismatch(draft: VendorDraft) -> VendorDraft:
    gstin = draft.gstin or "not available"
    inv = draft.invoice_number or "not available"
    sv = draft.source_values
    books_amount = sv.get("books_taxable_value")
    two_b_amount = sv.get("gstr2b_taxable_value")
    diff = sv.get("amount_difference")

    subject = f"Clarification requested: invoice {inv} amount mismatch"
    body_email = (
        f"Dear {draft.vendor_name or 'Vendor'},\n\n"
        f"We are reconciling our purchase register against our GSTR-2B "
        f"records for GSTIN {gstin}.\n\n"
        f"For invoice number {inv}, we noticed a difference between the "
        f"amounts recorded:\n"
        f"- Purchase register (books): {books_amount}\n"
        f"- GSTR-2B: {two_b_amount}\n"
        f"- Difference: {diff}\n\n"
        f"Please clarify the correct invoice amount and, if applicable, "
        f"share a revised invoice or credit/debit note so we can reconcile "
        f"our records accurately.\n\n"
        f"This is a clarification request only and does not constitute any "
        f"claim regarding ITC eligibility.\n\n"
        f"Thank you.\n"
    )
    body_whatsapp = (
        f"Hello {draft.vendor_name or ''}, please clarify the amount for "
        f"invoice {inv} (GSTIN {gstin}). Books: {books_amount}, GSTR-2B: "
        f"{two_b_amount}, difference: {diff}. Share a revised invoice if "
        f"needed. Thank you."
    )
    notes = (
        "Confirmed discrepancy: amounts differ between purchase register "
        "and GSTR-2B. Please provide clarification."
    )
    draft.subject = subject
    draft.body_email = body_email
    draft.body_whatsapp = body_whatsapp
    draft.notes = notes
    return draft


def _template_tax_head_mismatch(draft: VendorDraft) -> VendorDraft:
    gstin = draft.gstin or "not available"
    inv = draft.invoice_number or "not available"
    subject = f"Clarification requested: invoice {inv} tax-head mismatch"
    body_email = (
        f"Dear {draft.vendor_name or 'Vendor'},\n\n"
        f"We are reconciling our purchase register against our GSTR-2B "
        f"records for GSTIN {gstin}.\n\n"
        f"For invoice number {inv}, the tax appears to be reported under a "
        f"different head in our records versus GSTR-2B (for example, "
        f"domestic CGST/SGST versus IGST).\n\n"
        f"Please confirm the correct tax head and share supporting documents "
        f"so we can reconcile accurately.\n\n"
        f"This is a clarification request only and does not constitute any "
        f"claim regarding ITC eligibility.\n\n"
        f"Thank you.\n"
    )
    body_whatsapp = (
        f"Hello {draft.vendor_name or ''}, please confirm the tax head for "
        f"invoice {inv} (GSTIN {gstin}) - domestic CGST/SGST or IGST. Share "
        f"supporting documents. Thank you."
    )
    notes = (
        "Confirmed discrepancy: tax reported under different heads between "
        "purchase register and GSTR-2B. Please confirm correct tax head."
    )
    draft.subject = subject
    draft.body_email = body_email
    draft.body_whatsapp = body_whatsapp
    draft.notes = notes
    return draft


def _template_missing_in_2b(draft: VendorDraft) -> VendorDraft:
    gstin = draft.gstin or "not available"
    inv = draft.invoice_number or "not available"
    sv = draft.source_values
    amount = sv.get("taxable_value")
    subject = f"Invoice {inv} not found in GSTR-2B"
    body_email = (
        f"Dear {draft.vendor_name or 'Vendor'},\n\n"
        f"We are reconciling our purchase register against our GSTR-2B "
        f"records for GSTIN {gstin}.\n\n"
        f"Invoice number {inv} (taxable value: {amount}) appears in our "
        f"purchase register but was not found in the GSTR-2B records "
        f"available to us.\n\n"
        f"Please confirm whether this invoice was uploaded to the GST "
        f"portal and share any supporting details so we can reconcile our "
        f"records.\n\n"
        f"This is an information request only and does not constitute any "
        f"claim regarding ITC eligibility.\n\n"
        f"Thank you.\n"
    )
    body_whatsapp = (
        f"Hello {draft.vendor_name or ''}, invoice {inv} (GSTIN {gstin}, "
        f"taxable value: {amount}) appears in our books but not in GSTR-2B. "
        f"Please confirm if uploaded to GST portal. Thank you."
    )
    notes = (
        "Missing information: invoice present in purchase register but not "
        "found in GSTR-2B. Please confirm upload status."
    )
    draft.subject = subject
    draft.body_email = body_email
    draft.body_whatsapp = body_whatsapp
    draft.notes = notes
    return draft


def _template_duplicate(draft: VendorDraft) -> VendorDraft:
    gstin = draft.gstin or "not available"
    inv = draft.invoice_number or "not available"
    subject = f"Duplicate invoice {inv} in our records"
    body_email = (
        f"Dear {draft.vendor_name or 'Vendor'},\n\n"
        f"We are reconciling our purchase register for GSTIN {gstin}.\n\n"
        f"Our records show invoice number {inv} appearing more than once. "
        f"Please confirm whether this is a duplicate entry or whether "
        f"separate invoices share the same number, and share corrected "
        f"documentation if needed.\n\n"
        f"This is an information request only and does not constitute any "
        f"claim regarding ITC eligibility.\n\n"
        f"Thank you.\n"
    )
    body_whatsapp = (
        f"Hello {draft.vendor_name or ''}, invoice {inv} (GSTIN {gstin}) "
        f"appears more than once in our records. Please confirm if duplicate "
        f"or separate invoices. Thank you."
    )
    notes = (
        "Confirmed discrepancy: duplicate invoice number in purchase "
        "register. Please confirm."
    )
    draft.subject = subject
    draft.body_email = body_email
    draft.body_whatsapp = body_whatsapp
    draft.notes = notes
    return draft


def _template_invalid_data(draft: VendorDraft) -> VendorDraft:
    gstin = draft.gstin or "not available"
    inv = draft.invoice_number or "not available"
    subject = f"Invoice {inv} - invalid or incomplete data"
    body_email = (
        f"Dear {draft.vendor_name or 'Vendor'},\n\n"
        f"We are reconciling our purchase register for GSTIN {gstin}.\n\n"
        f"Invoice number {inv} could not be processed because it contains "
        f"invalid or incomplete data (for example, an invalid GSTIN, date, "
        f"or amount). Please review and share corrected details.\n\n"
        f"This is an information request only and does not constitute any "
        f"claim regarding ITC eligibility.\n\n"
        f"Thank you.\n"
    )
    body_whatsapp = (
        f"Hello {draft.vendor_name or ''}, invoice {inv} (GSTIN {gstin}) "
        f"has invalid or incomplete data. Please review and share corrected "
        f"details. Thank you."
    )
    notes = (
        "Missing information: invoice row failed validation. Please provide "
        "corrected details."
    )
    draft.subject = subject
    draft.body_email = body_email
    draft.body_whatsapp = body_whatsapp
    draft.notes = notes
    return draft


def _template_low_confidence(draft: VendorDraft) -> VendorDraft:
    gstin = draft.gstin or "not available"
    inv = draft.invoice_number or "not available"
    subject = f"Invoice {inv} - low-confidence match, please confirm"
    body_email = (
        f"Dear {draft.vendor_name or 'Vendor'},\n\n"
        f"We are reconciling our purchase register against our GSTR-2B "
        f"records for GSTIN {gstin}.\n\n"
        f"Invoice number {inv} was matched with low confidence. Please "
        f"confirm whether this invoice corresponds to your records so we "
        f"can reconcile accurately.\n\n"
        f"This is a confirmation request only and does not constitute any "
        f"claim regarding ITC eligibility.\n\n"
        f"Thank you.\n"
    )
    body_whatsapp = (
        f"Hello {draft.vendor_name or ''}, please confirm whether invoice "
        f"{inv} (GSTIN {gstin}) corresponds to your records. Thank you."
    )
    notes = (
        "Uncertain match: low-confidence match requires vendor confirmation."
    )
    draft.subject = subject
    draft.body_email = body_email
    draft.body_whatsapp = body_whatsapp
    draft.notes = notes
    return draft


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _decision_to_category(decision: DecisionResult) -> DraftCategory | None:
    """Map a decision's reason code / flags to a supported draft category."""
    code = decision.reason_code
    mapping = {
        ReasonCode.AMOUNT_MISMATCH: DraftCategory.AMOUNT_MISMATCH,
        ReasonCode.TAX_HEAD_MISMATCH: DraftCategory.TAX_HEAD_MISMATCH,
        ReasonCode.UNMATCHED_BOOKS: DraftCategory.MISSING_IN_2B,
        ReasonCode.DUPLICATE: DraftCategory.DUPLICATE,
        ReasonCode.INVALID_DATA: DraftCategory.INVALID_DATA,
        ReasonCode.LOW_CONFIDENCE_MATCH: DraftCategory.LOW_CONFIDENCE,
    }
    return mapping.get(code)


def _source_values_from_match(decision: DecisionResult) -> dict[str, Any]:
    """Extract traceable source values from a decision's match result."""
    match = decision.match_result
    sv: dict[str, Any] = {}
    book = match.purchase_record
    gstr2b = match.gstr2b_record
    if book is not None:
        sv["books_taxable_value"] = str(book.taxable_value) if book.taxable_value is not None else None
        sv["books_total_amount"] = str(book.total_amount) if book.total_amount is not None else None
        sv["books_cgst"] = str(book.cgst) if book.cgst is not None else None
        sv["books_sgst"] = str(book.sgst) if book.sgst is not None else None
        sv["books_igst"] = str(book.igst) if book.igst is not None else None
        sv["books_cess"] = str(book.cess) if book.cess is not None else None
    if gstr2b is not None:
        sv["gstr2b_taxable_value"] = str(gstr2b.taxable_value) if gstr2b.taxable_value is not None else None
        sv["gstr2b_total_amount"] = str(gstr2b.total_amount) if gstr2b.total_amount is not None else None
    if match.amount_difference is not None:
        sv["amount_difference"] = str(match.amount_difference)
    return sv


def draft_vendor_message(
    decision: DecisionResult,
    category: DraftCategory | None = None,
    enhanced_by_llm: bool = False,
) -> VendorDraft:
    """Create a vendor message draft for a decision.

    Args:
        decision: A :class:`DecisionResult` from :func:`itc_sentinel.decision.decide`.
        category: Optional explicit category; inferred from the decision if
            not provided.
        enhanced_by_llm: Whether LLM wording enhancement was applied (delegated
            to :mod:`itc_sentinel.llm`). Default False (template only).

    Returns:
        A :class:`VendorDraft` ready for human review and editing.

    Raises:
        ValueError: If the decision's category is not supported.
    """
    if category is None:
        category = _decision_to_category(decision)
    if category is None:
        raise ValueError(
            f"No supported draft category for reason code "
            f"{decision.reason_code!r}"
        )

    match = decision.match_result
    book = match.purchase_record
    gstr2b = match.gstr2b_record
    gstin = book.gstin if book is not None else (
        gstr2b.gstin if gstr2b is not None else None
    )
    invoice_number = book.invoice_number if book is not None else (
        gstr2b.invoice_number if gstr2b is not None else None
    )
    vendor_name = book.vendor_name if book is not None else None

    invoice_key = None
    if gstin or invoice_number:
        invoice_key = f"{gstin or ''}|{invoice_number or ''}"

    draft = VendorDraft(
        draft_id="",  # assigned below
        created_at=_utc_now_iso(),
        category=category.value,
        invoice_key=invoice_key,
        vendor_name=vendor_name,
        gstin=gstin,
        invoice_number=invoice_number,
        subject="",
        body_email="",
        body_whatsapp="",
        source_values=_source_values_from_match(decision),
        notes="",
        editable=True,
        llm_enhanced=enhanced_by_llm,
    )

    import uuid
    draft.draft_id = str(uuid.uuid4())

    builders: dict[DraftCategory, Any] = {
        DraftCategory.AMOUNT_MISMATCH: _template_amount_mismatch,
        DraftCategory.TAX_HEAD_MISMATCH: _template_tax_head_mismatch,
        DraftCategory.MISSING_IN_2B: _template_missing_in_2b,
        DraftCategory.DUPLICATE: _template_duplicate,
        DraftCategory.INVALID_DATA: _template_invalid_data,
        DraftCategory.LOW_CONFIDENCE: _template_low_confidence,
    }
    builder = builders[category]
    return builder(draft)

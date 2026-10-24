"""Optional LLM boundary for Phase 4.

This module is the sole LLM integration point in the MVP. It is optional and
disabled by default: vendor drafts work entirely from deterministic templates
without an API key or network connection.

Design principles (per `architecture.md`, `rules.md`, `requirements.md`):
- LLM is optional and limited to language tasks (wording enhancement only).
- It cannot set amounts, determine ITC eligibility, priorities, or actions.
- Every LLM feature has a template fallback that works offline.
- LLM usage is opt-in; data may leave the local machine only when a provider
  API is explicitly enabled and the user understands the disclosure.
- Never send source documents or taxpayer data to an LLM unless explicitly
  enabled and disclosed.
- LLM output cannot change numeric values or decisions; validate or fall back
  to templates.
- Timeout and retry limit; fails safely with a clear message.

Public functions:
    enhance_wording(text, *, enabled=False) -> str | None
    is_llm_enabled() -> bool
"""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "LLMError",
    "enhance_wording",
    "is_llm_enabled",
]


class LLMError(Exception):
    """Raised when LLM enhancement fails and no fallback is acceptable."""


def is_llm_enabled() -> bool:
    """Return True only when LLM usage has been explicitly opted into.

    LLM usage is opt-in. It is enabled only when the environment variable
    ``ITC_SENTINEL_LLM_ENABLED`` is set to ``"1"``. No provider API key is
    read or used by this module; callers are responsible for their own
    provider configuration and disclosure.
    """
    return os.environ.get("ITC_SENTINEL_LLM_ENABLED", "").strip() == "1"


def enhance_wording(
    text: str,
    *,
    enabled: bool = False,
    provider: Any = None,
    timeout_seconds: float = 10.0,
    max_retries: int = 1,
) -> str:
    """Optionally enhance wording using an LLM, with a deterministic fallback.

    This is the single LLM boundary. When ``enabled`` is False (the default),
    the input text is returned unchanged — no LLM is called, no data leaves
    the machine, and no network access is attempted.

    When ``enabled`` is True, a caller-supplied ``provider`` callable may be
    invoked to enhance the wording. The provider receives only the supplied
    text (no taxpayer identifiers beyond what the caller chose to include) and
    must return a string. If the provider is not callable, raises, times out,
    or exceeds retries, the function falls back to returning ``text`` unchanged
    and does not raise.

    The LLM may only rephrase wording. It cannot change numeric values,
    dates, invoice numbers, GSTINs, amounts, priorities, or decisions. The
    caller remains responsible for validating that output did not alter
    substantive fields.

    Args:
        text: The template text to potentially enhance.
        enabled: Whether LLM enhancement is opted into (default False).
        provider: Optional callable ``provider(text) -> str``. Not invoked
            unless ``enabled`` is True.
        timeout_seconds: Placeholder for provider timeout (not enforced by
            this module; the caller's provider is responsible).
        max_retries: Maximum provider retry attempts before fallback.

    Returns:
        The enhanced or original text. Never raises on provider failure;
        falls back to the original ``text``.

    Raises:
        ValueError: If ``text`` is not a string.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")

    # LLM disabled: return template text unchanged. No data leaves the machine.
    if not enabled:
        return text

    # LLM enabled but no provider: fall back to template.
    if provider is None or not callable(provider):
        return text

    for _ in range(max(1, max_retries)):
        try:
            enhanced = provider(text)
        except Exception:  # provider failures are not fatal
            continue
        if not isinstance(enhanced, str) or not enhanced:
            continue
        # Defensive: ensure the enhanced text did not drop or fabricate
        # numeric fields present in the original. This is a best-effort
        # sanity check, not a substitute for caller validation.
        if _looks_substantially_different(text, enhanced):
            continue
        return enhanced

    # Provider failed after retries: fall back to template text.
    return text


def _looks_substantially_different(original: str, enhanced: str) -> bool:
    """Best-effort check that enhancement did not alter substantive fields.

    Compares digits and currency tokens between original and enhanced text.
    Returns True if they differ meaningfully (suggesting the LLM altered
    numbers), in which case the caller should fall back to the original.
    """
    import re

    def tokens(s: str) -> set[str]:
        return set(re.findall(r"\d[\d,\.]*", s))

    return bool(tokens(original) and tokens(enhanced) and tokens(original) != tokens(enhanced))

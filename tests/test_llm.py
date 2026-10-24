"""Tests for the LLM boundary module (src/itc_sentinel/llm.py).

Covers opt-in behavior, template fallback when disabled, provider failure
resilience, and substantive-field protection (numbers not altered).
"""

from __future__ import annotations

import pytest

from itc_sentinel.llm import LLMError, enhance_wording, is_llm_enabled

# ---------------------------------------------------------------------------
# is_llm_enabled
# ---------------------------------------------------------------------------


def test_is_llm_enabled_defaults_false(monkeypatch):
    monkeypatch.delenv("ITC_SENTINEL_LLM_ENABLED", raising=False)
    assert is_llm_enabled() is False


def test_is_llm_enabled_true(monkeypatch):
    monkeypatch.setenv("ITC_SENTINEL_LLM_ENABLED", "1")
    assert is_llm_enabled() is True


def test_is_llm_enabled_other_values_false(monkeypatch):
    monkeypatch.setenv("ITC_SENTINEL_LLM_ENABLED", "0")
    assert is_llm_enabled() is False
    monkeypatch.setenv("ITC_SENTINEL_LLM_ENABLED", "true")
    assert is_llm_enabled() is False


# ---------------------------------------------------------------------------
# enhance_wording disabled (default)
# ---------------------------------------------------------------------------


def test_enhance_wording_disabled_returns_original():
    text = "Please clarify the amount for invoice INV-001."
    result = enhance_wording(text, enabled=False)
    assert result == text


def test_enhance_wording_no_flag_returns_original():
    text = "Please confirm the tax head for invoice INV-002."
    result = enhance_wording(text)
    assert result == text


def test_enhance_wording_no_provider_returns_original(monkeypatch):
    monkeypatch.setenv("ITC_SENTINEL_LLM_ENABLED", "1")
    text = "Please clarify the amount for invoice INV-003."
    result = enhance_wording(text, enabled=True)
    assert result == text


# ---------------------------------------------------------------------------
# Provider success
# ---------------------------------------------------------------------------


def test_enhance_wording_provider_success():
    def provider(text: str) -> str:
        return text.replace("clarify", "please verify")

    text = "Please clarify the amount for invoice INV-004."
    result = enhance_wording(text, enabled=True, provider=provider)
    assert result == "Please please verify the amount for invoice INV-004."


# ---------------------------------------------------------------------------
# Provider failure -> fallback
# ---------------------------------------------------------------------------


def test_enhance_wording_provider_raises_fallback():
    def failing_provider(text: str) -> str:
        raise RuntimeError("provider down")

    text = "Please clarify the amount for invoice INV-005."
    result = enhance_wording(text, enabled=True, provider=failing_provider)
    assert result == text  # fallback to original


def test_enhance_wording_provider_returns_empty_fallback():
    def empty_provider(text: str) -> str:
        return ""

    text = "Please clarify the amount for invoice INV-006."
    result = enhance_wording(text, enabled=True, provider=empty_provider)
    assert result == text


def test_enhance_wording_provider_returns_non_string_fallback():
    def bad_provider(text: str) -> int:
        return 123

    text = "Please clarify the amount for invoice INV-007."
    result = enhance_wording(text, enabled=True, provider=bad_provider)
    assert result == text


# ---------------------------------------------------------------------------
# Substantive field protection
# ---------------------------------------------------------------------------


def test_enhance_wording_number_changes_rejected():
    """If the provider alters numbers, fall back to the original text."""
    def number_changing_provider(text: str) -> str:
        return text.replace("1000.00", "9999.00")

    text = "Amount: 1000.00. Please clarify."
    result = enhance_wording(text, enabled=True,
                             provider=number_changing_provider)
    assert result == text  # numbers changed, so fallback


def test_enhance_wording_rewording_allowed():
    """Rephrasing without number changes is allowed."""
    def reword_provider(text: str) -> str:
        return text.replace("clarify", "verify")

    text = "Please clarify the amount."
    result = enhance_wording(text, enabled=True, provider=reword_provider)
    assert result == "Please verify the amount."


# ---------------------------------------------------------------------------
# max_retries
# ---------------------------------------------------------------------------


def test_enhance_wording_retries_then_fallback():
    call_count = 0

    def always_fails(text: str) -> str:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("fail")

    text = "Please clarify the amount."
    result = enhance_wording(text, enabled=True, provider=always_fails,
                             max_retries=3)
    assert result == text
    assert call_count == 3


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------


def test_enhance_wording_non_string_raises():
    with pytest.raises(ValueError):
        enhance_wording(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LLMError is importable (interface contract)
# ---------------------------------------------------------------------------


def test_llm_error_is_exception():
    assert issubclass(LLMError, Exception)

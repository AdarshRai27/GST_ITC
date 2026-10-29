"""Reusable presentation helpers for ITC Sentinel.

Everything here is presentation-only. Components never compute reconciliation
metrics or review policy; callers pass in values that already came from the
deterministic pipeline, :mod:`itc_sentinel.metrics`, or
:mod:`itc_sentinel.decision`.

Dynamic text is escaped before it is placed in raw HTML. Uploaded values are
therefore never interpolated into markup without escaping.
"""

from __future__ import annotations

import html
import textwrap
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Iterable, Sequence

import streamlit as st

__all__ = [
    "brand_mark",
    "callout",
    "chip",
    "comparison_table",
    "empty_state",
    "footer",
    "format_inr",
    "key_value_table",
    "kpi_card",
    "page_header",
    "review_header",
    "secondary_stats",
    "section_header",
    "sidebar_brand",
    "status_breakdown",
    "welcome_intro",
    "workflow_steps",
]

_TONE_CLASS = {
    "positive": "is-positive",
    "warning": "is-warning",
    "error": "is-error",
    "neutral": "is-neutral",
}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------
def format_inr(value: object, *, decimals: int = 2) -> str:
    """Format a value as INR using Indian digit grouping.

    ``None`` becomes an em dash. Non-numeric values are returned unchanged so
    the UI never hides an unexpected source value.
    """
    if value is None or value == "":
        return "—"
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if not amount.is_finite():
        return "—"

    quantum = Decimal(1).scaleb(-decimals)
    amount = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    negative = amount < 0
    text = f"{abs(amount):.{decimals}f}"
    whole, _, fraction = text.partition(".")

    if len(whole) > 3:
        last_three = whole[-3:]
        rest = whole[:-3]
        groups: list[str] = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        whole = ",".join(groups + [last_three])

    sign = "-" if negative else ""
    suffix = f".{fraction}" if decimals else ""
    return f"{sign}₹{whole}{suffix}"


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _markup(value: str) -> str:
    """Dedent trusted markup and remove blank lines.

    Markdown ends an HTML block at a blank line, which would turn the remainder
    of a component into a code block. Stripping blank lines and indentation
    keeps every component inside one HTML block.
    """
    dedented = textwrap.dedent(value)
    lines = [line.strip() for line in dedented.splitlines() if line.strip()]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Brand and shell
# ---------------------------------------------------------------------------
def brand_mark(size: int = 20) -> str:
    """Return the static ledger/check mark used by the sidebar and welcome."""
    return (
        f'<svg width="{int(size)}" height="{int(size)}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="1.7" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M5 3.5h10.5L19 7v13.5H5z"/>'
        '<path d="M15.5 3.5V7H19"/>'
        '<path d="M8 10.5h7M8 13.5h4.5"/>'
        '<path d="M8.5 17l1.8 1.8 3.7-3.7"/>'
        "</svg>"
    )


def sidebar_brand(version: str) -> None:
    """Render the compact sidebar identity block."""
    st.markdown(_markup(
        f"""
        <div class="itc-brand">
            <div class="itc-brand-mark">{brand_mark(21)}</div>
            <div>
                <div class="itc-brand-name">ITC Sentinel</div>
                <div class="itc-brand-desc">GST RECONCILIATION</div>
            </div>
        </div>
        <div class="itc-side-label">Workspace</div>
        <div class="itc-side-note">Version {_esc(version)} · Synthetic-data MVP</div>
        """),
        unsafe_allow_html=True,
    )


def page_header(
    *,
    source_label: str,
    source_tone: str,
    run_id: str | None,
) -> None:
    """Render the compact application header.

    ``source_tone`` is one of ``sample``, ``custom`` or ``neutral``.
    """
    tone_class = {
        "sample": "",
        "custom": " is-custom",
        "neutral": " is-neutral",
    }.get(source_tone, " is-neutral")
    run_html = (
        f'<div class="itc-runid">RUN {_esc(run_id[:8].upper())}</div>'
        if run_id
        else ""
    )
    st.markdown(_markup(
        f"""
        <div class="itc-header">
            <div class="itc-header-top">
                <div>
                    <div class="itc-eyebrow">Finance operations / Reconciliation</div>
                    <h1 class="itc-title">GST Reconciliation</h1>
                    <p class="itc-sub">
                        Match purchase-register invoices against GSTR-2B, surface
                        exceptions, and prepare review-ready reports.
                    </p>
                </div>
                <div class="itc-header-meta">
                    <span class="itc-pill{tone_class}">
                        <span class="itc-dot"></span>{_esc(source_label)}
                    </span>
                    {run_html}
                </div>
            </div>
        </div>
        <div class="itc-rule"></div>
        """),
        unsafe_allow_html=True,
    )


def section_header(
    title: str,
    description: str | None = None,
    *,
    eyebrow: str | None = None,
    level: int = 2,
) -> None:
    """Render a section heading with an optional eyebrow and description."""
    eyebrow_html = (
        f'<div class="itc-eyebrow">{_esc(eyebrow)}</div>' if eyebrow else ""
    )
    desc_html = (
        f'<p class="itc-section-desc">{_esc(description)}</p>'
        if description
        else ""
    )
    heading = "h3" if level == 3 else "h2"
    st.markdown(_markup(
        f"""
        <div class="itc-section-head">
            {eyebrow_html}
            <{heading} class="itc-section-title">{_esc(title)}</{heading}>
            {desc_html}
        </div>
        """),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Welcome / empty states
# ---------------------------------------------------------------------------
def welcome_intro() -> None:
    """Render the first-load introduction panel."""
    st.markdown(_markup(
        f"""
        <div class="itc-welcome">
            <div class="itc-welcome-mark">{brand_mark(27)}</div>
            <div>
                <div class="itc-eyebrow">Synthetic-data workspace</div>
                <h2>Reconcile GST input tax credit with a reviewable trail.</h2>
                <p>
                    ITC Sentinel compares a purchase register with GSTR-2B,
                    classifies every difference, and keeps a human in control of
                    every review decision. No filing, payment hold, or vendor
                    message is ever sent automatically.
                </p>
            </div>
        </div>
        """),
        unsafe_allow_html=True,
    )


def workflow_steps() -> None:
    """Render the three-step workflow used on first load."""
    steps = [
        (
            "01",
            "Select inputs",
            "Use the synthetic fixture or upload a purchase register and a "
            "GSTR-2B JSON file.",
        ),
        (
            "02",
            "Reconcile invoices",
            "Run the deterministic matcher to classify exact matches, "
            "discrepancies, candidates, duplicates, and invalid rows.",
        ),
        (
            "03",
            "Review and export",
            "Record review outcomes, prepare vendor drafts, and export an "
            "audited Excel workbook.",
        ),
    ]
    cells = "".join(
        f"""
        <div class="itc-step">
            <div class="itc-step-num">{_esc(num)}</div>
            <h3>{_esc(title)}</h3>
            <p>{_esc(body)}</p>
        </div>
        """
        for num, title, body in steps
    )
    st.markdown(
        _markup(f'<div class="itc-steps">{cells}</div>'),
        unsafe_allow_html=True,
    )


def empty_state(title: str, body: str, hint: str | None = None) -> None:
    """Render a compact, intentional empty state."""
    hint_html = (
        f'<div class="itc-empty-hint">{_esc(hint)}</div>' if hint else ""
    )
    st.markdown(_markup(
        f"""
        <div class="itc-empty">
            <div class="itc-empty-title">{_esc(title)}</div>
            <div class="itc-empty-body">{_esc(body)}</div>
            {hint_html}
        </div>
        """),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Dashboard components
# ---------------------------------------------------------------------------
def kpi_card(label: str, value: object, note: str) -> None:
    """Render one primary KPI inside a bordered container.

    ``st.metric`` is used deliberately so the value remains a native Streamlit
    metric (and is available to AppTest), while the surrounding container and
    typography provide the visual card treatment.
    """
    key_slug = "".join(
        character if character.isalnum() else "-"
        for character in label.lower()
    ).strip("-")
    with st.container(border=True, key=f"itc-card-{key_slug}"):
        st.metric(label, value)
        st.caption(note)


def secondary_stats(items: Sequence[tuple[str, object, str]]) -> None:
    """Render a responsive strip of secondary metrics.

    ``items`` is a sequence of ``(label, value, note)`` tuples.
    """
    if not items:
        return
    cells = "".join(
        f"""
        <div class="itc-stat">
            <div class="itc-stat-label">{_esc(label)}</div>
            <div class="itc-stat-value">{_esc(value)}</div>
            <div class="itc-stat-note">{_esc(note)}</div>
        </div>
        """
        for label, value, note in items
    )
    # Column count is intentionally left to CSS (``auto-fit``) so the strip
    # reflows at tablet and phone widths instead of staying five-across.
    st.markdown(
        _markup(f'<div class="itc-stat-strip">{cells}</div>'),
        unsafe_allow_html=True,
    )


def status_breakdown(
    rows: Iterable[tuple[str, int, str]],
) -> None:
    """Render a compact horizontal-bar breakdown.

    ``rows`` is an iterable of ``(label, count, tone)`` where tone is one of
    ``positive``, ``warning``, ``error``, ``critical``, or ``neutral``.
    """
    prepared = [(label, int(count), tone) for label, count, tone in rows]
    maximum = max((count for _, count, _ in prepared), default=0)
    blocks: list[str] = []
    for label, count, tone in prepared:
        width = (count / maximum * 100) if maximum > 0 else 0.0
        zero_class = " is-zero" if count == 0 else ""
        blocks.append(
            f"""
            <div class="itc-bar-row{zero_class}">
                <div class="itc-bar-top">
                    <span class="itc-bar-label">{_esc(label)}</span>
                    <span class="itc-bar-count">{count}</span>
                </div>
                <div class="itc-bar-track" aria-hidden="true">
                    <span class="itc-bar-fill tone-{_esc(tone)}"
                          style="width:{width:.1f}%"></span>
                </div>
            </div>
            """
        )
    st.markdown(
        _markup(f'<div class="itc-bars">{"".join(blocks)}</div>'),
        unsafe_allow_html=True,
    )


def callout(
    title: str,
    value: str,
    note: str,
    *,
    tone: str = "warning",
) -> None:
    """Render a small callout with an optional semantic left border."""
    extra = "" if tone == "warning" else " is-neutral"
    st.markdown(_markup(
        f"""
        <div class="itc-callout{extra}">
            <div class="itc-callout-title">{_esc(title)}</div>
            <div class="itc-callout-value">{_esc(value)}</div>
            <div class="itc-callout-note">{_esc(note)}</div>
        </div>
        """),
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Review queue components
# ---------------------------------------------------------------------------
def chip(label: str, tone: str = "neutral") -> str:
    """Return a static status chip as HTML."""
    css = _TONE_CLASS.get(tone, "is-neutral")
    return f'<span class="itc-chip {css}">{_esc(label)}</span>'


def review_header(record_id: str, chips: Sequence[tuple[str, str]]) -> None:
    """Render the review record identity and its status chips."""
    chips_html = "".join(chip(label, tone) for label, tone in chips)
    st.markdown(_markup(
        f"""
        <div class="itc-review-head">
            <div>
                <div class="itc-eyebrow">Review record</div>
                <div class="itc-record-id">{_esc(record_id)}</div>
            </div>
            <div class="itc-chip-row">{chips_html}</div>
        </div>
        """),
        unsafe_allow_html=True,
    )


def comparison_table(
    title: str,
    rows: Sequence[tuple[str, str, bool]],
) -> None:
    """Render an aligned field table for one side of a comparison.

    ``rows`` is ``(field, display_value, differs)``. Differences are marked in
    text as well as color so the meaning does not depend on color alone.
    """
    body_parts: list[str] = []
    for field, value, differs in rows:
        marker = '<span class="itc-diff-flag">differs</span>' if differs else ""
        row_class = "is-diff" if differs else ""
        body_parts.append(
            f'<tr class="{row_class}">'
            f"<th>{_esc(field)}</th>"
            f"<td>{_esc(value)}{marker}</td>"
            "</tr>"
        )
    body = "".join(body_parts)
    st.markdown(_markup(
        f"""
        <div class="itc-compare">
            <div class="itc-compare-title">{_esc(title)}</div>
            <table class="itc-fields"><tbody>{body}</tbody></table>
        </div>
        """),
        unsafe_allow_html=True,
    )


def key_value_table(
    title: str,
    rows: Sequence[tuple[str, str]],
    *,
    plain: bool = False,
) -> None:
    """Render a compact label/value table used for decision support."""
    body = "".join(
        f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"
        for label, value in rows
    )
    extra_class = " is-plain" if plain else ""
    st.markdown(_markup(
        f"""
        <div class="itc-compare{extra_class}">
            <div class="itc-compare-title">{_esc(title)}</div>
            <table class="itc-kv"><tbody>{body}</tbody></table>
        </div>
        """),
        unsafe_allow_html=True,
    )


def footer(version: str) -> None:
    """Render the discreet application footer."""
    st.markdown(_markup(
        f"""
        <div class="itc-footer">
            ITC Sentinel v{_esc(version)} · Synthetic-data MVP ·
            Decision support only — not a GST filing system. Eligibility remains
            uncertain pending Chartered Accountant validation of tax rules.
        </div>
        """),
        unsafe_allow_html=True,
    )

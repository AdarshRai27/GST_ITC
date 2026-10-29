"""Warm editorial theme for ITC Sentinel.

Design direction: understated financial operations software. Neutral parchment
surfaces carry most of the interface; sage marks primary actions and confirmed
states, terracotta marks discrepancies, and ochre marks attention/pending.

The palette is also mirrored in ``.streamlit/config.toml`` so Streamlit's own
widgets inherit the same foundation. CSS here handles typography, spacing, and
the few custom presentation blocks that Streamlit theming cannot express.
"""

from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
COLORS: dict[str, str] = {
    "canvas": "#F5F1E8",
    "surface": "#FFFCF6",
    "surface_secondary": "#ECE4D7",
    "surface_raised": "#F8F4EB",
    "border": "#DCD2C2",
    "border_strong": "#CFC3B0",
    "text": "#332B25",
    "text_secondary": "#74695E",
    "sage": "#78866B",
    "sage_deep": "#59694F",
    "terracotta": "#B96547",
    "ochre": "#D5B65D",
    "green": "#56745A",
    "red": "#A34F42",
}

FONT_SANS = (
    '"Inter", "Segoe UI", "Helvetica Neue", Arial, "Noto Sans", sans-serif'
)
FONT_SERIF = (
    'Georgia, "Iowan Old Style", "Palatino Linotype", "Times New Roman", serif'
)

_CSS = """
<style>
:root {
    --itc-canvas: #F5F1E8;
    --itc-surface: #FFFCF6;
    --itc-surface-2: #ECE4D7;
    --itc-surface-raised: #F8F4EB;
    --itc-border: #DCD2C2;
    --itc-border-strong: #CFC3B0;
    --itc-text: #332B25;
    --itc-text-2: #74695E;
    --itc-sage: #78866B;
    --itc-sage-deep: #59694F;
    --itc-terracotta: #B96547;
    --itc-ochre: #D5B65D;
    --itc-green: #56745A;
    --itc-red: #A34F42;
    --itc-radius: 12px;
    --itc-shadow: 0 1px 2px rgba(51, 43, 37, 0.05);
}

/* ---------- Canvas and typography ---------- */
.stApp,
[data-testid="stAppViewContainer"] {
    background: var(--itc-canvas);
    color: var(--itc-text);
    font-family: __FONT_SANS__;
}

[data-testid="stHeader"] {
    background: transparent;
}

[data-testid="stMainBlockContainer"],
.block-container {
    max-width: 1280px;
    padding-top: 2.2rem;
    padding-bottom: 3.2rem;
}

.stApp h1,
.stApp h2,
.stApp h3,
.stApp h4,
.stApp h5 {
    color: var(--itc-text);
    letter-spacing: -0.01em;
}

.stApp p,
.stApp li,
.stApp label,
.stApp span {
    color: var(--itc-text);
}

[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    color: var(--itc-text-2);
    font-size: 0.8rem;
}

a {
    color: var(--itc-sage-deep);
}

.stApp :focus-visible {
    outline: 2px solid var(--itc-sage-deep);
    outline-offset: 2px;
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background: var(--itc-surface-2);
    border-right: 1px solid var(--itc-border);
}

[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 1.1rem;
}

[data-testid="stSidebar"] .block-container {
    padding-top: 1.1rem;
    padding-bottom: 2rem;
}

[data-testid="stSidebar"] hr {
    border-color: var(--itc-border);
}

/* ---------- Navigation ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.2rem;
    border-bottom: 1px solid var(--itc-border);
    margin-bottom: 1.4rem;
}

.stTabs [data-baseweb="tab"] {
    height: auto;
    padding: 0.62rem 0.9rem;
    color: var(--itc-text-2);
    font-size: 0.88rem;
    font-weight: 600;
    border-radius: 9px 9px 0 0;
    border: 1px solid transparent;
    border-bottom: 0;
}

.stTabs [data-baseweb="tab"]:hover {
    color: var(--itc-text);
    background: rgba(255, 252, 246, 0.55);
}

.stTabs [aria-selected="true"] {
    color: var(--itc-text);
    background: var(--itc-surface);
    border-color: var(--itc-border);
}

.stTabs [data-baseweb="tab-highlight"] {
    background: var(--itc-sage);
    height: 2px;
}

.stTabs [data-baseweb="tab-border"] {
    background: var(--itc-border);
}

/* ---------- Buttons ---------- */
.stButton > button,
.stDownloadButton > button,
[data-testid="stBaseButton-secondaryFormSubmit"] {
    border-radius: 8px;
    border: 1px solid var(--itc-border-strong);
    background: var(--itc-surface);
    color: var(--itc-text);
    font-weight: 600;
    font-size: 0.88rem;
    padding: 0.5rem 0.95rem;
    box-shadow: none;
    transition: background 120ms ease, border-color 120ms ease,
        color 120ms ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
    border-color: var(--itc-sage);
    color: var(--itc-sage-deep);
    background: #F7F4EC;
}

.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {
    background: var(--itc-sage);
    border-color: var(--itc-sage);
    color: #FFFFFF;
}

.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover {
    background: var(--itc-sage-deep);
    border-color: var(--itc-sage-deep);
    color: #FFFFFF;
}

.stButton > button[kind="primary"] p,
[data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primaryFormSubmit"] p {
    color: #FFFFFF;
}

/* ---------- Inputs ---------- */
[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="select"] > div {
    background-color: var(--itc-surface) !important;
    border-color: var(--itc-border) !important;
    border-radius: 8px !important;
}

[data-baseweb="input"]:focus-within,
[data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {
    border-color: var(--itc-sage) !important;
}

[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="textarea"],
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background-color: var(--itc-surface) !important;
}

/* ---------- Containers, forms, expanders ---------- */
[data-testid="stVerticalBlock"][class*="st-key-itc-card"] {
    background: var(--itc-surface);
    border: 1px solid var(--itc-border);
    border-radius: var(--itc-radius);
    box-shadow: var(--itc-shadow);
    padding: 1rem 1.1rem;
}

[data-testid="stForm"] {
    background: var(--itc-surface);
    border: 1px solid var(--itc-border);
    border-radius: var(--itc-radius);
    padding: 1rem 1.1rem 0.35rem;
}

[data-testid="stExpander"] {
    background: var(--itc-surface);
    border: 1px solid var(--itc-border);
    border-radius: 10px;
}

[data-testid="stExpander"] summary {
    font-weight: 600;
}

/* ---------- Metrics ---------- */
[data-testid="stMetric"] {
    background: transparent;
    border: 0;
    padding: 0;
}

[data-testid="stMetricLabel"],
[data-testid="stMetricLabel"] p {
    color: var(--itc-text-2);
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.01em;
}

[data-testid="stMetricValue"] {
    color: var(--itc-text);
    font-size: 1.95rem;
    font-weight: 600;
    line-height: 1.15;
    font-variant-numeric: tabular-nums;
}

/* ---------- Tables and progress ---------- */
[data-testid="stDataFrame"] {
    border: 1px solid var(--itc-border);
    border-radius: 10px;
    overflow: hidden;
}

[data-testid="stProgressBarTrack"] {
    background: var(--itc-surface-2) !important;
}

[data-testid="stProgressBarTrack"] > div {
    background: var(--itc-sage) !important;
}

[data-testid="stAlert"] {
    border-radius: 10px;
    border: 1px solid var(--itc-border);
}

/* Keep success feedback inside the warm sage palette rather than the
   default mint alert surface. Streamlit paints the surface on
   ``stAlertContainer``; the content testid confirms the alert kind. */
[data-testid="stAlert"] {
    overflow: hidden;
}

[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
    background: #edf1e7;
    color: var(--itc-sage-deep);
}

[data-testid="stAlertContentSuccess"] {
    color: var(--itc-sage-deep);
}

code {
    background: var(--itc-surface-2);
    color: var(--itc-text);
    border-radius: 4px;
    padding: 0.08rem 0.3rem;
}

/* ---------- Brand block ---------- */
.itc-brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.15rem 0 1rem;
    border-bottom: 1px solid var(--itc-border);
    margin-bottom: 1.05rem;
}

.itc-brand-mark {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    background: var(--itc-text);
    color: var(--itc-canvas);
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
}

.itc-brand-name {
    font-family: __FONT_SERIF__;
    font-size: 1.16rem;
    font-weight: 600;
    line-height: 1.1;
    color: var(--itc-text);
}

.itc-brand-desc {
    margin-top: 0.18rem;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.13em;
    color: var(--itc-text-2);
}

.itc-side-label {
    margin: 0.3rem 0 0.45rem;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--itc-text-2);
}

.itc-side-note {
    margin-top: 0.35rem;
    font-size: 0.76rem;
    line-height: 1.45;
    color: var(--itc-text-2);
}

.itc-side-footer {
    margin-top: 1.3rem;
    padding-top: 0.85rem;
    border-top: 1px solid var(--itc-border);
    font-size: 0.7rem;
    line-height: 1.45;
    color: var(--itc-text-2);
}

/* ---------- Page header ---------- */
.itc-header {
    padding: 0.1rem 0 0.85rem;
}

.itc-header-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 2rem;
}

.itc-eyebrow {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--itc-text-2);
}

.itc-header .itc-title {
    margin: 0.22rem 0 0.32rem;
    font-family: __FONT_SERIF__;
    font-size: 2.1rem;
    line-height: 1.15;
    font-weight: 600;
    letter-spacing: -0.015em;
    color: var(--itc-text);
}

.itc-sub {
    max-width: 64ch;
    margin: 0;
    font-size: 0.93rem;
    line-height: 1.5;
    color: var(--itc-text-2);
}

.itc-header-meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.4rem;
    padding-top: 0.35rem;
    flex: 0 0 auto;
}

.itc-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.26rem 0.6rem;
    border: 1px solid var(--itc-border);
    border-radius: 999px;
    background: var(--itc-surface);
    color: var(--itc-text-2);
    font-size: 0.74rem;
    font-weight: 600;
    white-space: nowrap;
}

.itc-pill .itc-dot {
    width: 0.44rem;
    height: 0.44rem;
    border-radius: 50%;
    background: var(--itc-sage);
}

.itc-pill.is-custom .itc-dot {
    background: var(--itc-terracotta);
}

.itc-pill.is-neutral .itc-dot {
    background: #B5A998;
}

.itc-runid {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    color: var(--itc-text-2);
    font-variant-numeric: tabular-nums;
}

.itc-rule {
    height: 1px;
    background: var(--itc-border);
    margin: 0.15rem 0 1.35rem;
}

/* ---------- Section headings ---------- */
.itc-section-head {
    margin: 0.1rem 0 0.85rem;
}

.itc-section-title {
    margin: 0.16rem 0 0.2rem;
    font-size: 1.18rem;
    line-height: 1.3;
    font-weight: 650;
    color: var(--itc-text);
}

.itc-section-head .itc-section-title {
    font-size: 1.18rem;
    line-height: 1.3;
    font-weight: 650;
}

.itc-section-desc {
    margin: 0;
    max-width: 78ch;
    font-size: 0.86rem;
    line-height: 1.5;
    color: var(--itc-text-2);
}

.itc-section-divider {
    height: 1px;
    background: var(--itc-border);
    margin: 2rem 0 1.5rem;
}

/* ---------- Welcome / first load ---------- */
.itc-welcome {
    display: flex;
    align-items: flex-start;
    gap: 1.4rem;
    padding: 1.8rem 2rem;
    margin-bottom: 1.2rem;
    background: var(--itc-surface);
    border: 1px solid var(--itc-border);
    border-radius: 14px;
    box-shadow: var(--itc-shadow);
}

.itc-welcome-mark {
    flex: 0 0 auto;
    width: 54px;
    height: 54px;
    border-radius: 12px;
    background: var(--itc-surface-2);
    color: var(--itc-sage-deep);
    display: flex;
    align-items: center;
    justify-content: center;
}

.itc-welcome h2 {
    margin: 0.18rem 0 0.35rem;
    font-family: __FONT_SERIF__;
    font-size: 1.62rem;
    line-height: 1.25;
    font-weight: 600;
    letter-spacing: -0.01em;
}

.itc-welcome p {
    margin: 0;
    max-width: 72ch;
    font-size: 0.92rem;
    line-height: 1.55;
    color: var(--itc-text-2);
}

.itc-steps {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1rem;
    margin: 0 0 1.15rem;
}

.itc-step {
    padding: 0.9rem 0 0;
    border-top: 2px solid var(--itc-sage);
}

.itc-step-num {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    color: var(--itc-sage-deep);
}

.itc-step h3 {
    margin: 0.3rem 0 0.25rem;
    font-size: 0.98rem;
    font-weight: 650;
}

.itc-step p {
    margin: 0;
    font-size: 0.84rem;
    line-height: 1.5;
    color: var(--itc-text-2);
}

/* ---------- Secondary stat strip ---------- */
.itc-stat-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 1px;
    margin: 0.95rem 0 1.35rem;
    background: var(--itc-border);
    border: 1px solid var(--itc-border);
    border-radius: var(--itc-radius);
    overflow: hidden;
}

.itc-stat {
    padding: 0.8rem 0.95rem;
    background: var(--itc-surface);
    min-width: 0;
}

.itc-stat-label {
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--itc-text-2);
}

.itc-stat-value {
    margin-top: 0.18rem;
    font-size: 1.02rem;
    font-weight: 650;
    color: var(--itc-text);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.itc-stat-note {
    margin-top: 0.08rem;
    font-size: 0.68rem;
    line-height: 1.35;
    color: var(--itc-text-2);
}

/* ---------- Status breakdown ---------- */
.itc-bars {
    display: flex;
    flex-direction: column;
    gap: 0.68rem;
}

.itc-bar-top {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.26rem;
    font-size: 0.83rem;
}

.itc-bar-label {
    color: var(--itc-text);
}

.itc-bar-count {
    font-weight: 650;
    color: var(--itc-text);
    font-variant-numeric: tabular-nums;
}

.itc-bar-track {
    height: 6px;
    background: var(--itc-surface-2);
    border-radius: 999px;
    overflow: hidden;
}

.itc-bar-fill {
    display: block;
    height: 100%;
    border-radius: 999px;
    background: var(--itc-sage);
}

.itc-bar-fill.tone-positive {
    background: var(--itc-green);
}

.itc-bar-fill.tone-warning {
    background: var(--itc-ochre);
}

.itc-bar-fill.tone-error {
    background: var(--itc-terracotta);
}

.itc-bar-fill.tone-critical {
    background: var(--itc-red);
}

.itc-bar-fill.tone-neutral {
    background: #A99D8C;
}

.itc-bar-row.is-zero .itc-bar-label,
.itc-bar-row.is-zero .itc-bar-count {
    color: var(--itc-text-2);
}

.itc-bar-row.is-zero .itc-bar-track {
    background: #F0E9DD;
}

/* ---------- Callouts ---------- */
.itc-callout {
    padding: 1rem 1.15rem;
    background: var(--itc-surface);
    border: 1px solid var(--itc-border);
    border-left: 3px solid var(--itc-ochre);
    border-radius: 10px;
}

.itc-callout.is-neutral {
    border-left-color: var(--itc-sage);
}

.itc-callout-title {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    color: var(--itc-text-2);
}

.itc-callout-value {
    margin: 0.3rem 0 0.25rem;
    font-size: 1.42rem;
    font-weight: 650;
    color: var(--itc-text);
    font-variant-numeric: tabular-nums;
}

.itc-callout-note {
    font-size: 0.78rem;
    line-height: 1.45;
    color: var(--itc-text-2);
}

ul.itc-list {
    margin: 0.45rem 0 0;
    padding-left: 1.05rem;
}

ul.itc-list li {
    margin: 0.28rem 0;
    font-size: 0.82rem;
    line-height: 1.45;
    color: var(--itc-text-2);
}

/* ---------- Review queue ---------- */
.itc-review-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1.2rem;
    margin: 0.15rem 0 0.55rem;
}

.itc-record-id {
    margin-top: 0.15rem;
    font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace;
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--itc-text);
    overflow-wrap: anywhere;
}

.itc-chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.38rem;
    justify-content: flex-end;
}

.itc-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.55rem;
    border: 1px solid var(--itc-border);
    border-radius: 999px;
    background: var(--itc-surface);
    color: var(--itc-text-2);
    font-size: 0.71rem;
    font-weight: 600;
    white-space: nowrap;
}

.itc-chip.is-positive {
    background: #EEF2EA;
    border-color: #CBD5C3;
    color: #3F5138;
}

.itc-chip.is-warning {
    background: #F8F1DE;
    border-color: #E6D3A2;
    color: #6B5420;
}

.itc-chip.is-error {
    background: #F7E9E4;
    border-color: #E3C3B7;
    color: #7C3B2C;
}

.itc-chip.is-neutral {
    background: var(--itc-surface-2);
    color: var(--itc-text-2);
}

.itc-compare {
    height: 100%;
    padding: 0.9rem 1rem;
    background: var(--itc-surface);
    border: 1px solid var(--itc-border);
    border-radius: 10px;
}

.itc-compare.is-plain {
    height: auto;
    padding: 0;
    background: transparent;
    border: 0;
    border-radius: 0;
}

.itc-compare-title {
    margin-bottom: 0.45rem;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--itc-text-2);
}

table.itc-fields,
table.itc-kv {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}

table.itc-fields th,
table.itc-kv th {
    width: 44%;
    padding: 0.32rem 0.4rem 0.32rem 0;
    text-align: left;
    vertical-align: top;
    font-weight: 500;
    color: var(--itc-text-2);
}

table.itc-fields td,
table.itc-kv td {
    padding: 0.32rem 0;
    text-align: right;
    vertical-align: top;
    color: var(--itc-text);
    font-variant-numeric: tabular-nums;
    overflow-wrap: anywhere;
}

table.itc-fields tr + tr,
table.itc-kv tr + tr {
    border-top: 1px solid #EEE7DB;
}

table.itc-fields tr.is-diff td {
    color: var(--itc-terracotta);
    font-weight: 600;
}

.itc-diff-flag {
    margin-left: 0.32rem;
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--itc-terracotta);
}

.itc-kv-note {
    margin-top: 0.5rem;
    font-size: 0.75rem;
    line-height: 1.45;
    color: var(--itc-text-2);
}

/* ---------- Empty states ---------- */
.itc-empty {
    padding: 1.5rem 1.4rem;
    background: rgba(255, 252, 246, 0.55);
    border: 1px dashed var(--itc-border-strong);
    border-radius: var(--itc-radius);
}

.itc-empty-title {
    margin-bottom: 0.25rem;
    font-size: 0.95rem;
    font-weight: 650;
    color: var(--itc-text);
}

.itc-empty-body {
    max-width: 74ch;
    font-size: 0.86rem;
    line-height: 1.5;
    color: var(--itc-text-2);
}

.itc-empty-hint {
    margin-top: 0.45rem;
    font-size: 0.78rem;
    line-height: 1.45;
    color: var(--itc-text-2);
}

/* ---------- Footer ---------- */
.itc-footer {
    margin-top: 2.2rem;
    padding-top: 0.9rem;
    border-top: 1px solid var(--itc-border);
    font-size: 0.72rem;
    line-height: 1.5;
    color: var(--itc-text-2);
}

/* ---------- Responsive ---------- */
/* Streamlit columns do not wrap by default. Keyed containers let us target
   only the rows that should reflow, without touching unrelated layouts. */
@media (max-width: 1100px) {
    .st-key-itc-kpi-row [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
    }

    .st-key-itc-kpi-row [data-testid="stColumn"] {
        flex: 1 1 calc(50% - 0.5rem);
        min-width: 0;
        max-width: calc(50% - 0.5rem);
    }
}

@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"],
    .block-container {
        padding-top: 1.3rem;
    }

    .itc-header-top {
        flex-direction: column;
        gap: 0.9rem;
    }

    .itc-header-meta {
        align-items: flex-start;
        padding-top: 0;
    }

    .itc-welcome {
        flex-direction: column;
        padding: 1.35rem 1.25rem;
    }

    .itc-steps {
        grid-template-columns: 1fr;
        gap: 0.8rem;
    }

    .itc-review-head {
        flex-direction: column;
        gap: 0.6rem;
    }

    .itc-chip-row {
        justify-content: flex-start;
    }

    .st-key-itc-overview-row [data-testid="stHorizontalBlock"],
    .st-key-itc-exposure-row [data-testid="stHorizontalBlock"],
    .st-key-itc-compare-row [data-testid="stHorizontalBlock"],
    .st-key-itc-detail-row [data-testid="stHorizontalBlock"],
    .st-key-itc-form-row [data-testid="stHorizontalBlock"],
    .st-key-itc-export-row [data-testid="stHorizontalBlock"],
    .st-key-itc-table-filters [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap;
    }

    .st-key-itc-overview-row [data-testid="stColumn"],
    .st-key-itc-exposure-row [data-testid="stColumn"],
    .st-key-itc-compare-row [data-testid="stColumn"],
    .st-key-itc-detail-row [data-testid="stColumn"],
    .st-key-itc-form-row [data-testid="stColumn"],
    .st-key-itc-export-row [data-testid="stColumn"],
    .st-key-itc-table-filters [data-testid="stColumn"] {
        flex: 1 1 100%;
        min-width: 0;
        max-width: 100%;
    }
}

@media (max-width: 640px) {
    [data-testid="stMainBlockContainer"],
    .block-container {
        /* Clear Streamlit's collapsed-sidebar control, which otherwise
           overlaps the header eyebrow on phone-width screens. */
        padding-top: 2.5rem;
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .st-key-itc-kpi-row [data-testid="stColumn"] {
        flex-basis: 100%;
        max-width: 100%;
    }

    .itc-header .itc-title {
        font-size: 1.75rem;
    }

    .itc-header-top {
        gap: 0.75rem;
    }

    .itc-stat-strip {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    /* Native tabs scroll horizontally on phones; tighten them so more of
       each label is visible before the overflow control. */
    [data-testid="stTabs"] button[role="tab"] {
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        font-size: 0.78rem;
    }
}
</style>
"""

_CSS = _CSS.replace("__FONT_SANS__", FONT_SANS).replace(
    "__FONT_SERIF__", FONT_SERIF
)


def apply_theme() -> None:
    """Inject the application stylesheet.

    Call once after ``st.set_page_config``. The CSS is static and contains no
    uploaded content, so ``unsafe_allow_html`` is safe here.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

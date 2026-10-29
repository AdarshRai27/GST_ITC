"""Presentation layer for the ITC Sentinel Streamlit app.

The UI package deliberately contains no reconciliation logic. It only owns
design tokens, shared markup, and formatting helpers so that ``app.py`` can
stay focused on workflow and state.
"""

from .theme import COLORS, apply_theme

__all__ = ["COLORS", "apply_theme"]

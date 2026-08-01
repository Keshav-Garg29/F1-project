"""Design tokens for the Streamlit frontend.

Centralised so colour, typography, and spacing changes don't have to
hunt through every component. Stub — only a token map is defined.
"""

from __future__ import annotations

import streamlit as st

TOKENS: dict = {
    "color": {
        "bg": "#0E0E10",
        "fg": "#F5F5F7",
        "accent": "#E10600",
        "muted": "#6B6B70",
    },
    "font": {
        "family": "Inter, system-ui, sans-serif",
        "size_body": 16,
    },
}


def apply_theme() -> None:
    """Inject the token map into the Streamlit page. Stub."""
    raise NotImplementedError("apply_theme is a stub")

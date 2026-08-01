"""Reusable Streamlit components for the prediction views.

Two chart components today:

- ``render_qualifying_chart`` — Model A's predicted grid order
- ``render_result_chart`` — Model B's predicted finishing order

Each is a thin wrapper around the model output so the page can be
rearranged without touching prediction logic.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render_qualifying_chart(grid_predictions: pd.DataFrame) -> None:
    """Render Model A's predicted grid order. Stub."""
    raise NotImplementedError("render_qualifying_chart is a stub")


def render_result_chart(finish_predictions: pd.DataFrame) -> None:
    """Render Model B's predicted finishing order. Stub."""
    raise NotImplementedError("render_result_chart is a stub")

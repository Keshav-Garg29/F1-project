"""Backtesting harness — compare predictions against actual outcomes.

Both models call into this module for a fair, side-by-side metric
report: the model's own score next to a naive baseline (e.g. predict
the field's mean grid position, predict P1 for everyone, etc.).

The baseline choice per model is documented inline because it's the
most common place for "looks-good-but-isn't" evaluation in sports
forecasting.
"""

from __future__ import annotations

import pandas as pd


def evaluate_model_a(predictions: pd.Series, actuals: pd.Series) -> dict:
    """Score Model A (grid position) against actuals. Stub."""
    raise NotImplementedError("evaluate_model_a is a stub")


def evaluate_model_b(predictions: pd.Series, actuals: pd.Series) -> dict:
    """Score Model B (finish position) against actuals. Stub."""
    raise NotImplementedError("evaluate_model_b is a stub")

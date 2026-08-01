"""Streamlit entry point — chain Model A → Model B on a user scenario.

Run with ``streamlit run src/app/streamlit_app.py`` (see CLAUDE.md
"Commands"). The scenario widget collects season/round/weather/driver
lineup; ``render_scenario()`` is the single orchestration function
that the rest of the page delegates to.

Stub today.
"""

from __future__ import annotations

import streamlit as st

from src.app.components import render_qualifying_chart, render_result_chart
from src.app.styles import apply_theme
from src.models.train_qualifying_model import predict_grid_position
from src.models.train_race_result_model import predict_finish_position


def render_scenario(scenario: dict) -> None:
    """Chain Model A and Model B on a single scenario dict. Stub."""
    raise NotImplementedError("render_scenario is a stub")


def main() -> None:
    st.set_page_config(page_title="Apex Analytics", layout="wide")
    apply_theme()
    st.title("Apex Analytics — F1 Race Predictor")
    st.info("Stub: scenario chain not yet implemented.")


if __name__ == "__main__":
    main()

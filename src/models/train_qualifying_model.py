"""Model A — predict qualifying / grid position.

Critical constraint (CLAUDE.md "Warnings"): the real ``grid_position``
is the target — it must NEVER appear as a feature. The training
script asserts this at load time and refuses to fit if it does.

Exposes ``predict_grid_position(features: pd.DataFrame) -> np.ndarray``
so the Streamlit app can chain it into Model B.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config.settings import ARTIFACTS_DIR

# Public artefacts written by ``main()`` and consumed downstream.
MODEL_A_ARTIFACT: Path = ARTIFACTS_DIR / "model_a_grid_position.txt"
FEATURE_COLUMNS_ARTIFACT: Path = ARTIFACTS_DIR / "model_a_features.json"


def predict_grid_position(features: pd.DataFrame) -> pd.Series:
    """Score a feature frame with the trained Model A. Stub.

    Args:
        features: One row per (driver, race) with the columns
            documented in ``build_qualifying_features``.

    Returns:
        Predicted grid position, integer-like, one per row.
    """
    raise NotImplementedError("predict_grid_position is a stub")


def main() -> None:
    """Train Model A on the warehouse and write its artefact. Stub."""
    raise NotImplementedError("train_qualifying_model.main is a stub")


if __name__ == "__main__":
    main()

"""Model B — predict finishing position, chained on Model A.

Model B's training and inference share one code path. The difference
between "training" and "inference" is just the source of the
``grid_position`` column:

- Training: real ``grid_position`` from ``qualifying_results``
- Inference: predicted ``grid_position`` from Model A

The frontend hands Model B a precomputed grid (Model A's output), so
this module's public surface is ``predict_finish_position(features)``
where ``features`` already contains the grid column.

Stub today.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config.settings import ARTIFACTS_DIR

MODEL_B_ARTIFACT: Path = ARTIFACTS_DIR / "model_b_finish_position.txt"
FEATURE_COLUMNS_ARTIFACT: Path = ARTIFACTS_DIR / "model_b_features.json"


def predict_finish_position(features: pd.DataFrame) -> pd.Series:
    """Score a feature frame with the trained Model B. Stub.

    ``features`` must include a ``grid_position`` column — real during
    backtesting, Model A's prediction during scenario inference.
    """
    raise NotImplementedError("predict_finish_position is a stub")


def main() -> None:
    """Train Model B on the warehouse and write its artefact. Stub."""
    raise NotImplementedError("train_race_result_model.main is a stub")


if __name__ == "__main__":
    main()

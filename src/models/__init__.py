"""LightGBM model training and evaluation.

- ``train_qualifying_model`` — Model A (grid position)
- ``train_race_result_model`` — Model B (finish position), chained on
  Model A
- ``evaluate`` — backtesting harness shared by both models

Every training script reports a naive baseline alongside its own
metric (CLAUDE.md "Code style"). Model B's training/inference path
is shared: the only difference is whether ``grid_position`` comes
from the warehouse (training) or from Model A (inference).
"""

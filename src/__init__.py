"""Apex Analytics — F1 race result prediction.

Chains two LightGBM models: Model A predicts qualifying/grid position,
Model B predicts finishing position from Model A's output. Frontend is a
Streamlit app that runs a hypothetical scenario end to end.
"""

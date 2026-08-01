"""Streamlit frontend — scenario in, predicted result out.

The app is built around chaining: a scenario input flows into Model A,
whose output (predicted grid) feeds into Model B, whose output is the
predicted finishing order. New models should expose a ``predict_*()``
function so this module can wire them in without a rewrite.
"""

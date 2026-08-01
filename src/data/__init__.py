"""Data ingestion layer for the F1 prediction warehouse.

Submodules:

- ``fastf1_ingest`` — race and qualifying data from FastF1
- ``weather_ingest`` — historical and hypothetical weather from Open-Meteo
- ``warehouse`` — DuckDB connection and schema bootstrap
- ``run_pipeline`` — CLI entry point that orchestrates a full ingest

All ingest functions are stubbed today (see CLAUDE.md "Implemented vs
stub"); they're responsible for landing data into the local DuckDB
warehouse defined in ``warehouse.py`` and mirrored in ``sql/schema.sql``.
"""

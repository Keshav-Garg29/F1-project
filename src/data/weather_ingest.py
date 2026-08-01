"""Weather data ingestion via Open-Meteo.

The same module handles two use cases:

1. Backfilling historical weather for every round in the warehouse
   (so race features can include weather without an extra fetch at
   training time)
2. Pulling a hypothetical weather forecast for a scenario in the
   Streamlit app

Both are stubs today; the schema they target lives in
``src/data/warehouse.py`` under the ``weather`` table.
"""

from __future__ import annotations


def fetch_historical(season: int, round_: int) -> int:
    """Backfill historical weather for one round. Stub."""
    raise NotImplementedError("fetch_historical is a stub")


def fetch_hypothetical(circuit_lat: float, circuit_lon: float, race_date: str) -> dict:
    """Pull a forecast for a hypothetical scenario. Stub."""
    raise NotImplementedError("fetch_hypothetical is a stub")

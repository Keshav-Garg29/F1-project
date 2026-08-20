"""Weather data ingestion via Open-Meteo.

The same module handles two use cases:

1. Backfilling historical weather for every round in the warehouse
   (so race features can include weather without an extra fetch at
   training time) — ``fetch_historical``.
2. Pulling a hypothetical weather forecast for a scenario in the
   Streamlit app — ``fetch_hypothetical``.

Both target the same Open-Meteo Archive endpoint and share the same
variable mapping (``_DAILY_FIELDS``).

Why ``track_temp_c`` is always written as NULL: the Open-Meteo Archive
API exposes no track/road-surface temperature variable. Proxying with
``temperature_2m_max`` (ambient air) is materially misleading and would
corrupt downstream models. A future slice could add a separate track-
surface data source.

Coordinates: ``fetch_historical`` resolves lat/lon via the ``CIRCUIT_COORDS``
lookup below. This dict is hand-maintained for the 2022–2026 F1 calendar
and is drift-prone — a future spec should replace it with lat/lon read
from FastF1 session metadata (the preferred option in
``.claude/specs/data-ingestion.md``).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import requests
from requests.exceptions import RequestException

from src.data.warehouse import connect

# --- Open-Meteo Archive configuration --------------------------------------

_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
# Daily variables: air_temp_c <- temperature_2m_max (°C);
#                  humidity   <- relative_humidity_2m_mean (%);
#                  rainfall_mm<- precipitation_sum (mm);
#                  wind_kph   <- wind_speed_10m_max (km/h — no conversion needed).
_DAILY_FIELDS = (
    "temperature_2m_max,"
    "relative_humidity_2m_mean,"
    "precipitation_sum,"
    "wind_speed_10m_max"
)
_TIMEOUT_SECONDS = 15


# Reused session for connection pooling; tests can monkey-patch this module.
_HTTP = requests.Session()


# --- Circuit coordinate lookup ---------------------------------------------
# Drift-prone: hand-maintained for 2022–2026. A future slice should swap to
# reading coordinates from FastF1 session metadata instead.

# City string (matches FastF1 ``session.event.Location``) -> (lat, lon).
_BY_CITY: dict[str, tuple[float, float]] = {
    "Sakhir":         (26.0325, 50.5106),   # Bahrain
    "Jeddah":         (21.4858, 39.1925),   # Saudi Arabia
    "Melbourne":      (-37.8497, 144.9680), # Australia
    "Imola":          (44.3439, 11.7167),   # Emilia Romagna
    "Miami":          (25.9581, -80.2389),
    "Barcelona":      (41.5700, 2.2611),    # Spain
    "Monte Carlo":    (43.7347, 7.4206),    # Monaco (FastF1 may report 'Monaco' too)
    "Monaco":         (43.7347, 7.4206),
    "Baku":           (40.3725, 49.8533),   # Azerbaijan
    "Montréal":       (45.5048, -73.5228),  # Canada
    "Spielberg":      (47.2197, 14.7647),   # Austria
    "Silverstone":    (52.0786, -1.0169),   # UK
    "Budapest":       (47.5789, 19.2486),   # Hungary
    "Spa":            (50.4372, 5.9714),    # Belgium
    "Zandvoort":      (52.3888, 4.5407),    # Netherlands
    "Monza":          (45.6156, 9.2811),    # Italy
    "Singapore":      (1.2914, 103.8639),
    "Suzuka":         (34.8431, 136.5406),  # Japan
    "Austin":         (30.1328, -97.6411),  # USA (COTA)
    "Mexico City":    (19.4061, -99.0906),
    "São Paulo":      (-23.7036, -46.6997), # Brazil
    "Abu Dhabi":      (24.4672, 54.6031),   # UAE
    "Lusail":         (25.4900, 51.4500),   # Qatar
    "Las Vegas":      (36.1147, -115.1728),
    "Shanghai":       (31.3389, 121.2197),  # China
}

# (season, round) -> (lat, lon) for one-off overrides where the standard
# city mapping would be wrong (e.g. calendar reshuffles, venue name drift).
_BY_ROUND: dict[tuple[int, int], tuple[float, float]] = {}


def lookup_coords(season: int, round_: int, city: str | None) -> tuple[float, float] | None:
    """Resolve circuit coordinates; prefers ``(season, round)`` overrides,
    then falls back to the city dictionary. Returns ``None`` if neither hits.
    """
    key = (season, round_)
    if key in _BY_ROUND:
        return _BY_ROUND[key]
    if city and city in _BY_CITY:
        return _BY_CITY[city]
    return None


# --- Open-Meteo call --------------------------------------------------------


def _archive_query(lat: float, lon: float, day: date) -> dict:
    """Run a single Open-Meteo Archive call for ``day`` at ``lat, lon``."""
    params = {
        "latitude":  lat,
        "longitude": lon,
        "start_date": day.isoformat(),
        "end_date":   day.isoformat(),
        "daily":      _DAILY_FIELDS,
        "timezone":   "UTC",
    }
    resp = _HTTP.get(_ARCHIVE_URL, params=params, timeout=_TIMEOUT_SECONDS)
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(
            f"Open-Meteo error for ({lat},{lon},{day}): {payload.get('reason')!r}"
        )
    return payload


def _extract_day(payload: dict, day: date) -> tuple[float | None, float | None, float | None, float | None]:
    """Pull the four daily values for ``day`` out of an Open-Meteo response.

    Returns ``(air_temp_c, humidity, rainfall_mm, wind_kph)``. Any of them
    may be ``None`` if the upstream archive returned a null for that date.
    """
    daily = payload.get("daily") or {}
    days: list[str] = daily.get("time") or []
    try:
        idx = days.index(day.isoformat())
    except ValueError:
        return (None, None, None, None)

    def _at(field: str) -> float | None:
        arr = daily.get(field) or []
        if idx >= len(arr):
            return None
        v = arr[idx]
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f

    return (
        _at("temperature_2m_max"),
        _at("relative_humidity_2m_mean"),
        _at("precipitation_sum"),
        _at("wind_speed_10m_max"),
    )


# --- public functions ------------------------------------------------------


def fetch_historical(season: int, round_: int) -> int:
    """Backfill historical weather for one round.

    Reads the circuit and ``race_date`` from the ``races`` table (populated
    by ``ingest_race``), resolves coordinates via ``CIRCUIT_COORDS``, and
    upserts the response into the ``weather`` table.

    Returns ``1`` on success, ``0`` if the round is missing from ``races``
    or has no known coordinates.
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT circuit, race_date FROM races WHERE season = ? AND round = ?",
            [season, round_],
        ).fetchone()
        if row is None:
            return 0
        circuit, race_date = row
        coords = lookup_coords(season, round_, circuit)
        if coords is None:
            return 0
        lat, lon = coords
        payload = _archive_query(lat, lon, race_date)
        air_temp_c, humidity, rainfall_mm, wind_kph = _extract_day(payload, race_date)

        conn.execute(
            """
            INSERT INTO weather
                (season, round, air_temp_c, track_temp_c, humidity, rainfall_mm, wind_kph)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (season, round) DO UPDATE SET
                air_temp_c   = EXCLUDED.air_temp_c,
                track_temp_c = EXCLUDED.track_temp_c,
                humidity     = EXCLUDED.humidity,
                rainfall_mm  = EXCLUDED.rainfall_mm,
                wind_kph     = EXCLUDED.wind_kph
            """,
            [
                season,
                round_,
                air_temp_c,
                None,         # track_temp_c intentionally NULL
                humidity,
                rainfall_mm,
                wind_kph,
            ],
        )
        return 1
    finally:
        conn.close()


def fetch_hypothetical(circuit_lat: float, circuit_lon: float, race_date: str) -> dict:
    """Pull a forecast for a hypothetical scenario.

    Per the planning decision, this uses the same Open-Meteo **Archive**
    endpoint as ``fetch_historical`` — it returns the parsed daily dict
    (raw ``daily`` keys from the Open-Meteo response) for the supplied
    ``race_date`` (ISO ``YYYY-MM-DD``).

    A future slice can swap this to the **Forecast** endpoint
    (``https://api.open-meteo.com/v1/forecast``) when the Streamlit app
    needs real race-day lookups for upcoming races; the response shape
    is identical.
    """
    day = date.fromisoformat(race_date)
    payload = _archive_query(circuit_lat, circuit_lon, day)
    return payload.get("daily") or {}


# Re-export the request-exception class so run_pipeline can build a single net.
__all__ = [
    "fetch_historical",
    "fetch_hypothetical",
    "lookup_coords",
    "NETWORK_FAILURES",
]


NETWORK_FAILURES: tuple[type[BaseException], ...] = (RequestException,)

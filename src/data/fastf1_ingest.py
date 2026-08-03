"""FastF1 ingestion — race results and qualifying results.

Two public functions, one per round:

- ``ingest_race(season, round_)`` — finishers, grid, status, points
- ``ingest_qualifying(season, round_)`` — Q1/Q2/Q3 times + grid slot

Each is a single round call so the pipeline can be resumed round-by-round
without re-downloading successful ingests.

Why qualifying is a separate call: qualifying and race results are
published at different times, and Model A depends on qualifying being
available before we can build race features. (The orchestrator still
calls ``ingest_race`` first per round; see ``run_pipeline.main`` for the
rationale on preserving that ordering.)

Why a per-round call signature instead of bulk: keeps the pipeline
resumable, lets the orchestrator log progress round-by-round, and aligns
with the FastF1 API (one ``Session`` per round).
"""

from __future__ import annotations

from typing import Any

import fastf1
import pandas as pd
from fastf1.exceptions import (
    DataNotLoadedError,
    FastF1CriticalError,
    InvalidSessionError,
    NoLapDataError,
)
from requests.exceptions import RequestException

from src.config.settings import FASTF1_CACHE_DIR
from src.data.warehouse import connect

# --- module-level cache-enable guard ---------------------------------------
# ``fastf1.Cache.enable_cache`` is idempotent, but tracking it here means
# ad-hoc scripts and tests don't have to remember to enable it. ``main()``
# also calls this at startup, harmlessly twice.
_CACHE_ENABLED = False


def _ensure_cache_enabled() -> None:
    global _CACHE_ENABLED
    if _CACHE_ENABLED:
        return
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR), use_requests_cache=False)
    _CACHE_ENABLED = True


# --- session loader --------------------------------------------------------


def _load_session(season: int, round_: int, identifier: str):
    """Load a single FastF1 session.

    ``identifier`` is ``'R'`` for race, ``'Q'`` for qualifying, etc.
    Default ``Session.load()`` flags are sufficient — we only read
    ``session.results`` and ``session.laps``, no telemetry or weather.
    """
    _ensure_cache_enabled()
    session = fastf1.get_session(season, round_, identifier)
    session.load()
    return session


# --- small type coercion helpers -------------------------------------------


def _coerce_int(x: Any) -> int | None:
    """Coerce an arbitrary value (often a ``float`` or ``NaN``) to ``int | None``.

    FastF1 emits ``NaN`` for non-classified drivers' ``Position`` and
    ``GridPosition``. We forward ``None`` so DuckDB stores ``NULL`` rather
    than ``0`` (which would corrupt downstream model features).
    """
    if x is None:
        return None
    try:
        v = pd.to_numeric(x, errors="coerce")
    except (TypeError, ValueError):
        return None
    if pd.isna(v):
        return None
    return int(v)


def _coerce_str(x: Any) -> str | None:
    """Coerce to ``str`` or ``None`` for nullable TEXT columns."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        return None
    return str(x)


def _lap_seconds(x: Any) -> float | None:
    """Convert a ``pd.Timedelta`` (or NaT) to ``float`` seconds or ``None``."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        return None
    return float(x.total_seconds())


def _nationality(session, driver_id: str) -> str | None:
    """Return the driver's ``CountryCode`` from ``session.results``, or ``None``.

    CountryCode is FastF1's best stand-in for "nationality" — it's the
    ISO-3166-1 alpha-3 code from Ergast (e.g. ``'GBR'``, ``'MON'``). The
    warehouse schema treats this as nullable.
    """
    if session is None or session.results is None or session.results.empty:
        return None
    row = session.results.loc[session.results["DriverNumber"] == str(driver_id)]
    if row.empty:
        row = session.results.loc[session.results["Abbreviation"] == str(driver_id)]
    if row.empty:
        return None
    return _coerce_str(row.iloc[0].get("CountryCode"))


# --- upsert helpers --------------------------------------------------------


def _upsert_race_row(conn, season: int, round_: int, circuit: str, race_date) -> None:
    conn.execute(
        """
        INSERT INTO races (season, round, circuit, race_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (season, round) DO UPDATE SET
            circuit   = EXCLUDED.circuit,
            race_date = EXCLUDED.race_date
        """,
        [season, round_, circuit, race_date],
    )


def _upsert_driver(conn, driver_id: str, full_name: str, nationality: str | None) -> None:
    conn.execute(
        """
        INSERT INTO drivers (driver_id, full_name, nationality)
        VALUES (?, ?, ?)
        ON CONFLICT (driver_id) DO UPDATE SET
            full_name   = EXCLUDED.full_name,
            nationality = EXCLUDED.nationality
        """,
        [driver_id, full_name, nationality],
    )


def _upsert_result(
    conn,
    season: int,
    round_: int,
    driver_id: str,
    grid: int | None,
    finish: int | None,
    status: str | None,
    points: float | None,
) -> None:
    conn.execute(
        """
        INSERT INTO results
            (season, round, driver_id, grid_position, finish_position, status, points)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (season, round, driver_id) DO UPDATE SET
            grid_position   = EXCLUDED.grid_position,
            finish_position = EXCLUDED.finish_position,
            status          = EXCLUDED.status,
            points          = EXCLUDED.points
        """,
        [season, round_, driver_id, grid, finish, status, points],
    )


def _upsert_qualifying(
    conn,
    season: int,
    round_: int,
    driver_id: str,
    q1: float | None,
    q2: float | None,
    q3: float | None,
    grid: int | None,
) -> None:
    conn.execute(
        """
        INSERT INTO qualifying_results
            (season, round, driver_id, q1_time, q2_time, q3_time, grid_position)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (season, round, driver_id) DO UPDATE SET
            q1_time        = EXCLUDED.q1_time,
            q2_time        = EXCLUDED.q2_time,
            q3_time        = EXCLUDED.q3_time,
            grid_position  = EXCLUDED.grid_position
        """,
        [season, round_, driver_id, q1, q2, q3, grid],
    )


# --- public ingest functions -----------------------------------------------


def ingest_race(season: int, round_: int) -> int:
    """Ingest race results for one round into the warehouse.

    Returns the number of result rows written (== drivers counted).
    """
    _ensure_cache_enabled()

    # Pull the schedule row for this round to get circuit + race_date.
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    event_row = schedule.loc[schedule["RoundNumber"] == round_]
    if event_row.empty:
        raise ValueError(
            f"season={season} round={round_} not found in FastF1 schedule"
        )
    circuit = str(event_row.iloc[0]["Location"])
    race_date = pd.to_datetime(event_row.iloc[0]["EventDate"]).date()

    session = _load_session(season, round_, "R")

    written = 0
    conn = connect()
    try:
        _upsert_race_row(conn, season, round_, circuit, race_date)

        if session.results is None or session.results.empty:
            return 0

        for _, row in session.results.iterrows():
            driver_id = _coerce_str(row.get("Abbreviation"))
            if not driver_id:
                continue
            full_name = _coerce_str(row.get("FullName")) or driver_id
            # Upsert the driver FIRST so the FK on ``results`` is satisfied.
            # ``ingest_qualifying`` upserts the same driver rows; doing it
            # here too is cheap and keeps ``ingest_race`` usable in isolation.
            _upsert_driver(
                conn,
                driver_id,
                full_name,
                _nationality(session, driver_id),
            )
            _upsert_result(
                conn,
                season,
                round_,
                driver_id,
                _coerce_int(row.get("GridPosition")),
                _coerce_int(row.get("Position")),
                _coerce_str(row.get("Status")),
                None if pd.isna(row.get("Points")) else float(row.get("Points")),
            )
            written += 1

        return written
    finally:
        conn.close()


def ingest_qualifying(season: int, round_: int) -> int:
    """Ingest qualifying results for one round into the warehouse.

    Returns the number of qualifying rows written.
    """
    session = _load_session(season, round_, "Q")

    if session.results is None or session.results.empty:
        return 0

    written = 0
    conn = connect()
    try:
        for _, row in session.results.iterrows():
            driver_id = _coerce_str(row.get("Abbreviation"))
            if not driver_id:
                continue
            full_name = _coerce_str(row.get("FullName")) or driver_id
            grid = _coerce_int(row.get("GridPosition"))

            # Best Q1/Q2/Q3 from FastF1's session status split.
            q1 = q2 = q3 = None
            try:
                splits = session.laps.pick_driver(driver_id).split_qualifying_sessions()
                # Returns [Q1_laps, Q2_laps, Q3_laps]; None if a session was cancelled.
                for seg_idx, target in enumerate((q1, q2, q3)):
                    seg = splits[seg_idx] if seg_idx < len(splits) else None
                    if seg is None or len(seg) == 0:
                        continue
                    fastest = seg.pick_fastest()
                    if fastest is not None:
                        val = fastest.get("LapTime")
                        if seg_idx == 0:
                            q1 = _lap_seconds(val)
                        elif seg_idx == 1:
                            q2 = _lap_seconds(val)
                        else:
                            q3 = _lap_seconds(val)
            except (NoLapDataError, KeyError, AttributeError, ValueError):
                # Driver may have no laps in this session (e.g. withdrew).
                # Forward NULLs — do not abort the round.
                pass

            _upsert_qualifying(conn, season, round_, driver_id, q1, q2, q3, grid)
            _upsert_driver(
                conn,
                driver_id,
                full_name,
                _nationality(session, driver_id),
            )
            written += 1

        return written
    finally:
        conn.close()


# Re-export the network-failure exception list so run_pipeline can import
# them from one place if it wants a single net.
NETWORK_FAILURES: tuple[type[BaseException], ...] = (
    DataNotLoadedError,
    InvalidSessionError,
    NoLapDataError,
    FastF1CriticalError,
    RequestException,
)

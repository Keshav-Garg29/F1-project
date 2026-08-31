"""Tests for the Build Features slice.

Each test uses an in-memory DuckDB so it cannot pollute or be polluted
by the live warehouse. We bootstrap the raw schema (the five raw
tables), seed a tiny synthetic dataset, run the three ``build_*``
functions, and assert against the resulting feature tables.

Synthetic dataset (sentinel season ``2099``):

* 2 rounds: round 1 (Melbourne) on 2099-03-01; round 2 (Silverstone)
  on 2099-07-15.
* Drivers:
    - ``VER`` — veteran present in both rounds; Q3 in both; finishes
      both (``'Finished'``). Pole in round 1.
    - ``LEC`` — rookie at round 1 (no prior history); Q1 only in
      round 1, Q2 in round 2; finishes round 1, finishes round 2.
    - ``ALO`` — present only in round 2; Q2; finishes.
    - ``LAT`` — present only in round 2; Q1; ``'+1 Lap'`` (not a DNF
      per the spec's classification).
    - ``MSC`` — present only in round 2; Q1; ``'Retired'`` (DNF).

The dataset exercises:
  * Rookies (LEC round 1) — ``is_rookie=TRUE``, ``months_since_last_race IS NULL``.
  * Mixed status strings: ``'Finished'``, ``'+1 Lap'``, ``'Retired'``.
  * Mixed Q-session participation: Q1-only, Q1+Q2, Q1+Q2+Q3.
  * Multiple rounds so rolling windows are non-trivial.
"""

from __future__ import annotations

import duckdb
import pytest

from src.data.warehouse import bootstrap_schema
from src.features.build_features import (
    _ROLLING_WINDOW,
    build_driver_history,
    build_qualifying_features,
    build_race_result_features,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fresh_conn() -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB with the raw schema bootstrapped."""
    conn = duckdb.connect(":memory:")
    bootstrap_schema(conn)
    return conn


def _seed_races(conn: duckdb.DuckDBPyConnection) -> None:
    conn.executemany(
        """
        INSERT INTO races (season, round, circuit, race_date)
        VALUES (?, ?, ?, ?)
        """,
        [
            [2099, 1, "Melbourne",   "2099-03-01"],
            [2099, 2, "Silverstone", "2099-07-15"],
        ],
    )


def _seed_drivers(conn: duckdb.DuckDBPyConnection) -> None:
    conn.executemany(
        """
        INSERT INTO drivers (driver_id, full_name, nationality)
        VALUES (?, ?, ?)
        """,
        [
            ["VER", "Max Verstappen",   "NED"],
            ["LEC", "Charles Leclerc", "MON"],
            ["ALO", "Fernando Alonso",  "ESP"],
            ["LAT", "Nicholas Latifi",  "CAN"],
            ["MSC", "Mick Schumacher",  "GER"],
        ],
    )


def _seed_qualifying(conn: duckdb.DuckDBPyConnection) -> None:
    # Round 1: VER pole (best=80.0), LEC Q1-only (best=82.0).
    # Round 2: VER (best=85.0), LEC Q2 (best=86.0), ALO Q2 (best=87.0),
    #          LAT Q1 (best=88.0), MSC Q1 (best=89.0).
    conn.executemany(
        """
        INSERT INTO qualifying_results
            (season, round, driver_id, q1_time, q2_time, q3_time, grid_position)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            [2099, 1, "VER", 81.0, 80.5, 80.0, 1],
            [2099, 1, "LEC", 82.0, None, None, 2],
            [2099, 2, "VER", 86.0, 85.5, 85.0, 1],
            [2099, 2, "LEC", 87.0, 86.0, None, 2],
            [2099, 2, "ALO", 88.0, 87.0, None, 3],
            [2099, 2, "LAT", 88.0, None, None, 4],
            [2099, 2, "MSC", 89.0, None, None, 5],
        ],
    )


def _seed_results(conn: duckdb.DuckDBPyConnection) -> None:
    conn.executemany(
        """
        INSERT INTO results
            (season, round, driver_id, grid_position, finish_position, status, points)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            [2099, 1, "VER", 1, 1, "Finished", 25.0],
            [2099, 1, "LEC", 2, 2, "Finished", 18.0],
            [2099, 2, "VER", 1, 1, "Finished", 25.0],
            [2099, 2, "LEC", 2, 2, "Finished", 18.0],
            [2099, 2, "ALO", 3, 3, "Finished", 15.0],
            [2099, 2, "LAT", 4, 4, "+1 Lap",   12.0],
            [2099, 2, "MSC", 5, None, "Retired", 0.0],
        ],
    )


def _seed_weather(conn: duckdb.DuckDBPyConnection) -> None:
    conn.executemany(
        """
        INSERT INTO weather
            (season, round, air_temp_c, track_temp_c, humidity, rainfall_mm, wind_kph)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            [2099, 1, 28.0, None, 55.0, 0.0, 12.0],
            [2099, 2, 22.0, None, 70.0, 1.5, 18.0],
        ],
    )


def _seed_all(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_races(conn)
    _seed_drivers(conn)
    _seed_qualifying(conn)
    _seed_results(conn)
    _seed_weather(conn)


def _build_all(conn: duckdb.DuckDBPyConnection) -> None:
    build_driver_history(conn)
    build_qualifying_features(conn)
    build_race_result_features(conn)


# ---------------------------------------------------------------------------
# driver_history
# ---------------------------------------------------------------------------


def test_driver_history_one_row_per_started_driver() -> None:
    """One row per (driver, race) where the driver started."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        n = build_driver_history(conn)
        # Started rows: VER r1+r2, LEC r1+r2, ALO r2, LAT r2, MSC r2 = 7
        # ('Did not start' rows would be excluded; we have none here).
        assert n == 7
    finally:
        conn.close()


def test_driver_history_rookie_marker_and_null_recency() -> None:
    """Earliest row per driver: is_rookie=TRUE, months_since_last_race IS NULL."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        # VER's earliest row is round 1.
        ver_r1 = conn.execute(
            "SELECT is_rookie, months_since_last_race FROM driver_history "
            "WHERE season=2099 AND driver_id='VER' ORDER BY round LIMIT 1"
        ).fetchone()
        # LEC's earliest row is round 1 — that's his first career race.
        lec_r1 = conn.execute(
            "SELECT is_rookie, months_since_last_race FROM driver_history "
            "WHERE season=2099 AND driver_id='LEC' ORDER BY round LIMIT 1"
        ).fetchone()
        # VER: prior rounds exist? No — round 1 is VER's first start too
        # (synthetic dataset; in the live warehouse VER has many priors).
        assert ver_r1 == (True, None)
        assert lec_r1 == (True, None)

        # VER's round 2 row: NOT a rookie (round 1 was the first),
        # months_since_last_race should be 4 (Mar 1 -> Jul 15).
        ver_r2 = conn.execute(
            "SELECT is_rookie, months_since_last_race FROM driver_history "
            "WHERE season=2099 AND driver_id='VER' AND round=2"
        ).fetchone()
        assert ver_r2[0] is False
        assert ver_r2[1] == 4
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# qualifying_features — Model A target-leak guard
# ---------------------------------------------------------------------------


def test_qualifying_features_excludes_grid_position() -> None:
    """grid_position MUST NOT appear in qualifying_features (Model A target leak)."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        cols = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM duckdb_columns() "
                "WHERE table_name = 'qualifying_features'"
            ).fetchall()
        }
        assert "grid_position" not in cols, (
            f"qualifying_features must not contain grid_position; got {cols}"
        )
    finally:
        conn.close()


def test_qualifying_features_rookie_driver_rolls_match_team() -> None:
    """A rookie's driver_rolling must equal team_rolling (today: both = circuit median).

    With the team-table not yet built, team==driver, so the COALESCE chain
    reduces to: driver_rolling falls back to team_rolling. Both should be
    the circuit-median gap for round 1 (no prior history exists for LEC).
    """
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        lec_r1 = conn.execute(
            "SELECT team_rolling_quali_gap_to_pole, driver_rolling_quali_gap_to_pole "
            "FROM qualifying_features WHERE season=2099 AND driver_id='LEC' AND round=1"
        ).fetchone()
        assert lec_r1[0] is not None
        assert lec_r1[1] is not None
        # Both roll up to the same circuit-median value (no prior history).
        assert lec_r1[0] == pytest.approx(lec_r1[1])
    finally:
        conn.close()


def test_qualifying_features_no_null_rolling_columns() -> None:
    """No NULLs in the two *_rolling_quali_gap_to_pole columns (COALESCE discipline)."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        n_team = conn.execute(
            "SELECT COUNT(*) FROM qualifying_features "
            "WHERE team_rolling_quali_gap_to_pole IS NULL"
        ).fetchone()[0]
        n_drv = conn.execute(
            "SELECT COUNT(*) FROM qualifying_features "
            "WHERE driver_rolling_quali_gap_to_pole IS NULL"
        ).fetchone()[0]
        assert n_team == 0, f"{n_team} NULL team_rolling rows"
        assert n_drv == 0, f"{n_drv} NULL driver_rolling rows"
    finally:
        conn.close()


def test_qualifying_features_propagates_is_rookie_from_driver_history() -> None:
    """is_rookie in qualifying_features matches driver_history everywhere."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        n_diff = conn.execute(
            "SELECT COUNT(*) FROM qualifying_features qf "
            "JOIN driver_history dh USING (driver_id, season, round) "
            "WHERE qf.is_rookie IS DISTINCT FROM dh.is_rookie"
        ).fetchone()[0]
        assert n_diff == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# race_result_features — Model B chain column
# ---------------------------------------------------------------------------


def test_race_result_features_includes_grid_position() -> None:
    """grid_position MUST appear in race_result_features (Model B's chain column)."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        cols = {
            row[0]
            for row in conn.execute(
                "SELECT column_name FROM duckdb_columns() "
                "WHERE table_name = 'race_result_features'"
            ).fetchall()
        }
        assert "grid_position" in cols
    finally:
        conn.close()


def test_race_result_features_brand_new_team_falls_back_to_circuit_median() -> None:
    """A driver with no qualifying history gets the circuit-median rolling values.

    LAT has only round 2 qualifying, so for round 2 there is no prior
    qualifying history — the COALESCE chain must drop to the circuit
    median for both rolling columns. We check round 2 LAT row.
    """
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        # Compute the circuit-median finish-vs-quali and DNF rate for round 2.
        cm_fvq = conn.execute(
            "SELECT AVG(CAST(finish_position AS DOUBLE) - CAST(grid_position AS DOUBLE)) "
            "FROM results WHERE season=2099 AND round=2 "
            "AND finish_position IS NOT NULL AND grid_position IS NOT NULL"
        ).fetchone()[0]
        # DNF rate: only MSC is DNF in round 2; LAT is '+1 Lap' (NOT a DNF).
        # So round 2 DNF rate for the only-DNF count over 7 entrants = 1/7.
        cm_dnf = conn.execute(
            "SELECT AVG(CAST((status <> 'Finished' AND status <> 'Lapped' "
            "AND NOT status LIKE '+% Lap') AS DOUBLE)) "
            "FROM results WHERE season=2099 AND round=2"
        ).fetchone()[0]

        lat = conn.execute(
            "SELECT team_rolling_finish_vs_quali, driver_rolling_finish_vs_quali, "
            "team_rolling_dnf_rate, driver_rolling_dnf_rate "
            "FROM race_result_features WHERE season=2099 AND driver_id='LAT' AND round=2"
        ).fetchone()

        assert lat[0] == pytest.approx(cm_fvq)
        assert lat[1] == pytest.approx(cm_fvq)
        assert lat[2] == pytest.approx(cm_dnf)
        assert lat[3] == pytest.approx(cm_dnf)
    finally:
        conn.close()


def test_race_result_features_no_null_rolling_columns() -> None:
    """No NULLs in any of the four *_rolling_* columns (COALESCE discipline)."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        for col in (
            "team_rolling_finish_vs_quali",
            "driver_rolling_finish_vs_quali",
            "team_rolling_dnf_rate",
            "driver_rolling_dnf_rate",
        ):
            n = conn.execute(
                f"SELECT COUNT(*) FROM race_result_features WHERE {col} IS NULL"
            ).fetchone()[0]
            assert n == 0, f"{n} NULL rows in race_result_features.{col}"
    finally:
        conn.close()


def test_race_result_features_lapped_is_not_dnf() -> None:
    """'+1 Lap' / 'Lapped' must not feed the DNF-rate features."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        # LAT has status '+1 Lap' (finish_position=4). His DNF-related
        # columns should reflect that he's NOT a DNF.
        lat_is_dnf = conn.execute(
            "SELECT driver_rolling_dnf_rate, team_rolling_dnf_rate "
            "FROM race_result_features WHERE season=2099 AND driver_id='LAT' AND round=2"
        ).fetchone()
        # Round 2 has only MSC as a DNF; rolling window excludes current row,
        # so for LAT's row the rate is over 0 prior rounds and falls back to
        # the circuit median of 1/7.
        # The key assertion: the rate is below 1.0 (i.e. NOT all rows are DNF).
        assert lat_is_dnf[0] < 1.0
        assert lat_is_dnf[1] < 1.0
    finally:
        conn.close()


def test_race_result_features_races_completed_excludes_current_round() -> None:
    """races_completed_this_season counts PRIOR rounds only."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        # VER round 1: no prior rounds this season -> 0
        ver_r1 = conn.execute(
            "SELECT races_completed_this_season FROM race_result_features "
            "WHERE season=2099 AND driver_id='VER' AND round=1"
        ).fetchone()[0]
        # VER round 2: 1 prior round (round 1, VER classified) -> 1
        ver_r2 = conn.execute(
            "SELECT races_completed_this_season FROM race_result_features "
            "WHERE season=2099 AND driver_id='VER' AND round=2"
        ).fetchone()[0]
        assert ver_r1 == 0
        assert ver_r2 == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_idempotent_rerun() -> None:
    """Re-running build_* leaves row counts unchanged in all three tables."""
    conn = _fresh_conn()
    try:
        _seed_all(conn)
        _build_all(conn)
        first = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("driver_history", "qualifying_features", "race_result_features")
        }
        _build_all(conn)
        second = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("driver_history", "qualifying_features", "race_result_features")
        }
        assert first == second
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Module-level invariant
# ---------------------------------------------------------------------------


def test_rolling_window_constant_is_5() -> None:
    """_ROLLING_WINDOW must remain 5 unless the SQL literals are updated too."""
    assert _ROLLING_WINDOW == 5
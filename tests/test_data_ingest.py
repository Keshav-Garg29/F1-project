"""Tests for the data-ingestion slice.

Mirrors the style of ``test_warehouse.py``: bare ``assert``, explicit
``try/finally``, direct ``connect()``. Tests that write rows clean up
after themselves in ``finally`` so the warehouse starts clean for the
next test run.

These tests do not hit the network. FastF1 and Open-Meteo calls are
monkey-patched throughout.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data.run_pipeline import _iter_rounds, main
from src.data.warehouse import connect


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _delete(conn, table: str, where: str, params: list) -> None:
    """``DELETE FROM <table> WHERE <where>`` with positional parameters."""
    conn.execute(f"DELETE FROM {table} WHERE {where}", params)


# ---------------------------------------------------------------------------
# _iter_rounds
# ---------------------------------------------------------------------------


def test_iter_rounds_filters_testing_and_zeros() -> None:
    """RoundNumber 0 (testing), NaN, and any falsy values must be filtered out."""
    schedule = pd.DataFrame({"RoundNumber": [0, 1, 2, 3, float("nan"), 7]})
    with patch("src.data.run_pipeline.fastf1.get_event_schedule", return_value=schedule):
        rounds = _iter_rounds(2024)
    assert rounds == [1, 2, 3, 7]


def test_iter_rounds_empty_schedule() -> None:
    """Empty schedule should yield an empty list — not raise."""
    schedule = pd.DataFrame({"RoundNumber": []})
    with patch("src.data.run_pipeline.fastf1.get_event_schedule", return_value=schedule):
        rounds = _iter_rounds(2024)
    assert rounds == []


def test_iter_rounds_returns_list_int() -> None:
    """Return type is list[int], not range — callers may iterate twice."""
    schedule = pd.DataFrame({"RoundNumber": [1, 2, 3]})
    with patch("src.data.run_pipeline.fastf1.get_event_schedule", return_value=schedule):
        rounds = _iter_rounds(2024)
    assert isinstance(rounds, list)
    assert all(isinstance(r, int) for r in rounds)


# ---------------------------------------------------------------------------
# SQL idempotency (direct, no FastF1)
# ---------------------------------------------------------------------------


def test_races_upsert_is_idempotent() -> None:
    """Same PK twice should not double-write."""
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO races (season, round, circuit, race_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (season, round) DO UPDATE SET
                circuit   = EXCLUDED.circuit,
                race_date = EXCLUDED.race_date
            """,
            [2099, 1, "Test Circuit", "2099-01-01"],
        )
        conn.execute(
            """
            INSERT INTO races (season, round, circuit, race_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (season, round) DO UPDATE SET
                circuit   = EXCLUDED.circuit,
                race_date = EXCLUDED.race_date
            """,
            [2099, 1, "Test Circuit", "2099-01-01"],
        )
        n = conn.execute(
            "SELECT COUNT(*) FROM races WHERE season=2099 AND round=1"
        ).fetchone()[0]
        assert n == 1
    finally:
        _delete(conn, "races", "season = ?", [2099])
        conn.close()


def test_results_upsert_is_idempotent() -> None:
    """Second insert with different ``points`` must overwrite, not stack."""
    conn = connect()
    try:
        # FK parents
        conn.execute(
            """
            INSERT INTO races (season, round, circuit, race_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (season, round) DO UPDATE SET
                circuit = EXCLUDED.circuit, race_date = EXCLUDED.race_date
            """,
            [2099, 2, "Test", "2099-01-01"],
        )
        conn.execute(
            """
            INSERT INTO drivers (driver_id, full_name, nationality)
            VALUES (?, ?, ?)
            ON CONFLICT (driver_id) DO UPDATE SET
                full_name = EXCLUDED.full_name, nationality = EXCLUDED.nationality
            """,
            ["TST", "Test Driver", "GBR"],
        )

        for pts in (10.0, 25.0):
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
                [2099, 2, "TST", 1, 1, "Finished", pts],
            )

        n = conn.execute(
            "SELECT COUNT(*) FROM results WHERE season=2099 AND round=2"
        ).fetchone()[0]
        assert n == 1
        row = conn.execute(
            "SELECT points FROM results WHERE season=2099 AND round=2 AND driver_id='TST'"
        ).fetchone()
        assert row[0] == 25.0
    finally:
        _delete(conn, "results", "season = ?", [2099])
        _delete(conn, "races", "season = ?", [2099])
        _delete(conn, "drivers", "driver_id = ?", ["TST"])
        conn.close()


def test_qualifying_results_upsert_is_idempotent() -> None:
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO races (season, round, circuit, race_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (season, round) DO UPDATE SET
                circuit = EXCLUDED.circuit, race_date = EXCLUDED.race_date
            """,
            [2099, 3, "Test", "2099-01-01"],
        )
        conn.execute(
            """
            INSERT INTO drivers (driver_id, full_name, nationality)
            VALUES (?, ?, ?)
            ON CONFLICT (driver_id) DO UPDATE SET
                full_name = EXCLUDED.full_name, nationality = EXCLUDED.nationality
            """,
            ["TST", "Test Driver", "GBR"],
        )

        for q1 in (60.0, 59.5):
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
                [2099, 3, "TST", q1, None, None, 1],
            )

        n = conn.execute(
            "SELECT COUNT(*) FROM qualifying_results WHERE season=2099 AND round=3"
        ).fetchone()[0]
        assert n == 1
        row = conn.execute(
            "SELECT q1_time FROM qualifying_results "
            "WHERE season=2099 AND round=3 AND driver_id='TST'"
        ).fetchone()
        assert row[0] == 59.5
    finally:
        _delete(conn, "qualifying_results", "season = ?", [2099])
        _delete(conn, "races", "season = ?", [2099])
        _delete(conn, "drivers", "driver_id = ?", ["TST"])
        conn.close()


# ---------------------------------------------------------------------------
# Weather upsert (mocked HTTP)
# ---------------------------------------------------------------------------


def test_weather_upsert_with_null_track_temp() -> None:
    """``track_temp_c`` must always be NULL — Open-Meteo exposes no track variable."""
    # Parent row in ``races`` is required by FK.
    conn = connect()
    try:
        conn.execute(
            """
            INSERT INTO races (season, round, circuit, race_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (season, round) DO UPDATE SET
                circuit = EXCLUDED.circuit, race_date = EXCLUDED.race_date
            """,
            [2099, 4, "Sakhir", "2099-03-01"],
        )

        # Mock Open-Meteo response.
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "daily": {
                "time": ["2099-03-01"],
                "temperature_2m_max": [31.5],
                "relative_humidity_2m_mean": [55.0],
                "precipitation_sum": [0.0],
                "wind_speed_10m_max": [12.3],
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("src.data.weather_ingest._HTTP.get", return_value=mock_resp):
            from src.data.weather_ingest import fetch_historical
            written = fetch_historical(2099, 4)
        assert written == 1

        row = conn.execute(
            "SELECT air_temp_c, track_temp_c, humidity, rainfall_mm, wind_kph "
            "FROM weather WHERE season=2099 AND round=4"
        ).fetchone()
        assert row is not None
        air, track, hum, rain, wind = row
        assert air == pytest.approx(31.5)
        assert track is None      # the rule
        assert hum == pytest.approx(55.0)
        assert rain == pytest.approx(0.0)
        assert wind == pytest.approx(12.3)
    finally:
        _delete(conn, "weather", "season = ?", [2099])
        _delete(conn, "races", "season = ?", [2099])
        conn.close()


# ---------------------------------------------------------------------------
# ingest_race happy path (mocked FastF1)
# ---------------------------------------------------------------------------


def test_ingest_race_records_one_row_per_driver() -> None:
    """A 3-driver race session must write 3 results, 3 drivers, 1 race."""
    conn = connect()
    try:
        schedule = pd.DataFrame({
            "RoundNumber": [1],
            "Location":    ["Sakhir"],
            "EventDate":   [pd.Timestamp("2024-03-02")],
        })
        results_df = pd.DataFrame({
            "DriverNumber": ["1", "2", "3"],
            "Abbreviation":  ["VER", "PER", "ALO"],
            "FullName":      ["Max Verstappen", "Sergio Perez", "Fernando Alonso"],
            "TeamName":      ["Red Bull", "Red Bull", "Aston Martin"],
            "CountryCode":   ["NED", "MEX", "ESP"],
            "Position":      [1.0, 2.0, 3.0],
            "GridPosition":  [1.0, 3.0, 2.0],
            "Status":        ["Finished", "Finished", "Finished"],
            "Points":        [25.0, 18.0, 15.0],
        })
        # Build a fake session whose .results is the DataFrame and whose
        # .load() is a no-op.
        fake_session = MagicMock()
        fake_session.results = results_df
        fake_session.load = MagicMock()

        with patch("src.data.fastf1_ingest.fastf1.get_event_schedule",
                   return_value=schedule), \
             patch("src.data.fastf1_ingest.fastf1.get_session",
                   return_value=fake_session):
            from src.data.fastf1_ingest import ingest_race
            written = ingest_race(2024, 1)

        assert written == 3

        n_races = conn.execute(
            "SELECT COUNT(*) FROM races WHERE season=2024 AND round=1"
        ).fetchone()[0]
        n_results = conn.execute(
            "SELECT COUNT(*) FROM results WHERE season=2024 AND round=1"
        ).fetchone()[0]
        n_drivers = conn.execute(
            "SELECT COUNT(*) FROM drivers WHERE driver_id IN ('VER','PER','ALO')"
        ).fetchone()[0]
        assert n_races == 1
        assert n_results == 3
        assert n_drivers == 3
    finally:
        # Clear every FK-protected row that references our test drivers before
        # deleting the drivers themselves. ``season = 2024`` alone isn't enough
        # when a background pipeline is also writing real results for these
        # drivers in other seasons — those would orphan-violate the delete.
        for d in ("VER", "PER", "ALO"):
            _delete(conn, "results", "driver_id = ?", [d])
            _delete(conn, "qualifying_results", "driver_id = ?", [d])
        _delete(conn, "results", "season = ?", [2024])
        _delete(conn, "races", "season = ?", [2024])
        for d in ("VER", "PER", "ALO"):
            _delete(conn, "drivers", "driver_id = ?", [d])
        conn.close()


def test_ingest_qualifying_records_one_row_per_driver() -> None:
    """A 3-driver qualifying session must write 3 qualifying rows + 3 drivers.

    Mocks the FastF1 schedule + session with a ``laps`` MagicMock whose
    ``pick_drivers(...).split_qualifying_sessions()`` returns three
    1-row Laps DataFrames. This is the regression test for the
    ``pick_driver`` -> ``pick_drivers`` deprecation fix.
    """
    conn = connect()
    try:
        schedule = pd.DataFrame({
            "RoundNumber": [1],
            "Location":    ["Sakhir"],
            "EventDate":   [pd.Timestamp("2024-03-02")],
        })
        results_df = pd.DataFrame({
            "DriverNumber": ["1", "2", "3"],
            "Abbreviation":  ["VER", "PER", "ALO"],
            "FullName":      ["Max Verstappen", "Sergio Perez", "Fernando Alonso"],
            "TeamName":      ["Red Bull", "Red Bull", "Aston Martin"],
            "CountryCode":   ["NED", "MEX", "ESP"],
            "Position":      [1.0, 2.0, 3.0],
            "GridPosition":  [1.0, 2.0, 3.0],
        })

        # Build a fake qualifying session. We need:
        #   - session.results (DataFrame) — used to drive the row loop
        #   - session.laps.pick_drivers(id).split_qualifying_sessions()
        #         returns three seg-like objects, each whose pick_fastest()
        #         exposes a Timedelta LapTime the production code can read.
        #
        # The production code does ``len(seg)`` (truthy check) then
        # ``seg.pick_fastest().get("LapTime")``. ``pick_fastest()`` returns
        # a pandas Series, and ``Series.get("LapTime")`` returns the column
        # value. Each seg is therefore a Mock that reports a non-zero length
        # and whose ``pick_fastest()`` yields a 1-row Series with a
        # ``LapTime`` Timedelta.
        q1_lap_time = pd.Timedelta(seconds=90.0)
        q2_lap_time = pd.Timedelta(seconds=89.5)
        q3_lap_time = pd.Timedelta(seconds=89.0)

        def _make_seg(lap_time: pd.Timedelta) -> MagicMock:
            seg = MagicMock()
            seg.__len__.return_value = 1
            # ``pick_fastest()`` returns a pandas Series with a LapTime column.
            seg.pick_fastest.return_value = pd.Series(
                {"LapTime": lap_time}
            )
            return seg

        def _make_laps_pick(driver_id):
            """``pick_drivers(driver_id)`` returns a Mock whose
            ``split_qualifying_sessions()`` yields three seg Mocks keyed
            to the driver's expected Q1/Q2/Q3 lap time."""
            picks = {
                "VER": _make_seg(q1_lap_time),
                "PER": _make_seg(q2_lap_time),
                "ALO": _make_seg(q3_lap_time),
            }
            seg = picks[driver_id]
            select_mock = MagicMock()
            # Same seg for all three slots — Q1/Q2/Q3 are distinct in real
            # FastF1 data, but for this test we only need *some* Timedelta
            # to reach the qualifying_results row.
            select_mock.split_qualifying_sessions.return_value = [seg, seg, seg]
            return select_mock

        laps_mock = MagicMock()
        laps_mock.pick_drivers.side_effect = _make_laps_pick

        fake_session = MagicMock()
        fake_session.results = results_df
        fake_session.laps = laps_mock
        fake_session.load = MagicMock()

        with patch("src.data.fastf1_ingest.fastf1.get_event_schedule",
                   return_value=schedule), \
             patch("src.data.fastf1_ingest.fastf1.get_session",
                   return_value=fake_session):
            from src.data.fastf1_ingest import ingest_qualifying
            written = ingest_qualifying(2024, 1)

        assert written == 3

        n_quali = conn.execute(
            "SELECT COUNT(*) FROM qualifying_results WHERE season=2024 AND round=1"
        ).fetchone()[0]
        n_drivers = conn.execute(
            "SELECT COUNT(*) FROM drivers WHERE driver_id IN ('VER','PER','ALO')"
        ).fetchone()[0]
        assert n_quali == 3
        assert n_drivers == 3

        # Spot-check that the Q1 time was stored in seconds (90.0).
        q1_row = conn.execute(
            "SELECT q1_time FROM qualifying_results "
            "WHERE season=2024 AND round=1 AND driver_id='VER'"
        ).fetchone()
        assert q1_row[0] == pytest.approx(90.0)
    finally:
        # Same FK-protect-before-driver-delete pattern as the race test:
        # any results / qualifying_results rows referencing our drivers must
        # be cleared first, otherwise a concurrent pipeline write blocks the
        # driver delete with a foreign-key violation.
        for d in ("VER", "PER", "ALO"):
            _delete(conn, "results", "driver_id = ?", [d])
            _delete(conn, "qualifying_results", "driver_id = ?", [d])
        _delete(conn, "qualifying_results", "season = ?", [2024])
        for d in ("VER", "PER", "ALO"):
            _delete(conn, "drivers", "driver_id = ?", [d])
        conn.close()


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------


def test_main_exits_nonzero_on_failure() -> None:
    """If ``ingest_race`` raises, ``main`` must return 1 (not crash)."""
    with patch("src.data.run_pipeline._iter_rounds", return_value=[1]), \
         patch("src.data.run_pipeline.ingest_race",
               side_effect=RuntimeError("boom")), \
         patch("src.data.run_pipeline.ingest_qualifying"), \
         patch("src.data.run_pipeline.fetch_historical"):
        rc = main()
    assert rc == 1


def test_main_exits_zero_on_clean_run() -> None:
    """An empty round list is a clean run — return 0."""
    with patch("src.data.run_pipeline._iter_rounds", return_value=[]):
        rc = main()
    assert rc == 0

"""Build the three feature tables consumed by training and inference.

Tables produced (all in DuckDB, all SQL-defined):

1. ``driver_history`` — shared experience/recency per (driver, race)
   (``total_races_started``, ``months_since_last_race``, ``is_rookie``)
2. ``qualifying_features`` — Model A inputs
3. ``race_result_features`` — Model B inputs (joins Model A's
   ``grid_position`` for inference; uses real ``grid_position`` at
   training time — one code path, see CLAUDE.md "Tech constraints")

The three feature tables live here, not in ``warehouse._SCHEMA_STATEMENTS``,
because they are owned by this slice. ``sql/schema.sql`` mirrors only the
raw warehouse tables.

Notes on decisions deferred to implementation time:

* The ``home_race`` column listed in the spec is dropped this slice. The
  raw schema has no ``races.country`` to compare against
  ``drivers.nationality``, and adding a hand-maintained city-to-country
  dict would re-introduce the drift the ingestion layer's
  ``CIRCUIT_COORDS`` lookup was meant to warn against. Re-add ``home_race``
  here (and update CLAUDE.md's feature contract) once ``races.country``
  exists. TODO(home-race): reintroduce ``home_race`` after a
  ``races.country`` column is added.
* "Team" is approximated by ``qualifying_results.driver_id`` because the
  raw schema has no team table. A future team-table follow-up should
  replace every ``_driver_team`` CTE with a real lookup. The COALESCE
  chain in the projections already handles the future team-table swap
  without further changes.
* DNF classification for the ``*_dnf_rate`` features:
  ``status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+% Lap'``.
  ``'Lapped'`` drivers have a non-NULL ``finish_position`` in FastF1's
  Status column (they finished, more than a lap down) — they are NOT
  counted as DNFs. ``'+1 Lap'`` / ``'+2 Laps'`` / ... likewise mean the
  car was still running at the flag, just lapped.
"""

from __future__ import annotations

import duckdb

from src.data.warehouse import connect

# Rolling-window size for all four ``*_rolling_*`` features. N=5 covers
# roughly a third of an F1 season — short enough to react to car upgrades,
# long enough to smooth out one-off outliers (rain, traffic, mechanical).
# DuckDB rejects ``?`` parameters inside ``ROWS BETWEEN ? PRECEDING``,
# so the SQL hardcodes ``5 PRECEDING`` with an inline ``/* keep in sync
# with _ROLLING_WINDOW */`` marker.
_ROLLING_WINDOW: int = 5


def build_driver_history(conn: duckdb.DuckDBPyConnection) -> int:
    """Materialise the shared experience/recency feature block.

    One row per ``(driver, race)`` where the driver started the race
    (i.e. has a row in ``results`` and is not status ``'Did not start'``).
    DNFs are kept — a retired or accident-stricken driver still started.

    Why two columns (volume + freshness): CLAUDE.md explicitly forbids
    collapsing experience and recency into one number — a returning
    driver after a long layoff must look different from a continuously
    active driver with the same career race count. ``total_races_started``
    captures career volume; ``months_since_last_race`` captures freshness.

    Idempotent: ``DELETE FROM driver_history`` before the insert keeps
    row counts stable across re-runs while leaving the table object in
    place for any reader that has already opened a connection.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS driver_history (
            season                 INTEGER NOT NULL,
            round                  INTEGER NOT NULL,
            driver_id              TEXT    NOT NULL,
            total_races_started    INTEGER NOT NULL,
            months_since_last_race REAL,
            is_rookie              BOOLEAN NOT NULL,
            PRIMARY KEY (season, round, driver_id)
        )
        """
    )
    conn.execute("DELETE FROM driver_history")

    conn.execute(
        """
        INSERT INTO driver_history
            (season, round, driver_id, total_races_started,
             months_since_last_race, is_rookie)
        WITH started AS (
            -- One row per (driver, race) where a result was recorded.
            -- Keep DNFs; drop 'Did not start' — they never lined up on
            -- the grid so "career race starts" should not include them.
            SELECT r.season, r.round, r.driver_id, ra.race_date
            FROM results r
            JOIN races  ra
              ON ra.season = r.season AND ra.round = r.round
            WHERE r.status IS DISTINCT FROM 'Did not start'
        ),
        ordered AS (
            SELECT
                season, round, driver_id, race_date,
                -- Career starts STRICTLY before this row. ``ROWS ... 1
                -- PRECEDING`` excludes the current row, so the first
                -- career race naturally counts as 0 (rookie).
                CAST(COUNT(*) OVER (
                    PARTITION BY driver_id
                    ORDER BY season, round
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) AS INTEGER) AS total_races_started,
                -- Months between this race and the driver's previous
                -- race. LAG returns NULL on the first row, and DuckDB's
                -- DATEDIFF propagates NULL when either operand is NULL
                -- — so the rookie signal (no previous race) falls out
                -- naturally with no CASE WHEN needed.
                DATEDIFF('month',
                    LAG(race_date) OVER (
                        PARTITION BY driver_id ORDER BY season, round
                    ),
                    race_date
                ) AS months_since_last_race
            FROM started
        )
        SELECT
            season, round, driver_id,
            total_races_started,
            months_since_last_race,
            (total_races_started = 0) AS is_rookie
        FROM ordered
        """
    )
    n = conn.execute("SELECT COUNT(*) FROM driver_history").fetchone()[0]
    return n


def build_qualifying_features(conn: duckdb.DuckDBPyConnection) -> int:
    """Model A feature table.

    Target-leak guard: ``grid_position`` MUST NOT appear in this table.
    ``train_qualifying_model`` asserts this at load time; we make that
    assertion impossible to fail by simply omitting the column.

    Car-performance signal: ``team_rolling_quali_gap_to_pole`` is the
    rolling mean of ``(driver_best_qual_time - circuit_pole_time)`` over
    the prior ``_ROLLING_WINDOW`` rounds, keyed at the team level. Until
    a team table exists, "team" is ``qualifying_results.driver_id`` —
    see the ``_driver_team`` CTE (TODO(team-table) marks the swap-out).

    Rookie/NULL handling:
        * Driver-level rolls ``COALESCE`` to team-level rolls, which
          ``COALESCE`` to the circuit median across all drivers for
          brand-new teams.
        * No row in this table is permitted to have NULL rolling values
          (Definition of done in the spec).
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qualifying_features (
            season                           INTEGER NOT NULL,
            round                            INTEGER NOT NULL,
            driver_id                        TEXT    NOT NULL,
            circuit                          TEXT    NOT NULL,
            total_races_started              INTEGER NOT NULL,
            months_since_last_race           REAL,
            is_rookie                        BOOLEAN NOT NULL,
            best_qual_time                   REAL,
            made_q3                          BOOLEAN,
            made_q2                          BOOLEAN,
            circuit_quali_rank_pressure_proxy INTEGER,
            team_rolling_quali_gap_to_pole   REAL,
            driver_rolling_quali_gap_to_pole REAL,
            weather_air_temp_c               REAL,
            weather_rainfall_mm              REAL,
            weather_wind_kph                 REAL,
            PRIMARY KEY (season, round, driver_id)
        )
        """
    )
    conn.execute("DELETE FROM qualifying_features")

    conn.execute(
        """
        INSERT INTO qualifying_features
        WITH
        -- TODO(team-table): once races/drivers gain a team_id column,
        -- replace this with a real team lookup. Today we treat each
        -- driver_id as its own team, which means the team- and driver-
        -- level rolling features collapse to the same number; the
        -- COALESCE chain still holds.
        _driver_team AS (
            SELECT DISTINCT driver_id AS team_key FROM qualifying_results
        ),
        -- 1) Per-round pole time. LEAST ignores NULLs in DuckDB; a driver
        -- who never set a time in any session produces NULL best_qual_time
        -- and is excluded from gap computations but kept in the final
        -- table (left joins surface NULL rolling values that the COALESCE
        -- chain then resolves).
        pole_times AS (
            SELECT
                    season, round,
                    MIN(LEAST(q1_time, q2_time, q3_time)) AS pole_time
            FROM qualifying_results
            GROUP BY season, round
        ),
        -- 2) Driver-level gap-to-pole per round, plus best session time
        -- and made-Q2/Q3 flags.
        gap AS (
            SELECT
                qr.season, qr.round, qr.driver_id,
                LEAST(qr.q1_time, qr.q2_time, qr.q3_time) AS best_qual_time,
                (qr.q3_time IS NOT NULL) AS made_q3,
                (qr.q2_time IS NOT NULL) AS made_q2,
                LEAST(qr.q1_time, qr.q2_time, qr.q3_time)
                    - pt.pole_time AS gap_to_pole
            FROM qualifying_results qr
            JOIN pole_times pt USING (season, round)
            WHERE LEAST(qr.q1_time, qr.q2_time, qr.q3_time) IS NOT NULL
        ),
        -- 3) Team-level rolling gap-to-pole. Window excludes the
        -- current row to avoid leaking the current-round gap into its
        -- own feature.
        -- /* keep in sync with _ROLLING_WINDOW = 5 */
        team_rolling AS (
            SELECT
                g.season, g.round, dt.team_key,
                AVG(g.gap_to_pole) OVER (
                    PARTITION BY dt.team_key
                    ORDER BY g.season, g.round
                    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
                ) AS team_rolling_quali_gap_to_pole_raw
            FROM gap g
            JOIN _driver_team dt ON dt.team_key = g.driver_id
        ),
        -- 4) Driver-level rolling gap-to-pole.
        driver_rolling AS (
            SELECT
                season, round, driver_id,
                AVG(gap_to_pole) OVER (
                    PARTITION BY driver_id
                    ORDER BY season, round
                    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
                ) AS driver_rolling_quali_gap_to_pole_raw
            FROM gap
        ),
        -- 5) Circuit-wide median gap-to-pole per round. The final-tier
        -- fallback for brand-new teams with no prior history.
        circuit_medians AS (
            SELECT season, round, AVG(gap_to_pole) AS circuit_median_gap
            FROM gap
            GROUP BY season, round
        ),
        -- 6) Per-(season, round) rookie count. Coarse proxy for grid
        -- unpredictability — explicitly NOT the model's own rank (that
        -- would leak the target).
        season_rookies AS (
            SELECT season, COUNT(*) AS n_rookies_this_season
            FROM driver_history
            WHERE is_rookie
            GROUP BY season
        )
        SELECT
            qr.season, qr.round, qr.driver_id,
            ra.circuit,
            dh.total_races_started,
            dh.months_since_last_race,
            dh.is_rookie,
            g.best_qual_time,
            g.made_q3,
            g.made_q2,
            COALESCE(sr.n_rookies_this_season, 0)
                AS circuit_quali_rank_pressure_proxy,
            COALESCE(tr.team_rolling_quali_gap_to_pole_raw,
                     cm.circuit_median_gap)
                AS team_rolling_quali_gap_to_pole,
            COALESCE(dr.driver_rolling_quali_gap_to_pole_raw,
                     tr.team_rolling_quali_gap_to_pole_raw,
                     cm.circuit_median_gap)
                AS driver_rolling_quali_gap_to_pole,
            w.air_temp_c   AS weather_air_temp_c,
            w.rainfall_mm  AS weather_rainfall_mm,
            w.wind_kph     AS weather_wind_kph
        FROM qualifying_results qr
        JOIN races            ra ON ra.season = qr.season
                               AND ra.round  = qr.round
        JOIN driver_history   dh ON dh.season = qr.season
                                AND dh.round  = qr.round
                                AND dh.driver_id = qr.driver_id
        LEFT JOIN gap              g  ON g.season    = qr.season
                                      AND g.round     = qr.round
                                      AND g.driver_id = qr.driver_id
        LEFT JOIN team_rolling     tr ON tr.season   = qr.season
                                      AND tr.round    = qr.round
                                      AND tr.team_key = qr.driver_id
        LEFT JOIN driver_rolling   dr ON dr.season   = qr.season
                                      AND dr.round    = qr.round
                                      AND dr.driver_id = qr.driver_id
        LEFT JOIN circuit_medians  cm ON cm.season   = qr.season
                                      AND cm.round    = qr.round
        LEFT JOIN season_rookies   sr ON sr.season   = qr.season
        LEFT JOIN weather          w  ON w.season    = qr.season
                                      AND w.round     = qr.round
        """
    )
    n = conn.execute("SELECT COUNT(*) FROM qualifying_features").fetchone()[0]
    return n


def build_race_result_features(conn: duckdb.DuckDBPyConnection) -> int:
    """Model B feature table.

    Single code path: ``grid_position`` is just a column here. Training
    reads the real value (joined from ``qualifying_results.grid_position``);
    inference overwrites the column in memory with Model A's prediction
    and hands the resulting DataFrame to Model B. No separate
    ``..._predicted`` table — that would fork the model code, which
    CLAUDE.md's "Tech constraints" forbids.

    DNF-rate classification: a status of ``'Lapped'`` or ``'+N Lap(s)'``
    is NOT a DNF (the car finished, just more than a lap down). Anything
    else with a non-Finished status (Retired, Accident, Mechanical,
    Withdrew, Illness, ...) IS a DNF and feeds ``*_dnf_rate``.

    Rookie/NULL handling mirrors ``build_qualifying_features``: every
    driver-level roll ``COALESCE``s to the team-level roll, which
    ``COALESCE``s to the circuit median.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS race_result_features (
            season                          INTEGER NOT NULL,
            round                           INTEGER NOT NULL,
            driver_id                       TEXT    NOT NULL,
            circuit                         TEXT    NOT NULL,
            grid_position                   INTEGER,
            total_races_started             INTEGER NOT NULL,
            months_since_last_race          REAL,
            is_rookie                       BOOLEAN NOT NULL,
            team_rolling_finish_vs_quali    REAL,
            driver_rolling_finish_vs_quali  REAL,
            team_rolling_dnf_rate           REAL,
            driver_rolling_dnf_rate         REAL,
            weather_air_temp_c              REAL,
            weather_rainfall_mm             REAL,
            weather_wind_kph                REAL,
            races_completed_this_season     INTEGER,
            PRIMARY KEY (season, round, driver_id)
        )
        """
    )
    conn.execute("DELETE FROM race_result_features")

    conn.execute(
        """
        INSERT INTO race_result_features
        WITH
        -- TODO(team-table): same swap-out point as in
        -- build_qualifying_features. See that function for context.
        _driver_team AS (
            SELECT DISTINCT driver_id AS team_key FROM qualifying_results
        ),
        -- 1) Per-result derived flags.
        --    - is_dnf: status NOT in ('Finished','Lapped') AND NOT
        --      '+N Lap(s)'. 'Lapped' drivers are classified finishers
        --      (finish_position is non-NULL); same for '+N Lap(s)'.
        --    - is_classified: a finish_position was recorded at all.
        --      Used by races_completed_this_season.
        --    - has_finish_vs_quali: both grid and finish are known, so
        --      the delta is meaningful.
        base AS (
            SELECT
                r.season, r.round, r.driver_id,
                r.grid_position, r.finish_position, r.status,
                (r.status IS DISTINCT FROM 'Finished'
                 AND r.status IS DISTINCT FROM 'Lapped'
                 AND NOT (r.status LIKE '+% Lap')) AS is_dnf,
                (r.finish_position IS NOT NULL) AS is_classified,
                (r.finish_position IS NOT NULL
                 AND r.grid_position IS NOT NULL) AS has_finish_vs_quali,
                (CAST(r.finish_position AS DOUBLE)
                 - CAST(r.grid_position AS DOUBLE)) AS finish_vs_quali
            FROM results r
            WHERE r.status IS DISTINCT FROM 'Did not start'
        ),
        -- 2) Team-level rolling finish-vs-quali.
        -- /* keep in sync with _ROLLING_WINDOW = 5 */
        team_roll_fvq AS (
            SELECT b.season, b.round, dt.team_key,
                AVG(b.finish_vs_quali) OVER (
                    PARTITION BY dt.team_key
                    ORDER BY b.season, b.round
                    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
                ) AS team_rolling_finish_vs_quali_raw
            FROM base b
            JOIN _driver_team dt ON dt.team_key = b.driver_id
            WHERE b.has_finish_vs_quali
        ),
        -- 3) Driver-level rolling finish-vs-quali.
        driver_roll_fvq AS (
            SELECT season, round, driver_id,
                AVG(finish_vs_quali) OVER (
                    PARTITION BY driver_id
                    ORDER BY season, round
                    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
                ) AS driver_rolling_finish_vs_quali_raw
            FROM base
            WHERE has_finish_vs_quali
        ),
        -- 4) Team-level rolling DNF rate.
        team_roll_dnf AS (
            SELECT b.season, b.round, dt.team_key,
                AVG(CAST(b.is_dnf AS DOUBLE)) OVER (
                    PARTITION BY dt.team_key
                    ORDER BY b.season, b.round
                    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
                ) AS team_rolling_dnf_rate_raw
            FROM base b
            JOIN _driver_team dt ON dt.team_key = b.driver_id
        ),
        -- 5) Driver-level rolling DNF rate.
        driver_roll_dnf AS (
            SELECT season, round, driver_id,
                AVG(CAST(is_dnf AS DOUBLE)) OVER (
                    PARTITION BY driver_id
                    ORDER BY season, round
                    ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
                ) AS driver_rolling_dnf_rate_raw
            FROM base
        ),
        -- 6) Circuit-wide fallbacks for both metrics.
        circuit_medians AS (
            SELECT season, round,
                AVG(finish_vs_quali)         AS cm_finish_vs_quali,
                AVG(CAST(is_dnf AS DOUBLE))  AS cm_dnf_rate
            FROM base
            GROUP BY season, round
        ),
        -- 7) Prior rounds in the current season the driver has
        --    classified a finish in (matches driver_history's "started"
        --    semantics — DNFs count as appearances but the metric
        --    tracks actually-classified finishes per the spec).
        season_count AS (
            SELECT season, round, driver_id,
                CAST(SUM(CASE WHEN is_classified THEN 1 ELSE 0 END) OVER (
                    PARTITION BY season, driver_id
                    ORDER BY round
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                ) AS INTEGER) AS races_completed_this_season
            FROM base
        )
        SELECT
            r.season, r.round, r.driver_id,
            ra.circuit,
            qr.grid_position,
            dh.total_races_started,
            dh.months_since_last_race,
            dh.is_rookie,
            COALESCE(tr_fvq.team_rolling_finish_vs_quali_raw,
                     cm.cm_finish_vs_quali)
                AS team_rolling_finish_vs_quali,
            COALESCE(dr_fvq.driver_rolling_finish_vs_quali_raw,
                     tr_fvq.team_rolling_finish_vs_quali_raw,
                     cm.cm_finish_vs_quali)
                AS driver_rolling_finish_vs_quali,
            COALESCE(tr_dnf.team_rolling_dnf_rate_raw,
                     cm.cm_dnf_rate)
                AS team_rolling_dnf_rate,
            COALESCE(dr_dnf.driver_rolling_dnf_rate_raw,
                     tr_dnf.team_rolling_dnf_rate_raw,
                     cm.cm_dnf_rate)
                AS driver_rolling_dnf_rate,
            w.air_temp_c   AS weather_air_temp_c,
            w.rainfall_mm  AS weather_rainfall_mm,
            w.wind_kph     AS weather_wind_kph,
            COALESCE(sc.races_completed_this_season, 0)
                AS races_completed_this_season
        FROM results r
        JOIN races            ra ON ra.season = r.season
                               AND ra.round  = r.round
        JOIN driver_history   dh ON dh.season = r.season
                                AND dh.round  = r.round
                                AND dh.driver_id = r.driver_id
        LEFT JOIN qualifying_results qr ON qr.season = r.season
                                       AND qr.round  = r.round
                                       AND qr.driver_id = r.driver_id
        LEFT JOIN team_roll_fvq    tr_fvq ON tr_fvq.season   = r.season
                                          AND tr_fvq.round    = r.round
                                          AND tr_fvq.team_key = r.driver_id
        LEFT JOIN driver_roll_fvq  dr_fvq ON dr_fvq.season   = r.season
                                          AND dr_fvq.round    = r.round
                                          AND dr_fvq.driver_id = r.driver_id
        LEFT JOIN team_roll_dnf    tr_dnf ON tr_dnf.season   = r.season
                                          AND tr_dnf.round    = r.round
                                          AND tr_dnf.team_key = r.driver_id
        LEFT JOIN driver_roll_dnf  dr_dnf ON dr_dnf.season   = r.season
                                          AND dr_dnf.round    = r.round
                                          AND dr_dnf.driver_id = r.driver_id
        LEFT JOIN circuit_medians  cm     ON cm.season = r.season
                                          AND cm.round  = r.round
        LEFT JOIN season_count     sc     ON sc.season  = r.season
                                          AND sc.round   = r.round
                                          AND sc.driver_id = r.driver_id
        LEFT JOIN weather          w      ON w.season   = r.season
                                          AND w.round    = r.round
        """
    )
    n = conn.execute("SELECT COUNT(*) FROM race_result_features").fetchone()[0]
    return n


def main() -> None:
    """Build all three feature tables in the live warehouse.

    Order matters: ``driver_history`` is built first because both
    feature tables join to it. The two feature builders are otherwise
    independent and could run in either order; we keep the spec's
    ordering for clarity.
    """
    conn = connect()
    try:
        n_dh = build_driver_history(conn)
        print(f"driver_history: {n_dh} rows")

        n_qf = build_qualifying_features(conn)
        print(f"qualifying_features: {n_qf} rows")

        n_rrf = build_race_result_features(conn)
        print(f"race_result_features: {n_rrf} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
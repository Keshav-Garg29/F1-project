-- DuckDB warehouse schema. Plain-SQL mirror of src/data/warehouse.py.
-- Keep in sync with any change to _SCHEMA_STATEMENTS there.
--
-- A human reads this file first; the Python module is the version
-- the application actually executes.
--
-- The three feature tables (driver_history, qualifying_features,
-- race_result_features) are owned by src/features/build_features.py
-- and are NOT mirrored here — they have no CREATE TABLE in
-- warehouse._SCHEMA_STATEMENTS by design.

CREATE TABLE IF NOT EXISTS races (
    season     INTEGER NOT NULL,
    round      INTEGER NOT NULL,
    circuit    TEXT    NOT NULL,
    race_date  DATE    NOT NULL,
    PRIMARY KEY (season, round)
);

CREATE TABLE IF NOT EXISTS drivers (
    driver_id   TEXT PRIMARY KEY,
    full_name   TEXT NOT NULL,
    nationality TEXT
);

CREATE TABLE IF NOT EXISTS results (
    season          INTEGER NOT NULL,
    round           INTEGER NOT NULL,
    driver_id       TEXT    NOT NULL,
    grid_position   INTEGER,
    finish_position INTEGER,
    status          TEXT,
    points          REAL,
    PRIMARY KEY (season, round, driver_id),
    FOREIGN KEY (season, round) REFERENCES races(season, round),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

CREATE TABLE IF NOT EXISTS qualifying_results (
    season        INTEGER NOT NULL,
    round         INTEGER NOT NULL,
    driver_id     TEXT    NOT NULL,
    q1_time       REAL,
    q2_time       REAL,
    q3_time       REAL,
    grid_position INTEGER,
    PRIMARY KEY (season, round, driver_id),
    FOREIGN KEY (season, round) REFERENCES races(season, round),
    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
);

CREATE TABLE IF NOT EXISTS weather (
    season       INTEGER NOT NULL,
    round        INTEGER NOT NULL,
    air_temp_c   REAL,
    track_temp_c REAL,
    humidity     REAL,
    rainfall_mm  REAL,
    wind_kph     REAL,
    PRIMARY KEY (season, round),
    FOREIGN KEY (season, round) REFERENCES races(season, round)
);

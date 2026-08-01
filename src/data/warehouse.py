"""DuckDB warehouse: connection factory + schema bootstrap.

The schema is the source of truth for the warehouse; ``sql/schema.sql``
is a plain-SQL mirror that must be kept in sync. We keep both because:

- ``warehouse.py`` defines the schema in code so tests and notebooks
  get a consistent view without reading a separate file
- ``sql/schema.sql`` is what a human reads when they want to know the
  shape of the warehouse, and is also the artefact a DBA would diff

Tables (one row per …):
- ``races``               … race weekend (season, round, circuit, date)
- ``drivers``             … driver identity and metadata
- ``results``             … historical finishing results per (driver, race)
- ``qualifying_results``  … historical qualifying per (driver, race)
- ``weather``             … historical + hypothetical weather per race
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.config.settings import SQL_DIR, WAREHOUSE_PATH

# DDL kept as a list of statements so the bootstrap can execute them
# sequentially. Order matters: foreign keys are declared on the child
# tables, so referenced tables must exist first.
_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS races (
        season     INTEGER NOT NULL,
        round      INTEGER NOT NULL,
        circuit    TEXT    NOT NULL,
        race_date  DATE    NOT NULL,
        PRIMARY KEY (season, round)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS drivers (
        driver_id   TEXT PRIMARY KEY,
        full_name   TEXT NOT NULL,
        nationality TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS results (
        season        INTEGER NOT NULL,
        round         INTEGER NOT NULL,
        driver_id     TEXT    NOT NULL,
        grid_position INTEGER,
        finish_position INTEGER,
        status        TEXT,
        points        REAL,
        PRIMARY KEY (season, round, driver_id),
        FOREIGN KEY (season, round) REFERENCES races(season, round),
        FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qualifying_results (
        season     INTEGER NOT NULL,
        round      INTEGER NOT NULL,
        driver_id  TEXT    NOT NULL,
        q1_time    REAL,
        q2_time    REAL,
        q3_time    REAL,
        grid_position INTEGER,
        PRIMARY KEY (season, round, driver_id),
        FOREIGN KEY (season, round) REFERENCES races(season, round),
        FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS weather (
        season        INTEGER NOT NULL,
        round         INTEGER NOT NULL,
        air_temp_c    REAL,
        track_temp_c  REAL,
        humidity      REAL,
        rainfall_mm   REAL,
        wind_kph      REAL,
        PRIMARY KEY (season, round),
        FOREIGN KEY (season, round) REFERENCES races(season, round)
    )
    """,
)


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open (or create) the warehouse file and return a live connection.

    The caller owns the connection — close it (or use as a context
    manager) when done. The bootstrap is idempotent so it's safe to
    call on every connect.
    """
    db_path = db_path or WAREHOUSE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    bootstrap_schema(conn)
    return conn


def bootstrap_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create tables if they don't exist. Idempotent."""
    for stmt in _SCHEMA_STATEMENTS:
        conn.execute(stmt)

"""Build the three feature tables consumed by training and inference.

Tables produced (all in DuckDB, all SQL-defined):

1. ``driver_history`` — shared experience/recency per (driver, race)
   (``total_races_started``, ``months_since_last_race``, ``is_rookie``)
2. ``qualifying_features`` — Model A inputs
3. ``race_result_features`` — Model B inputs (joins Model A's
   ``grid_position`` for inference; uses real ``grid_position`` at
   training time — one code path, see CLAUDE.md "Tech constraints")

All three are stubs today; the contract this module guarantees is
that downstream models can select from these table names and get
exactly the feature columns documented in ``train_*_model.py``.
"""

from __future__ import annotations

import duckdb

from src.data.warehouse import connect


def build_driver_history(conn: duckdb.DuckDBPyConnection) -> int:
    """Materialise the shared experience/recency feature block.

    Why a single function: both Model A and Model B depend on it, and
    duplicating the logic in two places is exactly what CLAUDE.md's
    "Where things belong" table warns against.
    """
    raise NotImplementedError("build_driver_history is a stub")


def build_qualifying_features(conn: duckdb.DuckDBPyConnection) -> int:
    """Model A feature table. Stub."""
    raise NotImplementedError("build_qualifying_features is a stub")


def build_race_result_features(conn: duckdb.DuckDBPyConnection) -> int:
    """Model B feature table. Stub."""
    raise NotImplementedError("build_race_result_features is a stub")


def main() -> None:
    conn = connect()
    try:
        build_driver_history(conn)
        build_qualifying_features(conn)
        build_race_result_features(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

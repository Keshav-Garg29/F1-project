"""Smoke tests for the warehouse bootstrap.

These tests pin the contract that ``connect()`` produces a working
schema, independent of any data being loaded. They pass against the
stubs because the schema is defined in code, not in a separate
migration.
"""

from __future__ import annotations

from src.data.warehouse import connect


def test_connect_creates_expected_tables() -> None:
    conn = connect()  # uses the default warehouse path
    try:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    finally:
        conn.close()
    assert {"races", "drivers", "results", "qualifying_results", "weather"} <= tables

"""Project-wide settings resolved at import time.

The interesting bit is ``get_target_seasons()`` — it returns every
season from a fixed start year (2018) through the latest fully-elapsed
season. We avoid hardcoding the end year so the pipeline keeps ingesting
new data without code changes.

Why a function and not a module constant: the "latest season" depends
on the current date, and we want callers to get a fresh range each
invocation (e.g. a CLI run in March shouldn't claim to ingest a season
that hasn't started yet).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List

# FastF1 / Ergast only have reliable data from 2018 onward for the
# fields we depend on (full qualifying telemetry, driver metadata).
SEASON_START_YEAR: int = 2018

# Project paths. Resolved relative to the repo root so the pipeline
# works regardless of the current working directory.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = REPO_ROOT / "data"
SQL_DIR: Path = REPO_ROOT / "sql"
ARTIFACTS_DIR: Path = REPO_ROOT / "models" / "artifacts"
WAREHOUSE_PATH: Path = DATA_DIR / "warehouse.duckdb"
FASTF1_CACHE_DIR: Path = DATA_DIR / "fastf1_cache"


def get_target_seasons(today: date | None = None) -> List[int]:
    """Return [2018, ..., latest fully-elapsed season] inclusive.

    A season is considered "fully elapsed" once we're past January of
    the *following* year — that's when pre-season testing and the
    first round are realistically in the books, but we still leave a
    month of slack for early-year ingestion.

    Args:
        today: Override the current date (useful in tests).

    Returns:
        Sorted ascending list of integer season years.
    """
    today = today or date.today()
    latest = today.year - 1 if today.month == 1 else today.year
    return list(range(SEASON_START_YEAR, latest + 1))

"""FastF1 ingestion — race results and qualifying results.

Two public functions, one per round:

- ``ingest_race(season, round_)`` — finishers, grid, status, points
- ``ingest_qualifying(season, round_)`` — Q1/Q2/Q3 times + grid slot

Each is a single round call so the pipeline can be resumed round-by-round
without re-downloading successful ingests. (Status: both are stubs.)
"""

from __future__ import annotations


def ingest_race(season: int, round_: int) -> int:
    """Ingest race results for one round into the warehouse.

    Returns the number of rows written so the caller can report progress
    and decide whether to retry.
    """
    raise NotImplementedError(
        "ingest_race is a stub — see CLAUDE.md 'Implemented vs stub'"
    )


def ingest_qualifying(season: int, round_: int) -> int:
    """Ingest qualifying results for one round into the warehouse.

    Why this is a separate call from ``ingest_race``: qualifying and
    race results are published at different times, and Model A depends
    on qualifying being available before we can build race features.
    """
    raise NotImplementedError(
        "ingest_qualifying is a stub — see CLAUDE.md 'Implemented vs stub'"
    )

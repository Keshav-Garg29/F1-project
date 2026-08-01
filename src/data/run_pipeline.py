"""Pipeline CLI — ingest every season from 2018 through the latest.

Run with ``python -m src.data.run_pipeline``. The default invocation
covers every season returned by ``get_target_seasons()``; a ``--season``
flag is intentionally not exposed in the common path (see CLAUDE.md).
"""

from __future__ import annotations

from src.config.settings import get_target_seasons
from src.data.fastf1_ingest import ingest_qualifying, ingest_race
from src.data.warehouse import connect
from src.data.weather_ingest import fetch_historical


def main() -> None:
    seasons = get_target_seasons()
    print(f"Ingesting {len(seasons)} seasons: {seasons[0]}–{seasons[-1]}")

    conn = connect()
    try:
        for season in seasons:
            for round_ in _iter_rounds(season):
                ingest_race(season, round_)
                ingest_qualifying(season, round_)
                fetch_historical(season, round_)
    finally:
        conn.close()


def _iter_rounds(season: int) -> range:
    """Placeholder: real implementation will query the FastF1 schedule.

    Hard-coding a range here would silently miss cancelled rounds and
    sprint-weekend reshuffles, so the real version defers to FastF1's
    session list per season.
    """
    raise NotImplementedError("_iter_rounds is a stub")


if __name__ == "__main__":
    main()

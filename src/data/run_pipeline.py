"""Pipeline CLI — ingest every season from 2018 through the latest.

Run with ``python -m src.data.run_pipeline``. The default invocation
covers every season returned by ``get_target_seasons()``; a ``--season``
flag is intentionally not exposed in the common path (see CLAUDE.md).

Exit codes:
  0 — every season/round ingested cleanly.
  1 — at least one round failed one or more ingest steps; a summary is
      printed to stdout.
"""

from __future__ import annotations

import logging
import sys
from typing import Iterable

import fastf1

from src.config.settings import FASTF1_CACHE_DIR, get_target_seasons
from src.data.fastf1_ingest import NETWORK_FAILURES as FASTF1_FAILURES
from src.data.fastf1_ingest import ingest_qualifying, ingest_race
from src.data.weather_ingest import NETWORK_FAILURES as WEATHER_FAILURES
from src.data.weather_ingest import fetch_historical

log = logging.getLogger(__name__)

# The full per-step failure net. ``Exception`` is intentionally last-resort:
# the spec's "Network failures are non-fatal per round" rule beats raising,
# and a single network blip should not abort the whole season range.
_FAILURE_NETS: tuple[type[BaseException], ...] = (
    *FASTF1_FAILURES,
    *WEATHER_FAILURES,
    Exception,
)


def _iter_rounds(season: int) -> list[int]:
    """Return race round numbers from FastF1's event schedule.

    Defers to FastF1 rather than hardcoding a range so that cancelled
    rounds and sprint-weekend reshuffles are reflected automatically.
    Testing rounds (``RoundNumber == 0``) are filtered out defensively,
    even though ``include_testing=False`` should already remove them.

    Returns an empty list if the schedule cannot be resolved (network
    down, invalid season); ``main()`` will then skip the season.
    """
    try:
        schedule = fastf1.get_event_schedule(season, include_testing=False)
    except Exception as exc:  # noqa: BLE001 — network boundary
        log.warning("season=%s: schedule fetch failed: %s", season, exc)
        return []
    if schedule is None or len(schedule) == 0:
        return []
    return [int(r) for r in schedule["RoundNumber"].tolist() if r and r > 0]


def _run_steps(season: int, round_: int) -> list[tuple[str, str]]:
    """Run the three ingest steps for a round, catching failures.

    Returns a list of ``(step_name, exception_type_name)`` tuples for
    any step that raised. Empty list means clean.
    """
    failures: list[tuple[str, str]] = []
    for step_name, step in (
        ("ingest_race", ingest_race),
        ("ingest_qualifying", ingest_qualifying),
        ("fetch_historical", fetch_historical),
    ):
        try:
            step(season, round_)
        except _FAILURE_NETS as exc:
            log.warning(
                "season=%s round=%s step=%s failed: %s",
                season, round_, step_name, exc,
                exc_info=True,
            )
            failures.append((step_name, type(exc).__name__))
    return failures


def main() -> int:
    """Walk 2018 through the latest fully-elapsed season, one round at a time.

    Per-round failures are non-fatal; the round list keeps going. ``main``
    returns ``0`` if every step of every round succeeded, otherwise ``1``
    with a summary printed to stdout.
    """
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR), use_requests_cache=False)

    seasons = get_target_seasons()
    print(f"Ingesting {len(seasons)} seasons: {seasons[0]}–{seasons[-1]}")

    failed_rounds: list[tuple[int, int, list[tuple[str, str]]]] = []
    for season in seasons:
        rounds = _iter_rounds(season)
        print(f"  season={season}: {len(rounds)} round(s)")
        for round_ in rounds:
            print(f"    season={season} round={round_}")
            failures = _run_steps(season, round_)
            if failures:
                failed_rounds.append((season, round_, failures))

    if failed_rounds:
        print(
            f"\n{sum(len(f) for _, _, f in failed_rounds)} step failure(s) "
            f"across {len(failed_rounds)} round(s):"
        )
        for season, round_, failures in failed_rounds:
            for step_name, exc_name in failures:
                print(f"  - season={season} round={round_} step={step_name} ({exc_name})")
        return 1

    print("\nAll rounds ingested cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

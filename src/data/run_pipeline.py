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

import argparse
import logging
import sys
import time
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

# Per-step retry config. Transient ``IOException`` (network blips) succeed
# on a second attempt; rate-limit errors do not and are skipped by the
# retry loop.
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 10


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

    Each step is retried up to ``_MAX_RETRIES`` times with a short sleep
    backoff — FastF1 / Open-Meteo both have transient ``IOException`` /
    ``RateLimitExceededError`` failures that succeed on second attempt.
    A ``RateLimitExceededError`` is **not** retried (waiting 10 s won't
    free up FastF1's hourly quota).

    Returns a list of ``(step_name, exception_type_name)`` tuples for
    any step that ultimately raised. Empty list means clean.
    """
    failures: list[tuple[str, str]] = []
    for step_name, step in (
        ("ingest_race", ingest_race),
        ("ingest_qualifying", ingest_qualifying),
        ("fetch_historical", fetch_historical),
    ):
        last_exc: BaseException | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                step(season, round_)
                last_exc = None
                break
            except _FAILURE_NETS as exc:
                last_exc = exc
                # Rate-limit errors won't unblock with a short sleep —
                # bail straightaway so the outer loop can move on.
                if isinstance(exc, FASTF1_FAILURES) and 'RateLimit' in type(exc).__name__:
                    log.warning(
                        "season=%s round=%s step=%s rate-limited (no retry): %s",
                        season, round_, step_name, exc,
                    )
                    break
                if attempt < _MAX_RETRIES:
                    log.info(
                        "season=%s round=%s step=%s attempt %d/%d failed (%s), retrying in %ds",
                        season, round_, step_name, attempt, _MAX_RETRIES,
                        type(exc).__name__, _RETRY_BACKOFF_SECONDS,
                    )
                    time.sleep(_RETRY_BACKOFF_SECONDS)
                else:
                    log.warning(
                        "season=%s round=%s step=%s failed after %d attempts: %s",
                        season, round_, step_name, _MAX_RETRIES, exc,
                        exc_info=True,
                    )
        if last_exc is not None:
            failures.append((step_name, type(last_exc).__name__))
    return failures


def main(seasons: list[int] | None = None) -> int:
    """Walk 2018 through the latest fully-elapsed season, one round at a time.

    Per-round failures are non-fatal; the round list keeps going. ``main``
    returns ``0`` if every step of every round succeeded, otherwise ``1``
    with a summary printed to stdout.

    Pass ``seasons=[2020, 2021, ...]`` to walk a subset — useful when
    splitting the backfill into chunks that fit inside one shell-timeout
    window without re-touching cached rounds.
    """
    FASTF1_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE_DIR), use_requests_cache=False)

    if seasons is None:
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        default=None,
        help="Subset of seasons to ingest (default: every season from get_target_seasons())",
    )
    args = parser.parse_args()
    sys.exit(main(seasons=args.seasons))

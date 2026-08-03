# Spec: Data Ingestion

## Overview
Data Ingestion is the first vertical slice of the Apex Analytics platform. It lands
all raw inputs the rest of the pipeline needs into the local DuckDB warehouse:
race results and qualifying results from FastF1, driver/constructor metadata, race
calendar metadata, and historical weather from Open-Meteo. It does not build
features, train models, or expose any `predict_*()` function — its sole output is
populated warehouse tables plus a runnable end-to-end CLI
(`python -m src.data.run_pipeline`) that walks 2018 through the latest fully-elapsed
season one round at a time. This is the foundation both Model A and Model B depend
on, and it must be correct and idempotent before any feature engineering or training
work can begin.

## Depends on
- `src/config/settings.py` — `get_target_seasons()`, `WAREHOUSE_PATH`, `FASTF1_CACHE_DIR`
- `src/data/warehouse.py` — `connect()`, `bootstrap_schema()` (already exist and are correct)
- `sql/schema.sql` — current 5-table mirror of `warehouse.py`
- Network access to FastF1 and Open-Meteo (CLAUDE.md explicitly warns these may not
  work in a sandbox)

## Data flow
- Input source(s):
  - **FastF1** — season schedule, session-level race results, session-level qualifying
    results, driver list per round. Cached on disk under `FASTF1_CACHE_DIR`
    (`data/fastf1_cache`) to avoid re-fetching.
  - **Open-Meteo Archive API** — historical hourly weather for the round's circuit
    coordinates on `race_date`, aggregated to per-round `air_temp_c`,
    `track_temp_c`, `humidity`, `rainfall_mm`, `wind_kph`.
- Output destination: existing DuckDB tables in `data/warehouse.duckdb`
  - `races` — one row per `(season, round)`; populated from FastF1 schedule
  - `drivers` — one row per unique `driver_id`; upserted from FastF1 driver lists
  - `results` — one row per `(season, round, driver_id)` race finisher/DNF
  - `qualifying_results` — one row per `(season, round, driver_id)` qualifying entry
  - `weather` — one row per `(season, round)` from Open-Meteo Archive

## Database changes
- **Schema:** No new tables. The current 5 tables in `warehouse.py`
  (`_SCHEMA_STATEMENTS`, lines 30–88) and their `sql/schema.sql` mirror are
  sufficient. Confirmed during research: each table has the columns this slice
  needs.
- **Gap to flag for a future spec — not addressed here:**
  - No `team_id` / `constructor` column anywhere. Car-performance signal will be
    derived from a rolling qualifying-gap-to-pole feature (CLAUDE.md rule), but the
    ingestion layer currently has nowhere to record per-`(season, round, driver)`
    team membership. A future slice can add either a `teams` table + FK on
    `results`/`qualifying_results`, or a `(season, round, driver_id, team_id)`
    `driver_team` table. Tracking this as a follow-up; do **not** expand scope here.
  - No `circuit_lat` / `circuit_lon` in `races.circuit`. `fetch_hypothetical()`
    needs coords; ingestion for this slice can hardcode a small `CIRCUIT_COORDS`
    dict in `weather_ingest.py` (covered in the "Future gap" caveat), or look
    coords up from FastF1's session metadata. Decide one approach during
    implementation; do not change the schema.
- `sql/schema.sql` requires no edits for this slice (no schema changes).

## Features
- **No new features.** This slice does not touch `build_features.py`, the
  `driver_history` block, `qualifying_features`, or `race_result_features`. Those
  are downstream stubs and out of scope.

## Model impact
- **Not applicable.** No features are added and no model is trained. Both Model A
  and Model B remain stubs after this slice.

## Frontend changes
- **No frontend changes.** `streamlit_app.py`, `components.py`, and `styles.py`
  are not touched. No new `predict_*()` function is exposed by this slice.

## Files to change
- `src/data/fastf1_ingest.py` — implement `ingest_race()` and `ingest_qualifying()`
  (currently `raise NotImplementedError`).
- `src/data/weather_ingest.py` — implement `fetch_historical()` and
  `fetch_hypothetical()` (currently `raise NotImplementedError`).
- `src/data/run_pipeline.py` — implement `_iter_rounds()` to source the round
  list from FastF1's schedule per season (never hardcode a range — CLAUDE.md
  explicitly warns about cancelled rounds and sprint reshuffles); review the
  call order in `main()`.
- `tests/test_warehouse.py` (or a new test module) — add coverage for the
  ingestion functions and `_iter_rounds()`. See "Definition of done".
- `requirements.txt` — populate with the packages this slice needs (currently
  empty). See "New dependencies".
- `.gitignore` — **create** at repo root (none exists yet) with at minimum
  `data/fastf1_cache/` and `__pycache__/` so the FastF1 cache and Python
  bytecode don't get committed. The already-shipped `__pycache__` files and
  `data/warehouse.duckdb` were committed by mistake in the initial scaffolding
  — leave them; do not rewrite history in this slice.

## Files to create
- None. All target files already exist as stubs or skeletons.

## New dependencies
CLAUDE.md requires explicit flagging. This slice introduces the platform's first
real dependencies, so each one is named here for review **before** implementation:
- **`fastf1`** — FastF1's Python API for pulling schedules, session results, and
  driver lists. Required for `ingest_race`, `ingest_qualifying`, and
  `_iter_rounds`.
- **`requests`** — HTTP client for the Open-Meteo Archive API in
  `fetch_historical()`. (Lightweight; FastF1 also depends transitively, but
  importing it directly is clearer than relying on a transitive import.)
- **`pandas`** — for the glue between FastF1's session DataFrames and the
  parameterized DuckDB inserts. CLAUDE.md allows pandas only as glue.
- **`duckdb`** — already implicitly required by `warehouse.py`; adding it
  explicitly to `requirements.txt` for clarity.
- **Dev:** `pytest` — for the new ingestion tests.

**No Postgres, no ORM, no deep-learning frameworks, no Streamlit changes** — all
consistent with CLAUDE.md's tech constraints.

## Rules for implementation
- **DuckDB only** — no Postgres, no ORM.
- **LightGBM only** for both models — no deep learning on this tabular data.
- **SQL first for feature engineering** (window functions, CTEs); pandas only for
  glue code. (This slice writes very little SQL — only parameterized `INSERT`
  statements — but the same rule applies downstream.)
- **Parameterized `?` placeholders** — never f-strings in SQL. Every
  `conn.execute("INSERT ... VALUES (?, ?, ?)", [...])` call must use a parameter
  list, never an f-string or `.format()`.
- **Idempotency** — `ingest_race(season, round_)`, `ingest_qualifying(season, round_)`,
  and `fetch_historical(season, round_)` must be safe to re-run. Use
  `INSERT ... ON CONFLICT (season, round, driver_id) DO UPDATE SET ...` (or
  equivalent `DELETE` + `INSERT` inside a single transaction) so that resume
  after a partial failure does not double-write rows. `drivers` upserts must
  preserve `driver_id` as the natural key.
- **Never hardcode a round range.** `_iter_rounds(season)` must defer to
  FastF1's session list for that season. Hardcoding a range would silently
  miss cancelled rounds and sprint-weekend reshuffles.
- **FastF1 cache is mandatory.** Every FastF1 session load must use
  `fastf1.Cache.enable_cache(FASTF1_CACHE_DIR)`, set once in `run_pipeline.main`
  before any ingest call. Re-using cached sessions keeps re-runs fast and
  network-resilient.
- **Driver upsert strategy.** FastF1 emits a fresh `Driver` object per session;
  use the stable `Driver.abbreviation` (or `Driver.driverId`) as `driver_id`
  and upsert `full_name` / `nationality`. Do not invent IDs.
- **Weather coordinates.** `fetch_historical` needs lat/lon per round. Either
  (a) extend `weather_ingest.py` with a small hardcoded `CIRCUIT_COORDS` dict
  keyed by `(season, round)` or circuit name, or (b) read coords from the
  FastF1 session's `session.event.Location`. **Prefer (b)** — it stays
  data-driven, matches the "never hardcode" rule, and avoids drift if a
  circuit changes. Implementation may use (a) as a fallback if (b) yields
  nothing.
- **Network failures are non-fatal per round.** A single round failing
  FastF1 or Open-Meteo must log a warning and let the pipeline continue to
  the next round. The CLI should exit non-zero at the end with a summary of
  failed rounds, but not abort mid-run.
- **No new pip packages beyond those listed under "New dependencies"** without
  asking first.
- **Docstrings explain *why*, not just what** — every function added in this
  slice needs a docstring that captures rationale (e.g. why qualifying is
  ingested separately, why `ON CONFLICT` is used, why FastF1 cache is enabled
  at startup).

## Definition of done
A specific testable checklist. Each item must be verifiable by running the
relevant command:

- [ ] `pip install -r requirements.txt` succeeds on a fresh venv.
- [ ] `python -m src.data.run_pipeline` runs end-to-end against a real network
      (or a recorded FastF1 cache) for at least one round in a test season
      without raising.
- [ ] After the pipeline runs, `duckdb data/warehouse.duckdb` shows
      non-empty `races`, `drivers`, `results`, `qualifying_results`, and
      `weather` tables for the ingested season.
- [ ] Re-running `ingest_race(season, round_)` for the same round does **not**
      double-write — row count is unchanged (idempotency).
- [ ] `_iter_rounds(season)` returns exactly the rounds FastF1 has on file
      for that season, including any sprint-weekend reshuffles (verified by
      comparing to `fastf1.get_event_schedule(season)`).
- [ ] `fetch_historical(season, round_)` writes one row per round into
      `weather` with non-null `air_temp_c` and `rainfall_mm` for at least one
      historical round.
- [ ] `pytest tests/` passes, including new tests covering:
      - `ingest_race` / `ingest_qualifying` happy path against a recorded
        FastF1 session (use a tiny fixture or `fastf1.Cache` replay).
      - Idempotency: calling `ingest_race` twice does not change row counts.
      - `_iter_rounds` returns the expected set of rounds for a known season
        (mock the FastF1 schedule to avoid network in CI).
- [ ] `sql/schema.sql` is unchanged (still in sync with `warehouse.py` — no
      schema edits were required).
- [ ] No `__pycache__` or `data/fastf1_cache/` files added to git
      (verify with `git status` after a run).
- [ ] The "Implemented vs stub" table in `CLAUDE.md` can be updated:
      `ingest_race()` and `ingest_qualifying()` move from "Stub" to
      "Implemented" (or are removed from the stub list). `fetch_historical`
      and `_iter_rounds` get the same treatment.

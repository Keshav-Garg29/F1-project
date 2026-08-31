# Spec: Build Features

## Overview
Build Features is the second vertical slice of Apex Analytics, sitting directly between
Data Ingestion and Model Training. It materialises three feature tables inside the
existing DuckDB warehouse — `driver_history` (shared experience/recency block),
`qualifying_features` (Model A inputs), and `race_result_features` (Model B inputs).
The output of this slice is the contract that downstream training scripts and the
Streamlit app consume; once it lands, Model A and Model B have a stable feature
surface to read from. All feature engineering is SQL-first (CTEs and window
functions); Python is glue only. This slice produces no new warehouse tables — it
materialises *feature* tables that join the existing raw tables — and trains no
models.

## Depends on
- **Data Ingestion slice** (now merged into `main`): `races`, `drivers`, `results`,
  `qualifying_results`, `weather` tables must be populated. The slice does not
  require that every season is ingested, only that any `(season, round)` present
  in a feature row has corresponding rows in the raw tables.
- `src/data/warehouse.py` — `connect()` and `bootstrap_schema()`
- `src/config/settings.py` — `WAREHOUSE_PATH`, `SEASON_START_YEAR` (no new paths
  required; feature tables live in the same `data/warehouse.duckdb`)
- FastF1/Open-Meteo ingestion already cached on disk under `data/fastf1_cache/`

## Data flow
- Input source(s): existing DuckDB tables only — `races`, `drivers`, `results`,
  `qualifying_results`, `weather`. No new external calls. No new network I/O.
- Output destination: three new feature tables in the same DuckDB file:
  - `driver_history` — one row per `(driver_id, season, round)` for every driver
    who has started a race in `results`
  - `qualifying_features` — one row per `(driver_id, season, round)` where a
    qualifying entry exists
  - `race_result_features` — one row per `(driver_id, season, round)` where a
    race result exists; intended to carry a `grid_position` column that is
    **real during training** and **Model-A-predicted during inference** (see
    "Model impact").

## Database changes
- **No new tables.** Feature engineering writes into the same DuckDB file via
  `connect()`; the three feature tables are created by this slice in
  `build_features.py` itself using `CREATE TABLE IF NOT EXISTS`, mirroring the
  pattern already used by `warehouse.bootstrap_schema()`.
- The three new feature tables (`driver_history`, `qualifying_features`,
  `race_result_features`) are *not* added to `warehouse._SCHEMA_STATEMENTS` —
  they are owned by this slice. The `sql/schema.sql` mirror therefore needs no
  edits either; the comment header at the top of that file should be updated
  to point readers to `build_features.py` for the feature tables.
- No raw-table column additions. The known gap from the data-ingestion spec
  (no `team_id`/`constructor` column anywhere) is addressed here by deriving
  car-performance signal from a **rolling, data-driven feature** (see
  "Features") — never by adding a hardcoded per-team number and never by
  altering the raw schema.

## Features
The three feature tables are produced from SQL against the existing warehouse
tables. Each feature is justified below.

### `driver_history` — shared experience/recency block
One row per `(driver_id, season, round)`. Built once; both feature tables join
to it. Columns:

| Column | Type | Definition |
|---|---|---|
| `season` | INTEGER | FK to `races` |
| `round` | INTEGER | FK to `races` |
| `driver_id` | TEXT | FK to `drivers` |
| `total_races_started` | INTEGER | Career race starts up to *but not including* this `(season, round)` — a running count from `results` |
| `months_since_last_race` | REAL | Months between this race date and the driver's previous race date (NULL if this is the driver's first ever race) |
| `is_rookie` | BOOLEAN | TRUE iff `total_races_started == 0` |

**Why two columns for experience and recency:** CLAUDE.md explicitly forbids
collapsing them into one number — a returning driver after a long layoff must
look different from a continuously active driver with the same career race
count. `total_races_started` captures career volume; `months_since_last_race`
captures freshness.

**Rookie/NULL handling:** `months_since_last_race` is NULL for rookies
(`is_rookie = TRUE`). Downstream consumers must treat NULL as a rookie signal
rather than imputing a value. `total_races_started` is never NULL — it is `0`
for rookies. No `COALESCE` fallback is needed at this layer because nothing is
rolled up to a higher level here.

### `qualifying_features` — Model A inputs
One row per `(driver_id, season, round)` where a `qualifying_results` row
exists. Columns:

| Column | Type | Source |
|---|---|---|
| `season` | INTEGER | join key |
| `round` | INTEGER | join key |
| `driver_id` | TEXT | join key |
| `circuit` | TEXT | `races.circuit` |
| `driver_history.*` | — | joined from `driver_history` (`total_races_started`, `months_since_last_race`, `is_rookie`) |
| `best_qual_time` | REAL | `LEAST(q1_time, q2_time, q3_time)` ignoring NULLs (best session time the driver actually set) |
| `made_q3` | BOOLEAN | TRUE iff `q3_time IS NOT NULL` |
| `made_q2` | BOOLEAN | TRUE iff `q2_time IS NOT NULL` |
| `circuit_quali_rank_pressure_proxy` | INTEGER | Count of drivers on this circuit/season with `is_rookie = TRUE` — a coarse proxy for how unpredictable the grid is (not the model's own rank, which would leak the target) |
| `team_rolling_quali_gap_to_pole` | REAL | **The car-performance signal** — derived from real qualifying gap-to-pole data, **never hardcoded**. See "Car-performance signal" below. |
| `driver_rolling_quali_gap_to_pole` | REAL | Same metric at driver level; `COALESCE`s to the team value for rookies |
| `home_race` | BOOLEAN | TRUE iff the driver's `drivers.nationality` matches the circuit's host country (best-effort: country inferred from circuit name; NULL nationalities → FALSE) |
| `weather_air_temp_c` | REAL | joined from `weather` |
| `weather_rainfall_mm` | REAL | joined from `weather` |
| `weather_wind_kph` | REAL | joined from `weather` |

**Target leak guard:** `grid_position` is **never** a column on
`qualifying_features`. The downstream training script
(`train_qualifying_model.py`) will assert this at load time.

**Car-performance signal (CLAUDE.md "Where things belong" rule):** A rolling
feature computed from real qualifying gap-to-pole data over the prior *N*
rounds (N to be decided in implementation, default 5), keyed at the
*team-level* (since the raw schema has no team_id, the team is the
`qualifying_results` row's `driver_id` for now — see "Risks" below). The gap
is `(driver_best_qual_time − circuit_pole_time)`. This is a rolling, data-
driven number — never a hardcoded per-team strength score.

**Rookie/NULL handling:**
- `team_rolling_quali_gap_to_pole` is never NULL for any driver who has
  qualified before; for a brand-new team's first round it `COALESCE`s to the
  circuit median across all drivers.
- `driver_rolling_quali_gap_to_pole` `COALESCE`s to the team-level value when
  the driver has fewer than N prior rounds (rookies, returning drivers). This
  is the explicit rookie-fallback CLAUDE.md mandates.

### `race_result_features` — Model B inputs
One row per `(driver_id, season, round)` where a `results` row exists.
Columns:

| Column | Type | Source |
|---|---|---|
| `season` | INTEGER | join key |
| `round` | INTEGER | join key |
| `driver_id` | TEXT | join key |
| `circuit` | TEXT | `races.circuit` |
| `grid_position` | INTEGER | **The chain column.** Real at training time (joined from `qualifying_results.grid_position`); predicted at inference time (overwritten in memory by Model A's output before Model B sees it). Persisted as the real value; inference does not write back. |
| `driver_history.*` | — | joined from `driver_history` |
| `team_rolling_finish_vs_quali` | REAL | Rolling mean of `(finish_position − grid_position)` for prior rounds — measures how well the car converts grid to finishes |
| `driver_rolling_finish_vs_quali` | REAL | Same at driver level; `COALESCE`s to team-level for rookies |
| `team_rolling_dnf_rate` | REAL | Rolling share of `results.status != 'Finished'` (and not classified as `+N Laps`) |
| `driver_rolling_dnf_rate` | REAL | Same at driver level; `COALESCE`s to team-level |
| `weather_air_temp_c` | REAL | joined from `weather` |
| `weather_rainfall_mm` | REAL | joined from `weather` |
| `weather_wind_kph` | REAL | joined from `weather` |
| `races_completed_this_season` | INTEGER | Count of prior rounds in the current season the driver has started |

**Single code path preserved:** `grid_position` is just a column on this
feature table. At training time, the column holds the real value. At
inference time, the Streamlit app loads `race_result_features` for the
scenario round, overwrites `grid_position` in memory with Model A's
prediction, and hands the resulting DataFrame to Model B. No separate
feature table, no fork in the model.

**Rookie/NULL handling:**
- All four `*_rolling_*` features follow the same `COALESCE` discipline as
  qualifying features — driver-level rolls fall back to team-level rolls,
  which fall back to the circuit median for brand-new teams.
- `months_since_last_race` is NULL for rookies; this is preserved through the
  join.

## Model impact
- **Affects Model A and Model B**, since both consume one of the two feature
  tables produced here. Model A consumes `qualifying_features`; Model B
  consumes `race_result_features`. Both will need to read these tables in the
  *next* slice, but no model-training code changes are in scope here.
- **Target-leak guard (Model A):** `grid_position` is *not* a column on
  `qualifying_features`. Training-time enforcement remains Model A's
  responsibility (it already asserts this in its docstring), but this slice
  guarantees the contract by omitting the column at the source.
- **Model B's single code path is preserved:** `race_result_features` exposes
  a `grid_position` column. Training reads the real value from
  `qualifying_results`; inference reads Model A's prediction by overwriting
  that column in memory. There is no parallel `race_result_features_predicted`
  table.
- **Baseline reporting** is *not* introduced in this slice — it's a model
  concern. The slice only prepares the data the baselines will be computed
  against (e.g. prior-grid-position mean as the naive Model B baseline).

## Frontend changes
- **No frontend changes.** `streamlit_app.py`, `components.py`, and `styles.py`
  remain stubs. The Streamlit app consumes these feature tables *after*
  Model A/B are wired up; that is a separate slice. This slice only changes
  `build_features.py` and tests.

## Files to change
- `src/features/build_features.py` — implement `build_driver_history`,
  `build_qualifying_features`, `build_race_result_features`. Each function:
  (a) `CREATE TABLE IF NOT EXISTS <table> (...)`, (b) build the table from
  SQL (CTEs and window functions), (c) `INSERT INTO <table>` from the CTE,
  (d) return row count. `main()` already calls all three in order — keep
  that order so `driver_history` exists before the two feature tables join
  to it.
- `CLAUDE.md` — flip the "Implemented vs stub" entries:
  `driver_history`, `qualifying_features`, `race_result_features` move from
  "Stub" to "Implemented" (or are removed from the stub list, mirroring how
  the ingestion slice was unflagged).
- `sql/schema.sql` — update only the comment header to note that the file
  remains the mirror of `warehouse.py` only, and that the three feature
  tables are owned by `build_features.py`. No DDL changes.
- `tests/test_build_features.py` — **create** (see "Files to create").

## Files to create
- `tests/test_build_features.py` — pytest module covering:
  - `build_driver_history` produces rows for every driver with a `results`
    entry; `is_rookie` is TRUE exactly for first-career-race drivers;
    `months_since_last_race` is NULL for rookies.
  - `build_qualifying_features` excludes `grid_position` (target-leak
    guard); populates `driver_rolling_quali_gap_to_pole` from the team
    value for a synthetic rookie; `is_rookie` propagates from
    `driver_history`.
  - `build_race_result_features` includes `grid_position` (Model B needs
    it); team-level rolling features fall back to circuit medians for a
    synthetic brand-new team; rookie driver-level rolls fall back to the
    team-level value.
  - Re-running the slice is idempotent (no row-count growth on re-run).

## New dependencies
- **No new dependencies.** All required packages (`duckdb`) are already in
  `requirements.txt`. Per CLAUDE.md, no new pip packages without explicit
  flagging; none are needed here. If implementation reveals a need
  (e.g. `numpy` for some glue), surface it for approval before adding.

## Rules for implementation
- **DuckDB only** — no Postgres, no ORM. Use `conn.execute()` with the same
  `connect()` helper used by `warehouse.py`.
- **SQL first.** All rolling windows, joins, fallbacks, and aggregations
  belong in CTEs. Python is for the `connect()`/`CREATE TABLE`/final
  `INSERT … FROM <cte>` glue only.
- **Parameterized `?` placeholders** — never f-strings in SQL. If user-
  configurable parameters ever enter the picture, use `?`. For now, the SQL
  is static, but no f-string substitution into SQL is allowed.
- **Never give Model A real `grid_position` as a feature.** `grid_position`
  must not appear in `qualifying_features`. Model B is allowed to have it
  (it needs it).
- **Never collapse experience and recency.** `total_races_started` and
  `months_since_last_race` stay separate.
- **Never hardcode a team or driver strength score.** The car-performance
  signal is a rolling feature computed from real data; the team identifier
  comes from the warehouse (currently the `qualifying_results.driver_id`,
  pending the team-table follow-up — see "Risks").
- **Every driver-level rolling feature must `COALESCE` to a team-level
  fallback** for rookies. Team-level rolls fall back to the circuit median
  when there is no team history yet.
- **Idempotency.** Each `build_*` function must be safe to re-run. Use
  `CREATE TABLE IF NOT EXISTS` + `INSERT INTO … SELECT … FROM <cte>` after
  truncating the table, or `DELETE FROM <table>` + insert, so re-running
  doesn't grow row counts.
- **Docstrings explain *why*, not just what** — every public function and
  every rolling window needs a docstring capturing rationale (why this
  feature, why this fallback, why this rolling window size).
- **No new pip packages** without explicit approval.

## Definition of done
A specific testable checklist. Each item must be verifiable by running the
relevant command:

- [ ] `python -m src.features.build_features` runs end-to-end against the
      merged `main` warehouse without raising.
- [ ] After the run, `duckdb data/warehouse.duckdb` shows three new tables:
      `driver_history`, `qualifying_features`, `race_result_features`,
      each non-empty for at least the 2018 season.
- [ ] `driver_history.is_rookie` is TRUE exactly for drivers on their first
      career race; `months_since_last_race` is NULL for those rows.
- [ ] `SELECT column_name FROM duckdb_columns() WHERE table_name =
      'qualifying_features'` does **not** include `grid_position`
      (target-leak guard).
- [ ] `SELECT column_name FROM duckdb_columns() WHERE table_name =
      'race_result_features'` **does** include `grid_position`
      (Model B needs it).
- [ ] All four `*_rolling_*` features on `qualifying_features` and
      `race_result_features` are non-NULL for every row — the
      `COALESCE` discipline holds (spot-check by running a COUNT of NULLs
      per column and confirming zero).
- [ ] Re-running `python -m src.features.build_features` leaves row counts
      unchanged in all three feature tables (idempotency).
- [ ] `pytest tests/test_build_features.py` passes, covering the bullets
      listed under "Files to create".
- [ ] `pytest tests/` (entire suite) still passes — `test_warehouse.py`
      and `test_data_ingest.py` are unaffected.
- [ ] `sql/schema.sql` still matches `warehouse._SCHEMA_STATEMENTS`
      (only the header comment was updated).
- [ ] CLAUDE.md's "Implemented vs stub" table reflects the new state:
      `driver_history`, `qualifying_features`, `race_result_features`
      no longer listed as stubs.
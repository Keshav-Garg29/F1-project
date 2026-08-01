# Apex Analytics

Apex Analytics predicts Formula 1 race results by chaining two machine learning
models: **Model A** predicts qualifying/grid position, and **Model B** predicts
finishing position using Model A's output as an input feature. Historical data is
sourced from [FastF1](https://docs.fastf1.dev/), covering the 2018 season through
the latest available round. An interactive Streamlit app runs a hypothetical
race scenario through both models end to end.

This is the first complete vertical slice of a larger race-strategy platform.
See [Roadmap](#roadmap) for what's planned beyond this slice.

> **Status:** early development. See [Implemented vs. stub](#implemented-vs-stub)
> below for what currently works.

---

## Table of contents

- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Implemented vs. stub](#implemented-vs-stub)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Data model](#data-model)
- [Development](#development)
- [Testing](#testing)
- [Design principles](#design-principles)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## How it works

```
                 ┌──────────────┐        ┌──────────────┐
  Race weekend →  │   Model A    │  grid  │   Model B    │ → predicted
  scenario input  │ (qualifying) │ ─────► │ (race result)│    finishing order
                 └──────────────┘ position└──────────────┘
```

1. **Ingest** historical race, qualifying, and weather data from FastF1 and
   Open-Meteo into a local DuckDB warehouse.
2. **Build features** — a shared `driver_history` block (experience/recency)
   feeds two downstream feature tables: `qualifying_features` for Model A and
   `race_result_features` for Model B.
3. **Train Model A** (LightGBM) to predict grid position from qualifying-stage
   features only — no leakage of the actual result.
4. **Train Model B** (LightGBM) to predict finishing position, using either the
   *real* historical grid position (training) or *Model A's predicted* grid
   position (future-scenario inference) — a single code path handles both.
5. **Serve** predictions through a Streamlit app: enter a hypothetical scenario
   (season, round, weather, driver lineup), and see the predicted qualifying
   order flow into a predicted race result.

---

## Architecture

```
f1-strategy-intel/
├── src/
│   ├── config/
│   │   └── settings.py          # get_target_seasons() resolves 2018→latest dynamically
│   ├── data/
│   │   ├── fastf1_ingest.py     # ingest_race() + ingest_qualifying(), one call per round
│   │   ├── weather_ingest.py    # historical + hypothetical weather via Open-Meteo
│   │   ├── warehouse.py         # DuckDB schema: races, drivers, results,
│   │   │                        #   qualifying_results, weather
│   │   └── run_pipeline.py      # CLI, defaults to 2018→latest, no season flag needed
│   ├── features/
│   │   └── build_features.py    # driver_history (shared experience/recency) →
│   │                            #   qualifying_features (Model A), race_result_features (Model B)
│   ├── models/
│   │   ├── train_qualifying_model.py   # Model A
│   │   ├── train_race_result_model.py  # Model B — accepts real or predicted grid position
│   │   └── evaluate.py                  # backtesting vs. actual historical outcomes
│   └── app/
│       ├── streamlit_app.py     # scenario in → Model A → Model B → predicted result out
│       ├── styles.py            # design tokens for the frontend
│       └── components.py        # chart components (qualifying order, race result)
├── notebooks/
│   └── 01_eda.py                # jupytext percent-format EDA / SQL findings
├── sql/schema.sql               # plain-SQL mirror of warehouse.py — keep in sync
├── data/                        # local DuckDB warehouse file(s)
├── models/artifacts/            # trained LightGBM model artifacts
├── tests/                       # unit and integration tests
└── requirements.txt
```

**Where things belong:**

| Concern | Lives in |
|---|---|
| Experience/recency logic (`total_races_started`, `months_since_last_race`, `is_rookie`) | The shared `driver_history` block in `build_features.py` **only** — both feature tables join to it rather than duplicating the logic |
| Grid-position prediction | `train_qualifying_model.py` **only**. Model A must never receive real grid position as a feature — that's the value it predicts |
| Car-performance signal | A rolling feature computed from real qualifying gap-to-pole data — never a hardcoded per-team number |

---

## Implemented vs. stub

| Component | Status |
|---|---|
| `ingest_qualifying()` | Stub |
| `driver_history` (experience/recency) | Stub |
| `qualifying_features` | Stub |
| `race_result_features` | Stub |
| `train_qualifying_model.py` (Model A) | Stub |
| `train_race_result_model.py` (Model B, chained on Model A) | Stub |
| Frontend: scenario → A → B → result | Stub |

---

## Requirements

- Python 3.10+
- Network access to `fastf1` (which fetches from the FIA/Ergast-style sources)
  and Open-Meteo — **not available in fully sandboxed/offline environments**
- ~2 GB disk space for cached FastF1 session data and the DuckDB warehouse

---

## Installation

```bash
git clone <repo-url> f1-strategy-intel
cd f1-strategy-intel

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

No new pip packages should be added without flagging it first — see
[Design principles](#design-principles).

---

## Usage

Run each stage of the pipeline in order:

```bash
# 1. Ingest historical race, qualifying, and weather data (2018 → latest season)
python -m src.data.run_pipeline

# 2. Build feature tables (driver_history, qualifying_features, race_result_features)
python -m src.features.build_features

# 3. Train Model A — grid position prediction
python -m src.models.train_qualifying_model

# 4. Train Model B — finishing position prediction, chained on Model A
python -m src.models.train_race_result_model

# 5. Launch the interactive app
streamlit run src/app/streamlit_app.py
```

`run_pipeline.py` defaults to ingesting every season from 2018 through the
latest available — no `--season` flag is required for the common case.

---

## Configuration

Season range and other environment-level settings are resolved dynamically in
`src/config/settings.py` via `get_target_seasons()`, rather than hardcoded.
Check that file for the current set of configurable options (e.g. DuckDB file
location, cache directory for FastF1 sessions).

---

## Project structure

See [Architecture](#architecture) above for the full directory tree and a
description of where each concern lives.

---

## Data model

The DuckDB warehouse (`src/data/warehouse.py`, mirrored in `sql/schema.sql`)
holds:

- **`races`** — one row per race weekend (season, round, circuit, date)
- **`drivers`** — driver identity and metadata
- **`results`** — historical finishing results per driver per race
- **`qualifying_results`** — historical qualifying/grid position per driver per race
- **`weather`** — historical and hypothetical weather conditions (via Open-Meteo)

Feature tables are built on top of this warehouse:

- **`driver_history`** — shared experience/recency features (career race count,
  months since last race, rookie flag), joined into both downstream tables
- **`qualifying_features`** — inputs to Model A
- **`race_result_features`** — inputs to Model B (includes grid position, real
  or predicted)

`sql/schema.sql` is a plain-SQL mirror of `warehouse.py` and **must be kept in
sync** with any schema change.

---

## Development

### Code style

- Python, PEP 8, `snake_case`
- Feature engineering is SQL-first — window functions and CTEs in SQL, with
  pandas reserved for glue code only
- Every model reports a naive baseline next to its own metric — never accuracy
  in isolation
- Database queries use parameterized `?` placeholders — never f-strings in SQL
- Docstrings explain **why**, not just what

### Tech constraints

- **DuckDB only** — no Postgres, no ORM
- **LightGBM only** for both models — no deep learning on this tabular data
- **Streamlit only** for the frontend
- Model B must handle a real historical grid position (training) and a
  predicted one from Model A (inference) through **one code path**, not a fork
- Any driver-level rolling feature must `COALESCE` to a team-level fallback for
  rookies — never leave `NULL` or silently drop the row
- New pip packages require flagging before they're added

---

## Testing

```bash
pytest
```

Model evaluation (backtesting against actual historical outcomes) is handled
separately by `src/models/evaluate.py`.

---

## Design principles

These are hard constraints for anyone extending this codebase:

- **Never** train Model A with grid position as a feature — this is a direct
  target leak
- **Never** collapse experience and recency into a single number — a returning
  driver after a long gap must look different from a continuously active driver
  with the same career race count
- **Never** hardcode a team or driver strength score — always derive it from a
  rolling, data-driven feature
- Keep `sql/schema.sql` in sync with any `warehouse.py` change
- FastF1 and Open-Meteo require real network access — don't assume they work in
  a sandboxed environment

---

## Roadmap

This is intentionally the first complete vertical slice, not the final scope.
The architecture is designed to extend without restructuring:

- **New models** live as new files under `src/models/`, following the same
  one-file-per-prediction-target pattern as Model A/B, each with its own
  feature table in `build_features.py`
- **New data sources** get their own ingestion file under `src/data/`, landing
  into new warehouse tables rather than overloading existing ones
- **New frontend surfaces** — the app is built around chaining models
  together; new models should expose a `predict_*()` function so
  `streamlit_app.py` can wire them in without rewrites

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `run_pipeline.py` hangs or times out | No network access to FastF1/Open-Meteo — this pipeline cannot run fully offline |
| Model A performs suspiciously well | Check for grid-position leakage into its feature set — this must never happen |
| `NULL`s in rookie-driver rows | A rolling feature is missing its `COALESCE` team-level fallback |
| `sql/schema.sql` and warehouse queries disagree | The SQL mirror wasn't updated alongside a `warehouse.py` change |

---

## Contributing

1. Create a feature branch off `main`
2. Follow the code style and tech constraints above — in particular, DuckDB
   and LightGBM only, SQL-first feature engineering, parameterized queries
3. Keep `sql/schema.sql` in sync with any warehouse schema change
4. Run `pytest` before opening a pull request
5. Flag any new pip dependency in the PR description before adding it to
   `requirements.txt`
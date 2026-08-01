# CLAUDE.md

## Project overview

Apex Analytics predicts F1 race results by chaining two models: **Model A** predicts
qualifying/grid position, and **Model B** predicts finishing position using Model A's
output as input. Data comes from FastF1, covering 2018 through the latest available
season. Storage is a local DuckDB warehouse, models are LightGBM, and the frontend is
a Streamlit app that runs a hypothetical scenario through both models end to end.

This is being built as the first complete slice of a larger platform — see
**Future expansion** at the bottom before assuming this is the whole project.

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
├── data/, models/artifacts/, tests/
└── requirements.txt
```

**Where things belong:**
- Experience/recency logic (`total_races_started`, `months_since_last_race`,
  `is_rookie`) → the shared `driver_history` block in `build_features.py` only;
  both feature tables join to it rather than duplicating the logic
- Grid-position prediction → `train_qualifying_model.py` only. **Never** give
  Model A real grid position as a feature — that's the thing it predicts
- Car-performance signal → a rolling feature computed from real qualifying gap-to-pole
  data, never a hardcoded per-team number

---

## Code style

- Python: PEP 8, snake_case
- Feature engineering: SQL first (window functions, CTEs), pandas only for glue code
- Every model reports a naive baseline next to its own metric — never accuracy alone
- DB queries: parameterized `?` placeholders — never f-strings in SQL
- Docstrings explain *why*, not just what

---

## Tech constraints

- **DuckDB only** — no Postgres, no ORM
- **LightGBM only** for both models — no deep learning on this tabular data
- **Streamlit only** for the frontend
- Model B must work with either a real historical grid position (training) or a
  predicted one from Model A (future-scenario inference) — one code path, not a fork
- Any driver-level rolling feature must `COALESCE` to a team-level fallback for
  rookies — never leave `NULL` or silently drop the row
- No new pip packages without flagging first

---

## Subagent Policy
- Always use a builtin explore subagent for codebase exploration before implementing any new feature
- Always use a subagent to verify test results after any implementation
- When asked to plan, delegate codebase research to a subagent before presenting the plan
- always use a builtin plan subagent in plan mode

---

## Commands
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python -m src.data.run_pipeline              # ingest 2018 → latest available season
python -m src.features.build_features        # build Model A + Model B feature sets
python -m src.models.train_qualifying_model   # train Model A
python -m src.models.train_race_result_model  # train Model B

streamlit run src/app/streamlit_app.py
pytest
```

---

## Implemented vs stub

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

## Warnings and things to avoid

- **Never train Model A with grid position as a feature** — direct target leak
- **Never collapse experience and recency into one number** — a returning driver
  after a long gap must look different from a continuously active one with the same
  career race count
- **Never hardcode a team or driver strength score** — always derive it from a
  rolling, data-driven feature
- Keep `sql/schema.sql` in sync with any `warehouse.py` change
- FastF1/Open-Meteo need real network access — don't assume they work in a sandbox

---

## Future expansion

This is intentionally the first complete vertical slice, not the final scope. The
architecture should stay easy to extend without restructuring:
- New models live as new files under `src/models/`, following the same pattern as
  Model A/B (one file per prediction target, own feature table in `build_features.py`)
- New data sources get their own ingestion file under `src/data/`, landing into new
  warehouse tables rather than overloading existing ones
- The frontend is built around chaining models together — new models should expose a
  `predict_*()` function so `streamlit_app.py` can wire them in without rewrites

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

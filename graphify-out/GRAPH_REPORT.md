# Graph Report - F1_project  (2026-08-27)

## Corpus Check
- 31 files · ~18,440 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 281 nodes · 391 edges · 21 communities (12 shown, 9 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a6ef901b`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]

## God Nodes (most connected - your core abstractions)
1. `connect()` - 22 edges
2. `_seed_all()` - 19 edges
3. `Apex Analytics` - 17 edges
4. `_fresh_conn()` - 16 edges
5. `_build_all()` - 16 edges
6. `Spec: <component_title>` - 16 edges
7. `ingest_qualifying()` - 15 edges
8. `ingest_race()` - 14 edges
9. `Spec: Build Features` - 13 edges
10. `Spec: Data Ingestion` - 13 edges

## Surprising Connections (you probably didn't know these)
- `test_ingest_race_records_one_row_per_driver()` --calls--> `ingest_race()`  [EXTRACTED]
  tests/test_data_ingest.py → src/data/fastf1_ingest.py
- `test_ingest_qualifying_records_one_row_per_driver()` --calls--> `ingest_qualifying()`  [EXTRACTED]
  tests/test_data_ingest.py → src/data/fastf1_ingest.py
- `test_connect_creates_expected_tables()` --calls--> `connect()`  [EXTRACTED]
  tests/test_warehouse.py → src/data/warehouse.py
- `_fresh_conn()` --calls--> `bootstrap_schema()`  [EXTRACTED]
  tests/test_build_features.py → src/data/warehouse.py
- `_build_all()` --calls--> `build_qualifying_features()`  [EXTRACTED]
  tests/test_build_features.py → src/features/build_features.py

## Import Cycles
- None detected.

## Communities (21 total, 9 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (36): bootstrap_schema(), connect(), DuckDB warehouse: connection factory + schema bootstrap.  The schema is the sour, Create tables if they don't exist. Idempotent., Open (or create) the warehouse file and return a live connection.      The calle, _archive_query(), _extract_day(), fetch_historical() (+28 more)

### Community 1 - "Community 1"
Cohesion: 0.11
Nodes (39): build_driver_history(), Materialise the shared experience/recency feature block.      One row per ``(dri, _build_all(), _fresh_conn(), DuckDBPyConnection, Tests for the Build Features slice.  Each test uses an in-memory DuckDB so it ca, One row per (driver, race) where the driver started., Earliest row per driver: is_rookie=TRUE, months_since_last_race IS NULL. (+31 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (27): Reusable Streamlit components for the prediction views.  Two chart components to, Render Model A's predicted grid order. Stub., Render Model B's predicted finishing order. Stub., render_qualifying_chart(), render_result_chart(), main(), Streamlit entry point — chain Model A → Model B on a user scenario.  Run with ``, Chain Model A and Model B on a single scenario dict. Stub. (+19 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (23): Data flow, Database changes, Definition of done, Depends on, Features, Files to change, Files to create, Frontend changes (if applicable) (+15 more)

### Community 4 - "Community 4"
Cohesion: 0.10
Nodes (21): get_target_seasons(), Project-wide settings resolved at import time.  The interesting bit is ``get_tar, Return [2018, ..., latest fully-elapsed season] inclusive.      A season is cons, _iter_rounds(), main(), Pipeline CLI — ingest every season from 2018 through the latest.  Run with ``p, Walk 2018 through the latest fully-elapsed season, one round at a time.      P, Return race round numbers from FastF1's event schedule.      Defers to FastF1 (+13 more)

### Community 5 - "Community 5"
Cohesion: 0.18
Nodes (21): Any, _coerce_int(), _coerce_str(), _ensure_cache_enabled(), ingest_qualifying(), ingest_race(), _lap_seconds(), _load_session() (+13 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (19): Apex Analytics, Architecture, Code style, Configuration, Contributing, Data model, Design principles, Development (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (16): Data flow, Database changes, Definition of done, Depends on, `driver_history` — shared experience/recency block, Features, Files to change, Files to create (+8 more)

### Community 8 - "Community 8"
Cohesion: 0.14
Nodes (13): Data flow, Database changes, Definition of done, Depends on, Features, Files to change, Files to create, Frontend changes (+5 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (10): Architecture, Code style, Commands, Future expansion, graphify, Implemented vs stub, Project overview, Subagent Policy (+2 more)

### Community 10 - "Community 10"
Cohesion: 0.31
Nodes (8): build_qualifying_features(), build_race_result_features(), main(), Build the three feature tables consumed by training and inference.  Tables produ, Model A feature table.      Target-leak guard: ``grid_position`` MUST NOT appear, Model B feature table.      Single code path: ``grid_position`` is just a column, Build all three feature tables in the live warehouse.      Order matters: ``driv, DuckDBPyConnection

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (6): evaluate_model_a(), evaluate_model_b(), Backtesting harness — compare predictions against actual outcomes.  Both models, Score Model A (grid position) against actuals. Stub., Score Model B (finish position) against actuals. Stub., Series

## Knowledge Gaps
- **83 isolated node(s):** `PreToolUse`, `allow`, `date`, `Path`, `DataFrame` (+78 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `connect()` connect `Community 0` to `Community 10`, `Community 5`?**
  _High betweenness centrality (0.137) - this node is a cross-community bridge._
- **Why does `bootstrap_schema()` connect `Community 0` to `Community 1`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Why does `_fresh_conn()` connect `Community 1` to `Community 0`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **What connects `PreToolUse`, `allow`, `# TODO: SQL-first EDA — qualifying gap distribution, finish-vs-grid` to the rest of the system?**
  _163 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.07682926829268293 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.11282051282051282 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.06854838709677419 - nodes in this community are weakly interconnected._
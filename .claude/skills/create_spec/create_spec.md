---
description: Create a spec file and feature branch for the next Apex Analytics component
argument-hint: "Component name and short description, e.g. 'weather-features add rolling wet-race signal'"
allowed-tools: Read, Write, Glob, Bash(git:*)
---

You are a senior developer spinning up a new component for the
Apex Analytics F1 prediction platform. Always follow the rules in CLAUDE.md.

Before doing anything else, use a builtin explore subagent to research the
codebase (per Subagent Policy in CLAUDE.md) rather than exploring directly.

User input: $ARGUMENTS

## Step 1 — Check working directory is clean
Run `git status` and check for uncommitted, unstaged, or
untracked files. If any exist, stop immediately and tell
the user to commit or stash changes before proceeding.
DO NOT CONTINUE until the working directory is clean.

## Step 2 — Parse the arguments
From $ARGUMENTS extract:

1. `component_title` — human readable title in Title Case
   - Example: "Weather Ingestion" or "Race Result Model"

2. `component_slug` — git and file safe slug
   - Lowercase, kebab-case
   - Only a-z, 0-9 and -
   - Maximum 40 characters
   - Example: weather-ingestion, race-result-model

3. `branch_name` — format: `feature/<component_slug>`
   - Example: `feature/weather-ingestion`

If you cannot infer these from $ARGUMENTS, ask the user
to clarify before proceeding.

## Step 3 — Check branch name is not taken
Run `git branch` to list existing branches.
If `branch_name` is already taken, append a number:
`feature/weather-ingestion-01`, `feature/weather-ingestion-02` etc.

## Step 4 — Switch to main and pull latest
Run:
```
git checkout main
git pull origin main
```

## Step 5 — Create and switch to the feature branch
Run:
```
git checkout -b <branch_name>
```

## Step 6 — Research the codebase
Delegate this research to a builtin explore subagent (per Subagent Policy).
The subagent should read:
- `CLAUDE.md` — architecture, conventions, "Implemented vs stub" table, warnings
- `src/config/settings.py` — how season ranges are resolved
- `src/data/warehouse.py` and `sql/schema.sql` — existing DuckDB schema (must stay in sync)
- `src/features/build_features.py` — existing feature tables, especially the shared
  `driver_history` block, to avoid duplicating experience/recency logic
- `src/models/` — existing model files, to follow the one-file-per-target pattern
- `src/app/streamlit_app.py`, `src/app/components.py`, `src/app/styles.py` — if the
  component touches the frontend
- All files in `.claude/specs/` — avoid duplicating existing specs

Check the "Implemented vs stub" table in `CLAUDE.md` to confirm the requested
component is not already marked complete. If it is, warn the user and stop.

## Step 7 — Write the spec
Generate a spec document with this exact structure:

---
# Spec: <component_title>

## Overview
One paragraph describing what this component does, where it sits in the
Model A → Model B pipeline (or frontend/data layer), and why it's needed
at this stage of the Apex Analytics roadmap.

## Depends on
Which existing components (ingestion, warehouse tables, `driver_history`,
Model A, etc.) this component requires to already exist.

## Data flow
Where inputs come from and where outputs land:
- Input source(s): FastF1 ingest, Open-Meteo, existing warehouse tables,
  or another model's output
- Output destination: new/existing DuckDB table, new feature columns,
  a trained model artifact, or a `predict_*()` function exposed to the frontend

If this component is purely a transformation with no new storage,
state "No new data flow — operates on existing tables/features".

## Database changes
Any new DuckDB tables, columns, or constraints needed in `warehouse.py`.
Always verify against the current `src/data/warehouse.py` before writing
this section. Note that `sql/schema.sql` must be updated to match.
If none: state "No database changes".

## Features
- **New:** any new columns/features added to `qualifying_features` or
  `race_result_features`, and whether they belong in the shared
  `driver_history` block
- **Rookie/NULL handling:** confirm any new driver-level rolling feature
  has a team-level `COALESCE` fallback
If no new features: state "No new features".

## Model impact (if applicable)
- Does this affect Model A (qualifying/grid position) or Model B
  (finishing position)? State which, or "Not applicable".
- Explicit confirmation that no target-leaking feature is introduced
  (e.g. real grid position must never reach Model A)
- Whether Model B's single code path (real or predicted grid position)
  is preserved

## Frontend changes (if applicable)
- **Create:** new chart/component functions with their path
  (e.g. `src/app/components.py`)
- **Modify:** existing Streamlit elements and what changes
- Whether a new `predict_*()` function needs wiring into `streamlit_app.py`
If none: state "No frontend changes".

## Files to change
Every file that will be modified.

## Files to create
Every new file that will be created.

## New dependencies
Any new pip packages. Per CLAUDE.md, these must be flagged explicitly
before use. If none: state "No new dependencies".

## Rules for implementation
Specific constraints Claude must follow. Always include, as relevant:
- DuckDB only — no Postgres, no ORM
- LightGBM only for both models — no deep learning
- SQL first for feature engineering (window functions, CTEs); pandas only for glue
- Parameterized `?` placeholders — never f-strings in SQL
- Never give Model A real grid position as a feature
- Never collapse experience and recency into a single number
- Never hardcode a team or driver strength score — derive from a rolling,
  data-driven feature
- Any driver-level rolling feature must `COALESCE` to a team-level fallback
- Every model reports a naive baseline next to its own metric
- Keep `sql/schema.sql` in sync with any `warehouse.py` change
- Docstrings explain *why*, not just what

## Definition of done
A specific testable checklist. Each item must be verifiable by running
the relevant pipeline command (e.g. `python -m src.features.build_features`,
`python -m src.models.train_qualifying_model`, `pytest`, or
`streamlit run src/app/streamlit_app.py`).
---

## Step 8 — Save the spec
Save to: `.claude/specs/<component_slug>.md`

## Step 9 — Verify
Use a builtin subagent to verify the spec is internally consistent — that
referenced files actually exist in the codebase and that no rule from
CLAUDE.md's "Warnings and things to avoid" section is contradicted.

## Step 10 — Report to the user
Print a short summary in this exact format:
```
Branch:    <branch_name>
Spec file: .claude/specs/<component_slug>.md
Title:     <component_title>
```

Then tell the user:
"Review the spec at `.claude/specs/<component_slug>.md`
then enter Plan Mode with Shift+Tab twice to begin implementation."

Do not print the full spec in chat unless explicitly asked.
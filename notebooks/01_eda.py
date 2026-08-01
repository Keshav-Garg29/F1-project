# %% [markdown]
# # 01 — Exploratory data analysis
#
# Jupytext percent-format notebook. Open in a Jupyter-aware editor or
# pair with a `.ipynb` via `jupytext --set-formats ipynb,py:percent`.
#
# Findings here should inform feature engineering in
# ``src/features/build_features.py`` and the baseline choices in
# ``src/models/evaluate.py``.

# %%
from src.data.warehouse import connect

conn = connect()
print(conn.execute("SHOW TABLES").fetchdf())

# %%
# TODO: SQL-first EDA — qualifying gap distribution, finish-vs-grid
# deltas, rookie vs veteran comparison, weather correlation with
# retirements. Each finding becomes a candidate feature or a
# documented decision not to add one.

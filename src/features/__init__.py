"""Feature engineering for the two prediction models.

SQL-first (window functions, CTEs), pandas only for glue code. The
shared ``driver_history`` block is the single source of truth for
experience/recency features and is joined into both downstream feature
tables — never duplicated.
"""

# Future Tools — simple_snowflake_mcp

Tools to consider adding, prioritised for dbt/SQL development workflows.

## From Original Upstream (not yet implemented)

- **list-views** — List views in a database/schema. Essential since dbt models often materialise as views.
- **describe-view** — Get view definition SQL + columns. Useful for debugging dbt model output.
- **query-view** — Query a view with optional row limit. Quick inspection of dbt model results.
- **get-table-sample** — Sample N rows from a table. Preview data when building staging/intermediate models.
- **explain-query** — Show execution plan for a SQL query. Performance-tune dbt models before promotion.
- **show-query-history** — Recent query history with timing. Debug dbt run performance, find slow models.
- **get-warehouse-status** — Warehouse status and usage. Monitor compute during dbt runs.
- **validate-sql** — Syntax-check SQL without executing. Catch errors before committing dbt models.

## New Ideas

- **list-warehouses** — List available warehouses. Check compute options before running dbt.
- **compare-schemas** — Diff two schemas (e.g. dev vs prod). Core dbt dev workflow — verify model changes.
- **get-row-count** — Quick row counts for one or more tables. Data validation after dbt runs.
- **search-sql-history** — Search past queries by pattern/user/time. Find specific dbt run queries.
- **get-dependencies** — Table/view lineage via `GET_OBJECT_REFERENCES`. Understand upstream/downstream impact.
- **run-data-test** — Execute ad-hoc dbt-style tests (not_null, unique, accepted_values) against any table/column.
- **get-freshness** — Check max timestamp column value for a table. Equivalent of `dbt source freshness`.
- **diff-table-counts** — Compare row counts between two tables (e.g. source vs staging). Quick reconciliation.

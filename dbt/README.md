# dbt layer

Bronze = the Parquet lake (read in place). Silver = typed, deduplicated tables. Gold = star schema
(`dim_session`, `dim_driver`, `fct_lap`, `fct_stint`, `fct_pit_stop`, `fct_result`,
`fct_race_control_event`) plus `rec_finish_order`, a reconciliation of lap positions against the
official classification.

Run from the repository root:

    dbt build --project-dir dbt --profiles-dir dbt
    dbt docs generate --project-dir dbt --profiles-dir dbt && dbt docs serve --project-dir dbt --profiles-dir dbt

Environment: `F1_LAKE` (default `data/lake`), `F1_DBT_DB` (default `data/f1_dbt.duckdb`).
Tests marked `warn` report suspect data without failing the build. Gold models with an enforced
contract fail at build time if a column's name or type changes.
Not covered yet: telemetry tables, history (Jolpica) tables, weather, track status.
CI check on synthetic data: `python dbt/ci/make_ci_lake.py ci_lake` then
`F1_LAKE=ci_lake F1_DBT_DB=ci_lake/f1.duckdb dbt build --project-dir dbt --profiles-dir dbt`.

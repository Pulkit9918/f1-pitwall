"""Smoke test: can Airflow see the project, the lake and both virtualenvs? Trigger it by hand from the UI."""
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

with DAG(
    dag_id="f1_smoke_test",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["f1", "smoke"],
) as dag:
    BashOperator(
        task_id="ingest_venv",
        bash_command="/home/airflow/venvs/ingest/bin/python -c \"import fastf1, pandera, duckdb, pandas; "
                     "print('fastf1', fastf1.__version__, '| pandera', pandera.__version__, '| duckdb', duckdb.__version__, "
                     "'| pandas', pandas.__version__)\"",
    )
    BashOperator(
        task_id="dbt_venv",
        bash_command="/home/airflow/venvs/dbt/bin/dbt --version",
    )
    BashOperator(
        task_id="lake_visible",
        bash_command="cd /opt/f1 && ls data/lake | head -20 && echo '---' && ls data/lake/laps | head -3",
    )

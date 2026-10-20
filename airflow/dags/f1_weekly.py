"""Weekly F1 pipeline: ingest new sessions, build dbt, check contracts and docs.

plan_sessions    asks the ingest venv which sessions are finished but not yet in the lake
ingest_session   one mapped task per session, pool f1_ingest (1 slot) so FastF1 is hit
                 one session at a time; a rate limit retries the task after a delay
dbt_build        silver + gold models and dbt tests
check_contracts  pandera contracts over the whole lake
dbt_docs, doc_coverage   catalog plus the documentation gate
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from datetime import timedelta

import pendulum
from airflow.exceptions import AirflowFailException, AirflowSkipException
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.sdk import DAG, Param, get_current_context, task

REPO = os.environ.get("F1_REPO", "/opt/f1")
INGEST_PY = "/home/airflow/venvs/ingest/bin/python"
DBT = "/home/airflow/venvs/dbt/bin/dbt"
WRAPPER = "scripts/airflow_ingest.py"
EXIT_SKIP, EXIT_RATELIMIT = 99, 75


def _stream(cmd: list[str]) -> tuple[int, list[str]]:
    """Run a command from the repo root, echo its output into the task log."""
    proc = subprocess.Popen(
        cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    lines = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    return proc.wait(), lines


def _alert_failed_run(context) -> None:
    """DAG failure callback: one line in logs/alerts.log, plus a phone push when
    F1_ALERT_NTFY_TOPIC is set. Never raises, so it cannot hide the real failure."""
    try:
        run_id = getattr(context.get("dag_run"), "run_id", "unknown run")
        reason = str(context.get("reason") or "run failed")
    except Exception:
        run_id, reason = "unknown run", "run failed"
    text = f"f1_weekly {run_id} failed ({reason}). Check the red tasks at http://localhost:8081"
    try:
        path = os.path.join(os.environ.get("AIRFLOW_HOME", "/opt/airflow"), "logs", "alerts.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{pendulum.now('UTC').to_iso8601_string()} {text}\n")
    except Exception as e:
        print(f"alert: could not write the local log: {e}", flush=True)
    topic = os.environ.get("F1_ALERT_NTFY_TOPIC", "").strip()
    if not topic:
        return
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{topic}",
            data=text.encode("utf-8"),
            headers={"Title": "F1 pipeline failed", "Priority": "high", "Tags": "rotating_light"},
        )
        urllib.request.urlopen(req, timeout=15).close()
    except Exception as e:
        print(f"alert: could not send the push: {e}", flush=True)

@task
def plan_sessions() -> list[dict]:
    p = get_current_context()["params"]
    cmd = [
        INGEST_PY, WRAPPER, "plan",
        "--years", p["years"] or str(pendulum.now("UTC").year),
        "--rounds", p["rounds"],
        "--codes", p["codes"],
        "--limit", str(p["limit"]),
    ]
    if p["retry_failed"]:
        cmd.append("--retry-failed")
    rc, lines = _stream(cmd)
    if rc != 0:
        raise AirflowFailException(f"planning failed (exit {rc})")
    marked = [x for x in lines if x.startswith("PLAN_JSON:")]
    if not marked:
        raise AirflowFailException("planner printed no PLAN_JSON line")
    return json.loads(marked[-1][len("PLAN_JSON:"):])


@task(
    pool="f1_ingest",
    max_active_tis_per_dag=1,
    retries=4,
    retry_delay=timedelta(minutes=20),
)
def ingest_session(s: dict) -> str:
    cmd = [INGEST_PY, WRAPPER, "run", str(s["year"]), str(s["round"]), s["code"]]
    if not s["telemetry"]:
        cmd.append("--no-telemetry")
    rc, _ = _stream(cmd)
    if rc == 0:
        return f"{s['year']} R{s['round']} {s['code']}: ok"
    if rc == EXIT_SKIP:
        raise AirflowSkipException("already ingested")
    if rc == EXIT_RATELIMIT:
        raise RuntimeError("FastF1 rate limited; Airflow retries after the retry delay")
    raise AirflowFailException(f"ingest failed (exit {rc}); not retried, see the log above")


def _bash(task_id: str, command: str, **kw) -> BashOperator:
    return BashOperator(task_id=task_id, bash_command=f"cd {REPO} && {command}", **kw)


with DAG(
    dag_id="f1_weekly",
    description="Ingest new F1 sessions, then dbt build, contracts and docs",
    schedule="0 3 * * 2",
    start_date=pendulum.datetime(2026, 1, 1, tz="Australia/Sydney"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "pulkit"},
    on_failure_callback=_alert_failed_run,
    params={
        "years": Param("", type="string", description="blank = current year; or 2022-2026"),
        "rounds": Param("", type="string", description="blank = all; or 5 or 5-9"),
        "codes": Param("", type="string", description="blank = all; or R,Q,S"),
        "limit": Param(0, type="integer", description="0 = no limit; else plan at most N sessions"),
        "retry_failed": Param(False, type="boolean"),
    },
    tags=["f1"],
):
    plan = plan_sessions()
    ingested = ingest_session.expand(s=plan)

    dbt_build = _bash(
        "dbt_build",
        f"{DBT} build --project-dir dbt --profiles-dir dbt",
        trigger_rule="all_done",
    )
    contracts = _bash(
        "check_contracts", f"{INGEST_PY} scripts/check_contracts.py", trigger_rule="all_done"
    )
    dbt_docs = _bash("dbt_docs", f"{DBT} docs generate --project-dir dbt --profiles-dir dbt")
    doc_coverage = _bash("doc_coverage", f"{INGEST_PY} scripts/doc_coverage.py --check")

    ingested >> [dbt_build, contracts]
    dbt_build >> dbt_docs >> doc_coverage

    # the run's state comes from its last tasks; this one fails the run if planning,
    # any ingest, contracts or docs failed (skipped is fine)
    pipeline_ok = EmptyOperator(task_id="pipeline_ok", trigger_rule="none_failed")
    [ingested, contracts, doc_coverage] >> pipeline_ok

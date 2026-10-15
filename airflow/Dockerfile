# Airflow for f1-pitwall. The project's own dependencies live in two separate virtualenvs inside the image
# (ingest and dbt), exactly like on the laptop, so they can never clash with Airflow's own packages.
# They are installed with the same pinned constraints files the project uses everywhere else.
# If the pull fails for this tag, build with:  docker compose build --build-arg AIRFLOW_IMAGE=apache/airflow:3.3.2
ARG AIRFLOW_IMAGE=apache/airflow:3.3.2-python3.11
FROM ${AIRFLOW_IMAGE}
USER airflow
COPY --chown=airflow:0 requirements-ingest.txt requirements-dbt.txt /tmp/req/
COPY --chown=airflow:0 constraints/ingest.txt /tmp/req/constraints-ingest.txt
COPY --chown=airflow:0 constraints/dbt.txt /tmp/req/constraints-dbt.txt
RUN python -m venv /home/airflow/venvs/ingest \
 && /home/airflow/venvs/ingest/bin/pip install --no-cache-dir -r /tmp/req/requirements-ingest.txt -c /tmp/req/constraints-ingest.txt \
 && python -m venv /home/airflow/venvs/dbt \
 && /home/airflow/venvs/dbt/bin/pip install --no-cache-dir -r /tmp/req/requirements-dbt.txt -c /tmp/req/constraints-dbt.txt

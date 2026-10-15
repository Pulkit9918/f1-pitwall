# Airflow for f1-pitwall

Airflow 3.3.2, LocalExecutor, Postgres. Runs on its own port (8081), project name and volumes.
The project is mounted at /opt/f1; its dependencies live in two virtualenvs in the image
(`/home/airflow/venvs/ingest` and `/home/airflow/venvs/dbt`), built from the pinned `constraints/` files.

```bash
cd airflow
cp .env.example .env     # then fill FERNET_KEY and AIRFLOW__API_AUTH__JWT_SECRET (see below)
docker compose build
docker compose up -d
```

Open http://localhost:8081 (login airflow / airflow, local only).

Generate the two secrets:

```bash
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"   # FERNET_KEY
python -c "import secrets;print(secrets.token_urlsafe(48))"                           # JWT secret
```

Stop: `docker compose stop` (keeps everything). Remove containers and database: `docker compose down -v`.

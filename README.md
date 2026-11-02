# F1 Pitwall

![CI](https://github.com/Pulkit9918/f1-pitwall/actions/workflows/ci.yml/badge.svg)
![dbt](https://github.com/Pulkit9918/f1-pitwall/actions/workflows/dbt.yml/badge.svg)

Race-strategy analytics for Formula 1 on a local Parquet lakehouse: a resumable ingestion pipeline, a tested dbt layer, a race-state engine rebuilt from GPS, a pit-stop predictor, a Streamlit app, a read-only API and a static web app with a race replay.

Most F1 tools are viewers. This project asks a narrower question: *how well can the numbers on a timing screen be reconstructed and used for strategy decisions, and how do we know?* Every derived number comes with a test against something independent (official sector timing, the official classification, real pit stops), and the limits are written down.

> **Unofficial.** Not associated with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V. Data comes from the public timing feed via [FastF1](https://github.com/theOehrly/Fast-F1) and from the [Jolpica](https://github.com/jolpica/jolpica-f1) Ergast-compatible API. The raw data, the lake and the database are not in this repository. It does include derived JSON that the web app reads under `web/public`; I have not confirmed that publishing that is permitted (see [Data terms](docs/data-terms.md)). Personal, non-commercial use.

## Results at a glance

| Part | Result | Details |
|---|---|---|
| Ingest | 706 sessions, 2018-2026, about 1.8 GB of zstd Parquet. Every attempt is in an audit log; data contracts are checked on every table before it is written | [data.md](docs/data.md) |
| dbt on DuckDB | 57 models, 1 seed and 200 tests: 251 of 258 steps passed, 7 warnings, 0 errors. 26 gold models have enforced contracts; a documentation-coverage gate runs in CI | [dbt.md](docs/dbt.md) |
| Race-state engine | Running order rebuilt from GPS and checked against official sector timing on 135 sessions: median exact order 97.2% at the first sector line (85.9% for a last-lap baseline) and 99.7% at the second (86.1%). It fails at the second line at Baku and Suzuka | [engine-and-models.md](docs/engine-and-models.md) |
| Pit-stop predictor | Scored on races it was not fitted on: 41.1% exact place over 5,489 green-flag stops, and 79.4% on the 649 undisturbed stops, which are 12% of all stops | [apps.md](docs/apps.md) |
| Q&A agent | A local 14B model answering questions with SQL: 25 of 28 on questions written after the prompts were frozen, and it declined all 8 that the data cannot answer | [qa-agent.md](docs/qa-agent.md) |

## Limits to know first

- **New sessions cannot be ingested at the moment.** Since about 15 October 2026 F1's timing archive wants a login. The lake is complete through round 17 of 2026 (Singapore); everything downstream works on it.
- **The pit-stop predictor gets the exact place right about four times in ten.** In most stops other cars are also pitting and the model does not account for them.
- **Some results are unexplained.** The data gaps, and the warnings left in the dbt build, are listed with what was measured, in [dbt.md](docs/dbt.md).
- **Publishing the derived JSON is a risk I have not resolved.** See [Data terms](docs/data-terms.md).

The full list is in [decisions-and-limits.md](docs/decisions-and-limits.md).

## What it does

- **Ingests** race-weekend data one session at a time (laps, sectors, tyres, weather, race control, track status, car telemetry and GPS position at about 3.8 Hz) into partitioned Parquet files, and 1950-to-now results and standings from Jolpica. Every attempt is written to an ingest log.
- **Transforms** the lake with dbt (DuckDB): typed and deduplicated silver tables, gold dimensions and facts with enforced data contracts, and tests that compare the pipeline's output with the official classification and with its own log.
- **Checks** every table it writes against data contracts (structure as hard failures, value ranges as logged findings) and records per-session quality metrics (value ranges, sampling gaps, circuit metadata) in the log.
- **Reconstructs the race** from GPS: a running order and time gaps for every car at any moment, validated against the official sector timing.
- **Models pit stops**: the time lost in the pit lane, and where a driver rejoins, backtested on real stops.
- **Serves it** in a Streamlit app (race explorer, track map, driver and multi-driver telemetry, race gaps, pit window, a race scrubber with auto-play, a session timing screen, a 1950-to-now history browser) and through a read-only API.
- **Publishes it** as a static web app: telemetry against distance, sector colours, a pit-stop predictor scored on held-out races, practice long runs and a race replay. No server is needed; the pages read JSON that exporters write from the gold tables.

## Architecture

```
FastF1 (timing + telemetry) ──┐
                               ├─► ingest.py / batch.py ─► Parquet lake ─► dbt (DuckDB) ─► gold tables ─► Streamlit app
Jolpica API (1950-now) ───────┘      (rate-limit aware,     data/lake/      silver -> gold     contracts      (read-only)
                                      resumable, one          year=/round=/   + reconciliation   + tests
                                      session at a time)      session=/
                                           │
                                           └─► _manifest/*.jsonl (ingest log) ─► dbt run metadata, report.py, verify.py
```

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Sources | FastF1 3.8 (timing, telemetry), Jolpica (history) |
| Storage | Parquet (zstd), Hive-style partitions, JSONL ingest log |
| Transform | dbt-core 1.12 with dbt-duckdb, models read the lake in place |
| Query | DuckDB (embedded), pandas, NumPy |
| App | Streamlit 1.65, Plotly |
| CI | GitHub Actions: unit tests and syntax lint, a full dbt build on a synthetic lake, and a documentation coverage gate |
| Checks | pandera data contracts at ingest (`contracts.py`), dbt tests and contracts, `verify.py` (file vs log), `report.py` (coverage and problems) |
| Reproducibility | Exact dependency versions per environment in `constraints/`, regenerated by `scripts/freeze_constraints.sh` |
| Orchestration | Apache Airflow 3.3 in Docker Compose (LocalExecutor, Postgres), one weekly DAG, ingest and dbt in separate virtualenvs in the image |

There is no warehouse server. That was deliberate: an earlier version of this project ran on a warehouse trial that expired and took its dashboard with it. Everything here runs from files, and Airflow (local, in Docker) only schedules the same commands you can run by hand (see Orchestration).

## Run it locally

```bash
# environments (kept separate so the app can never disturb a long ingest)
python3.11 -m venv ~/.venvs/f1-pitwall && ~/.venvs/f1-pitwall/bin/pip install -r requirements-ingest.txt -c constraints/ingest.txt
python3.11 -m venv ~/.venvs/f1-app     && ~/.venvs/f1-app/bin/pip install -r requirements-app.txt -c constraints/app.txt
python3.11 -m venv ~/.venvs/f1-dbt     && ~/.venvs/f1-dbt/bin/pip install -r requirements-dbt.txt -c constraints/dbt.txt

# ingest one season (race, qualifying, sprints); --dry-run first to see the plan
source ~/.venvs/f1-pitwall/bin/activate
python batch.py --years 2024 --codes R,Q,S,SQ,SS --dry-run
scripts/start_batch.sh --years 2024 --codes R,Q,S,SQ,SS --cooldown 5 --max-waits 30
scripts/status.sh                                             # progress at a glance

# history, checks
python history.py
python report.py && python verify.py
python scripts/check_contracts.py                    # the eight main tables against contracts.py

# transform and test with dbt (reads data/lake, writes data/f1_dbt.duckdb)
~/.venvs/f1-dbt/bin/dbt build --project-dir dbt --profiles-dir dbt
~/.venvs/f1-dbt/bin/dbt docs generate --project-dir dbt --profiles-dir dbt
python scripts/doc_coverage.py --check                # documentation coverage (also run in CI)

# app
~/.venvs/f1-app/bin/streamlit run app/Home.py

# the CI dbt build on a synthetic lake, without any real data
python dbt/ci/make_ci_lake.py ci_lake
F1_LAKE=ci_lake F1_DBT_DB=ci_lake/f1.duckdb ~/.venvs/f1-dbt/bin/dbt build --project-dir dbt --profiles-dir dbt
```

`F1_LAKE` and `F1_DBT_DB` set the lake and dbt database paths (defaults `data/lake` and `data/f1_dbt.duckdb`).

To browse the tables in a SQL editor, install the DuckDB CLI, run `duckdb -ui` from the repository root, and run `ATTACH 'data/f1_dbt.duckdb' AS f1 (READ_ONLY);` in the editor. Read-only, so it cannot block a dbt build.

## Documentation

| File | What is in it |
|---|---|
| [docs/data.md](docs/data.md) | Coverage, lake layout, ingestion and rate limits, and what the data-quality checks found in the raw feed |
| [docs/dbt.md](docs/dbt.md) | The silver and gold models, reconciliation, race control periods, telemetry coverage, known data gaps |
| [docs/engine-and-models.md](docs/engine-and-models.md) | The race-state engine and its validation, pit loss, rejoin prediction, tyre degradation, undercuts |
| [docs/apps.md](docs/apps.md) | The Streamlit app, the web app and its replay, the API, and the Airflow DAG |
| [docs/qa-agent.md](docs/qa-agent.md) | The question-answering agent and its two evaluation sets |
| [docs/decisions-and-limits.md](docs/decisions-and-limits.md) | Decisions and dead ends, limitations, roadmap |
| [docs/data-terms.md](docs/data-terms.md) | What I found about data terms |

## Repository layout

```
ingest.py        one session -> partitioned Parquet + log record
batch.py         season loop: schedule, skips, rate-limit waits, retries
history.py       Jolpica 1950-now -> Parquet (cached raw responses)
report.py        coverage and problems per season
verify.py        every ingested file against its log record
contracts.py     pandera data contracts checked at ingest (hard rules fail a table, soft rules are logged)
constraints/     exact dependency versions per environment (ingest, app, dbt)
dbt/             models (silver, gold, reconciliation), tests, macros, CI lake generator
airflow/         Docker Compose stack (Airflow 3, Postgres), image with the ingest and dbt virtualenvs, the f1_weekly DAG
scripts/         start_batch.sh (refuses a second run), status.sh, backfill_track_status.py, check_contracts.py, doc_coverage.py, freeze_constraints.sh, airflow_ingest.py (plan and run entry points for the DAG), export_*.py (gold tables to the JSON the web app reads)
app/             Streamlit app: pitwall.py (data access), engine.py (race state), racelib.py, pages/
api/             read-only FastAPI service over the gold tables (main.py); requirements-api.txt
web/             static Next.js site (analytics pages, telemetry, predictor, practice, replay), vitest tests
qa_agent/        question-answering agent over the gold tables and its 44-question evaluation (see Question-answering agent)
tests/           unit tests for the race engine, race-control logic, history fetching, app helpers and the API
experiments/     measurement scripts behind the numbers above (run from the repository root)
.github/         CI: ci.yml (tests, lint) and dbt.yml (dbt build on a synthetic lake, documentation gate)
```

## Credits and licence

Built on [FastF1](https://github.com/theOehrly/Fast-F1) (MIT) and the Jolpica API. The design was informed by several open-source F1 projects (f1-race-replay, F1ReplayTiming, undercut-f1); no code from them is used here.

The code is MIT-licensed (see `LICENSE`). The licence covers the code only, not F1 data or marks.

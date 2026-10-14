# F1 Pitwall

![CI](https://github.com/Pulkit9918/f1-pitwall/actions/workflows/ci.yml/badge.svg)
![dbt](https://github.com/Pulkit9918/f1-pitwall/actions/workflows/dbt.yml/badge.svg)

Race-strategy analytics for Formula 1 on a local Parquet lakehouse: a resumable ingestion pipeline with an audit log, a tested dbt transformation layer (typed silver tables, gold dimensions and facts with enforced contracts, reconciliation against official results), a validated race-state engine, strategy models with measured accuracy, and a Streamlit app with a race scrubber.

> **Unofficial.** This project is not associated with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V. Data comes from the public timing feed via [FastF1](https://github.com/theOehrly/Fast-F1) and from the [Jolpica](https://github.com/jolpica/jolpica-f1) Ergast-compatible API. The data is not redistributed in this repository. Personal, non-commercial use.

<!-- TODO: add 3 screenshots to docs/screenshots/ (race scrubber, session timing, pit window) and reference them here -->

## What it does

- **Ingests** race-weekend data one session at a time (laps, sectors, tyres, weather, race control, track status, 4 Hz car telemetry and GPS position) into partitioned Parquet files, and 1950-to-now results and standings from Jolpica. Every attempt is written to an ingest log.
- **Transforms** the lake with dbt (DuckDB): typed and deduplicated silver tables, gold dimensions and facts with enforced data contracts, and tests that compare the pipeline's output with the official classification and with its own log.
- **Checks** every file it writes and records per-session quality metrics (value ranges, sampling gaps, circuit metadata) in the log.
- **Reconstructs the race** from GPS: a running order and time gaps for every car at any moment, validated against the official sector timing.
- **Models pit stops**: the time lost in the pit lane, and where a driver rejoins, backtested on real stops.
- **Serves it** in a Streamlit app: race explorer, track map, driver and multi-driver telemetry, race gaps, pit window, a race scrubber with auto-play, a session timing screen, and a 1950-to-now history browser.

## Why it exists

Most F1 tools are viewers: they show the timing screen. This project asks a narrower question: *how well can the numbers on that screen be reconstructed and used for strategy decisions, and how do we know?* Every derived number here comes with a test against something independent (official sector timing, official classification, real pit stops), and the limits are written down.

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
| CI | GitHub Actions: unit tests and syntax lint, and a full dbt build on a synthetic lake |
| Checks | dbt tests and contracts, `verify.py` (file vs log), `report.py` (coverage and problems) |

There is no warehouse server and no orchestrator yet (see the roadmap). That was deliberate: an earlier version of this project ran on a warehouse trial that expired and took its dashboard with it. Everything here runs from files.

## Data

**Coverage**

| Tier | Years | Content |
|---|---|---|
| Results, standings, drivers, teams, circuits | 1950 - 2026 | Jolpica |
| Full detail | 2022 - 2026 | Races, qualifying, sprints, sprint qualifying: laps, sectors, tyres, weather, race control, track status, car telemetry, GPS position |
| Laps only | Practice sessions, 2022 - 2026 | No telemetry |
| Timing without telemetry | 2018 - 2021 | Races and qualifying only (no practice, no 2021 sprints): laps, tyres, weather, race control, track status |

Sessions loaded completely: 706 (2018: 41, 2019: 42, 2020: 34, 2021: 44, 2022: 110, 2023: 110, 2024: 120, 2025: 120, 2026: 85), plus one 2018 race for which FastF1 provides no laps (see known data gaps). Total about 1.8 GB on disk.

**Typical size per session** (zstd Parquet): race with telemetry 9-16 MB, qualifying 4-5 MB, sprint 4-7 MB, practice (laps only) about 0.1 MB.

**Lake layout**

```
data/lake/
  laps/ telemetry_car/ telemetry_pos/ weather/ race_control/ results/
  circuit_corners/ circuit_marshal_sectors/ track_status/ session_status/
     year=YYYY/round=RR/session=CODE/part.parquet
  history/   results, driver_standings, constructor_standings, drivers, constructors, circuits
  _manifest/ sessions.jsonl (one record per ingest attempt), backfill.jsonl (one per backfill attempt)
data/f1_dbt.duckdb                       dbt output (silver and gold schemas)
```

Round numbers follow FastF1's numbering for the season. They do not always match the official calendar (the 2026 calendar was changed), so history tables are never joined to sessions by round number. The 2023 sprint qualifying session is stored as `SS`.

## Ingestion

- **One session at a time**, written then recorded in the ingest log, so an interrupted run loses at most the session in progress.
- **Rate limits.** FastF1 limits itself to about 500 requests an hour (200 for ergast.com hosts), counted in a sliding window inside the Python process; it raises an error when the window is full. The batch runner detects this, waits, and retries. Observed behaviour: a burst of roughly 40 sessions, then about an hour before the first retry succeeds. A season takes 2-3 hours unattended. <!-- TODO: confirm wording after the 2022-2023 runs -->
- **Resumable.** Finished sessions are skipped; `--retry-failed` redoes failures; `--dry-run` prints the plan.
- **Scratch cache** is deleted after every session, so disk use stays flat.
- **Status per session:** ok, partial or failed, with the reason.
- **A launcher script** refuses to start a second run. (An accidental double launch early on made two runs collide on the shared cache; `verify.py` was written to prove nothing was damaged. It found nothing, and the duplicate log lines are harmless.)
- **Backfill.** `scripts/backfill_track_status.py` adds `track_status` and `session_status` to sessions that were ingested before those tables existed (206 sessions in 2019, 2025 and 2026). It only writes the missing tables, skips sessions that already have them, and logs to `backfill.jsonl`.

## Transformation layer (dbt)

Run from the repository root: `dbt build --project-dir dbt --profiles-dir dbt`. The models read the Parquet lake in place and write a DuckDB file under `data/`.

| Layer | Models | What happens |
|---|---|---|
| Sources | `lake.*`, `history.*`, `manifest.runs` | Parquet files and the JSON ingest log, with not-null checks on key columns |
| Silver (10) | laps, results, race control, weather, track status, sessions, three history tables, ingest runs | Typed columns, duplicates removed, explicit keys such as `session_key = 2025-R07-R` |
| Gold (17) | `dim_session`, `dim_driver`, `dim_circuit`, `dim_constructor`, `dim_historical_driver`, `fct_lap`, `fct_stint`, `fct_pit_stop`, `fct_result`, `fct_race_control_event`, `fct_track_status_period`, `fct_session_weather`, `fct_season_result`, `fct_driver_standing`, `fct_constructor_standing`, `fct_ingest_session`, `fct_ingest_summary` | Facts and dimensions the app and any later API read |
| Reconciliation (3) | `rec_finish_order`, `rec_lake_vs_manifest`, `rec_weekend_coverage` | The pipeline checked against official results and against its own log |

The last build had 93 steps: 30 models and 63 tests. Result: 90 passed, 3 warnings, 0 errors. Five gold models have enforced contracts (declared column names and types that the build checks).

**What the reconciliation found**

| Check | Result |
|---|---|
| Lap counts of classified finishers against the official classification | Match in 3,116 of 3,183 classified finishers (67 mismatches; 65 of them are in the four races whose lap counts disagree, listed under known data gaps below) |
| Finishing order derived from laps against the official order | Exact position match turned out to be a poor metric: post-race penalties shift official positions. The test now compares the order of classified finishers pairwise and flags races with at least 10 finishers that fall below 90% agreement or have more than one lap-count mismatch. Ten races are flagged, all listed under known data gaps below: four have penalty events in race control (whether they explain the order is untested), two have low order agreement and no recorded penalty, and four have lap counts that disagree with the official classification |
| Pit lane time (timed lane transit) for green-flag race stops | Median about 23 s. Different from the 22.4 s pit *loss* used in the strategy models below, which includes the in-lap and out-lap. Two stops fall outside the 5-300 s plausibility window (one in the 2026 round 1 race, one in the 2026 round 12 sprint); neither is a red flag, cause unknown (see known data gaps) |
| Lake files against the ingest log, five tables per session | Row counts agreed for every session at the last build |
| Race weekends against the expected set of sessions | No gaps. A session counts as present if any of its tables has data, so this check does not see the 2018 Italian GP race (results but no laps). Expected sessions by weekend format are my reading of FastF1's session names |
| Sessions with results but no laps | One: the 2018 Italian GP race (`session_missing_laps`) |

**Known data gaps**

Every warning left in the build is listed here, with what was measured and what is still unexplained.

| Session | What the data shows | Status |
|---|---|---|
| 2018 Italian GP, race | FastF1 reports "Failed to load timing data" and the failure repeated on a retry. Results, weather, race control and track status are in the lake; laps are not | Source gap, caught by `session_missing_laps` |
| 2021 Belgian GP, race | Red flags on lap 1 and lap 3. The classification counts 1 lap, the laps table has 3 | Explained by the red flags (not checked against the sporting rules) |
| 2020 Austrian GP, race | The laps table ends at lap 68 for the winner and 67 for most others; the classification and the chequered flag say 71. No red flag in race control | Gap in the source timing laps |
| 2019 Japanese GP, race | The laps table has 53 laps for the winner, the classification 52. Race control logs the chequered flag twice, at lap 53 | Cause unknown |
| 2018 Canadian GP, race | The source classification gives the winner 68 laps, the laps table has 70, race control logs the chequered flag at lap 70 | Cause unknown |
| 2018 Bahrain GP and 2019 German GP, races | Pairwise order agreement 88.2% and 87.2%; lap counts match; no penalty events in race control | Cause unknown |
| 2023 Australian GP, 2024 and 2025 Miami sprints, 2026 Monaco GP | Order agreement 76-90%; race control holds penalty events (1, 6, 1 and 15) | Penalties are the candidate cause; not tested |
| 2026 round 1 race (STR, lap 34) and round 12 sprint (HUL, lap 5) | One car spends 18 and 21 minutes between pit entry and pit exit (1,082 s and 1,270 s). The track status has no red flag, and only one driver has a long lap at those lap numbers | Cause unknown: a long garage stop or a timing artefact. A third long lap (lap 13, 1,070 s, same race) was not flagged by the plausibility check |

For the four lap-count cases I compared the raw Parquet files with the gold tables for the winner: the row counts agree, so the transformation does not lose laps and the disagreement is between the source's timing laps and its classification. The explanations above are readings of this data, not confirmed against official documents.

**Data problems the tests found, and what was done**

- **Garage visits** in qualifying and practice were counted as pit stops (4,466 false warnings). Pit-stop plausibility now applies to race sessions only.
- **Red-flag laps** (Monaco 2024 lap 1) triggered lap-time warnings; laps under a red flag are excluded from that check.
- **Shared drives**: in 1950-1964 a driver could take over another car in the same race, which gave 71 duplicate result keys. `fct_season_result` now numbers the extra drives (`drive_number`) and suffixes the key.
- **Missing driver ids**: FastF1 gives `nan` or an empty id for some drivers (Bearman, Piastri, and practice-only drivers in 2025-2026, 59 session rows). The id is filled from the Jolpica history by season and driver code; drivers who have never raced get a placeholder id `ff1-<code>`, and `driver_id_source` records which rule applied. FastF1 also writes missing names as the text `None None`; those become null.

CI builds the same project on a small synthetic lake (`dbt/ci/make_ci_lake.py`) that contains deliberate bad rows: a duplicate lap, a null lap number, a `nan` driver id, a practice-only driver, a shared drive, and a log that the lake must match. The real data is not needed in CI.

## What the data-quality checks found (raw feed)

| Finding | Handling |
|---|---|
| Car telemetry runs at about 4 Hz (0.24 s median step), with feed gaps of 1.4-1.8 s | Interpolate within gaps; flag long gaps |
| Throttle above 100 in 10-55% of samples in some qualifying sessions | Stored raw, clamped for display |
| Gear above 8 in a handful of samples | Stored raw, counted |
| DRS is always 0 in 2026 (DRS was removed); 2025 uses codes 0, 1, 2, 3, 8, 10, 12, 14 | Shown as n/a for 2026. Open = 10, 12, 14 is an interpretation of the FastF1 documentation |
| Monaco 2026 race has a 3,011 s hole in position data inside the lap window | No usable track map or scrubber for that race |
| Some 2026 sessions (Spain, the relocated Bahrain race) have no circuit corner data | Corner numbers omitted |
| 2026 round 16 is labelled "Bahrain" but was run at Sepang, Malaysia | Circuits are keyed by location, not event name |
| Lap boundaries from timing match GPS within about 0.1 s on almost every lap, but a few Miami laps matched a second place on the reference line | Stricter lap-length check, see the engine section |

## Race-state engine

Goal: for every car at every moment, a running order and the time gap to the car ahead.

**Method.** A reference line is taken from the fastest clean lap of the session. Each GPS sample is projected onto it (nearest point), giving distance around the lap. Progress = laps completed plus the fraction of the current lap. Each lap's fraction is normalised between that driver's official lap-start and lap-end times, so progress is a whole number exactly at the start/finish line. A lap whose GPS span is not within 8% of the track length falls back to time-based progress and is flagged `~` in the app. The gap to the car ahead is the time since that car was at the same point on track.

**Validation.** Order at the start/finish line is correct by construction, so the test uses the two sector timing lines, which the engine never sees: at the moment each driver crosses a sector line, is the engine's running order the same as the order derived from the official sector times?

| Race | Sector 1 line, exact order | Sector 2 line | Baseline: last lap-end position |
|---|---|---|---|
| 2026 Singapore, race | 97.9% | 99.5% | 92.4% / 91.6% |
| 2025 Singapore, race | 95.2% <!-- TODO: re-run with the lap-length check --> | 99.8% | 86.2% / 87.5% |
| 2026 Singapore, sprint (wet) | 91.7% | 89.3% | 82.4% / 83.4% |
| 2026 Miami, race | 96.1% | 96.9% | 88.2% / 87.3% |

Within one place: 98-100% in all four. Median error in predicted sector-line crossing time: 0.04-0.15 s. <!-- TODO: re-run the four races together on the final code and update this table -->

**Known failure modes.** Cars parked in the pit lane under a safety car (timing laps tick on while the car does not move); incidents; lap 1 and the start are untested; races with broken position data.

## Strategy models

**Pit-lane time loss.** Measured as the in-lap plus out-lap time minus two laps at the field's pace on the same laps, so the figure does not depend on the driver. Green-flag stops (n = 557 in the first measurement): median 22.4 s, middle half 20.5-24.7 s. <!-- TODO: re-measure on 2022-2026 -->

**A circuit-specific pit loss did not beat a single global figure** in a held-out test (predict each stop from the other sessions): mean error 3.47 s per circuit against 3.20 s global (235 stops). Safety car and VSC stops could not be measured reliably with this method and are not modelled.

**Rejoin position** after a green-flag stop, predicted from information available at the time, backtested against the real position at the end of the out-lap (661 stops, 46 sessions, 2025-2026): <!-- TODO: re-run on all seasons -->

| Predictor | Exact | Within one place | Mean error (places) |
|---|---|---|---|
| Stay in the same position | 12.9% | 25.6% | 3.53 |
| Lose the typical 3 places | 12.9% | 42.5% | 2.13 |
| **Lap-end times + pit loss** | **48.1%** | **77.9%** | **0.95** |
| Live gaps from the race-state engine | 49.0% | 75.9% | 1.05 |
| Oracle (peeks at the future) | 49.5% | 77.9% | 0.93 |

Using the engine's live gaps was **no more accurate** than lap-end times, so the app keeps the simpler model. Not modelled: other cars pitting in the same window, traffic after the stop, safety cars.

## The app

| Page | What it does |
|---|---|
| Home | Coverage summary |
| Race explorer | Results, lap times with safety car / VSC / red shading and pit markers, tyre strategy, weather, race control |
| Track map | A lap coloured by speed, sector or throttle/brake, with corner numbers |
| Driver comparison | Two laps overlaid against distance with a time-gap trace |
| Season history | 1950-to-now seasons, drivers, teams, circuits |
| Race gaps | Positions, gap to leader, per-lap timing tower |
| Multi-driver telemetry | Up to six drivers, with DRS where it exists |
| Pit window | Predicted rejoin position and the cars around you, with the backtest figures |
| Race scrubber | All cars on the track at any moment; timing tower with sector colours; flags, weather and race control feed; follow drivers; auto-play 0.5x-60x |
| Session timing | Best laps, sectors and ideal lap for qualifying and practice |

## Run it locally

```bash
# environments (kept separate so the app can never disturb a long ingest)
python3.11 -m venv ~/.venvs/f1-pitwall && ~/.venvs/f1-pitwall/bin/pip install -r requirements-ingest.txt
python3.11 -m venv ~/.venvs/f1-app     && ~/.venvs/f1-app/bin/pip install -r requirements-app.txt
python3.11 -m venv ~/.venvs/f1-dbt     && ~/.venvs/f1-dbt/bin/pip install -r requirements-dbt.txt

# ingest one season (race, qualifying, sprints); --dry-run first to see the plan
source ~/.venvs/f1-pitwall/bin/activate
python batch.py --years 2024 --codes R,Q,S,SQ,SS --dry-run
scripts/start_batch.sh --years 2024 --codes R,Q,S,SQ,SS --cooldown 5 --max-waits 30
scripts/status.sh                                             # progress at a glance

# history, checks
python history.py
python report.py && python verify.py

# transform and test with dbt (reads data/lake, writes data/f1_dbt.duckdb)
~/.venvs/f1-dbt/bin/dbt build --project-dir dbt --profiles-dir dbt

# app
~/.venvs/f1-app/bin/streamlit run app/Home.py

# the CI dbt build on a synthetic lake, without any real data
python dbt/ci/make_ci_lake.py ci_lake
F1_LAKE=ci_lake F1_DBT_DB=ci_lake/f1.duckdb ~/.venvs/f1-dbt/bin/dbt build --project-dir dbt --profiles-dir dbt
```

`F1_LAKE` and `F1_DBT_DB` set the lake and dbt database paths (defaults `data/lake` and `data/f1_dbt.duckdb`).

## Repository layout

```
ingest.py        one session -> partitioned Parquet + log record
batch.py         season loop: schedule, skips, rate-limit waits, retries
history.py       Jolpica 1950-now -> Parquet (cached raw responses)
report.py        coverage and problems per season
verify.py        every ingested file against its log record
dbt/             models (silver, gold, reconciliation), tests, macros, CI lake generator
scripts/         start_batch.sh (refuses a second run), status.sh, backfill_track_status.py
app/             Streamlit app: pitwall.py (data access), engine.py (race state), racelib.py, pages/
tests/           unit tests for the race engine, race-control logic, history fetching and app helpers
experiments/     measurement scripts behind the numbers above (run from the repository root)
.github/         CI: ci.yml (tests, lint) and dbt.yml (dbt build on a synthetic lake)
```

## Decisions and dead ends

- **Files instead of a warehouse.** The earlier version used a warehouse trial that expired. This one has nothing to expire. dbt runs on DuckDB for the same reason.
- **Reconciliation metric.** Exact finishing-position match flagged 52 to 64 races, mostly for reasons that were not real problems: post-race penalties change the official order, and retirements are not ranked on the same scale. Comparing classified finishers pairwise, plus lap counts, cut it to four races that deserve a look.
- **Direction-aware map matching made things worse** (Miami exact order fell from 93% to 87%), so it was dropped. A stricter lap-length check helped (93% to 96%).
- **Circuit-specific pit loss did not help** against a single global figure.
- **A live-gap rejoin model was no better** than lap-end times.
- **Streamlit, not a Next.js front end,** for now: all the logic is Python, and a web front end would need a server. A smooth replay would be a static page built from precomputed files; parked.
- **Live timing was dropped:** live car positions need an F1 TV subscription.

## Limitations

- GPS position is already snapped to a common line, so cars cannot be shown side by side.
- The simulated safety car is placed about 500 m ahead of the leader (no safety car GPS exists).
- Red-flag periods end at the next pit-exit-open, safety car, track-clear or race-start message; no message states the end.
- Wind speed is assumed to be in m/s; DRS open codes and the track status code meanings are interpretations of the FastF1 documentation.
- Gaps are lap-timing based at the lines and GPS based in between; accuracy is validated on four races only.
- The dbt layer does not cover the telemetry tables yet, and the safety car, VSC and red-flag logic still lives in the app code (`app/racecontrol.py`), not in a model.
- The reconciliation is against my own ingest of the public feed, so it shows internal consistency and agreement with the official classification, not that the feed itself is right.

## Roadmap

<!-- TODO: edit -->
- Re-run every figure above on the full 2022-2026 dataset, once the practice-session ingest finishes
- Orchestration with Airflow: a calendar-driven DAG, one task per session, a rate-limit pool, retries, then `dbt build` and the reconciliation checks
- Schema checks at ingest time, and a FastAPI layer over the gold tables
- Tyre degradation and undercut models on the gold tables
- Public deployment (hosting undecided)
- A smooth static replay page

## Credits and licence

Built on [FastF1](https://github.com/theOehrly/Fast-F1) (MIT) and the Jolpica API. The design was informed by several open-source F1 projects (f1-race-replay, F1ReplayTiming, undercut-f1); no code from them is used here. <!-- TODO: choose a licence for this repository and add a LICENSE file -->
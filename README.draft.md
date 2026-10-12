# F1 Pitwall

![CI](https://github.com/Pulkit9918/f1-pitwall/actions/workflows/ci.yml/badge.svg)

Race-strategy analytics for Formula 1 on a local Parquet lakehouse: a resumable ingestion pipeline, data-quality checks, a validated race-state engine, strategy models with measured accuracy, and a Streamlit app with a race scrubber.

> **Unofficial.** This project is not associated with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V. Data comes from the public timing feed via [FastF1](https://github.com/theOehrly/Fast-F1) and from the [Jolpica](https://github.com/jolpica/jolpica-f1) Ergast-compatible API. The data is not redistributed in this repository. Personal, non-commercial use.

<!-- TODO: add 3 screenshots to docs/screenshots/ (race scrubber, session timing, pit window) and reference them here -->

## What it does

- **Ingests** race-weekend data one session at a time (laps, sectors, tyres, weather, race control, 4 Hz car telemetry and GPS position) into partitioned Parquet files, and 1950-to-now results and standings from Jolpica.
- **Checks** every file it writes and records per-session quality metrics (value ranges, sampling gaps, circuit metadata) in a manifest.
- **Reconstructs the race** from GPS: a running order and time gaps for every car at any moment, validated against the official sector timing.
- **Models pit stops**: the time lost in the pit lane, and where a driver rejoins, backtested on real stops.
- **Serves it** in a Streamlit app: race explorer, track map, driver and multi-driver telemetry, race gaps, pit window, a race scrubber with auto-play, a session timing screen, and a 1950-to-now history browser.

## Why it exists

Most F1 tools are viewers: they show the timing screen. This project asks a narrower question: *how well can the numbers on that screen be reconstructed and used for strategy decisions, and how do we know?* Every derived number here comes with a test against something independent (official sector timing, real pit stops), and the limits are written down.

## Architecture

```
FastF1 (timing + telemetry) ──┐
                               ├─► ingest.py / batch.py ─► Parquet lake ─► DuckDB ─► Streamlit app
Jolpica API (1950-now) ───────┘      (rate-limit aware,     data/lake/        (read-only)
                                      resumable, one          year=/round=/
                                      session at a time)      session=/
                                           │
                                           └─► _manifest/sessions.jsonl ─► report.py, verify.py
```

| Layer | Choice |
|---|---|
| Language | Python 3.11 |
| Sources | FastF1 3.8 (timing, telemetry), Jolpica (history) |
| Storage | Parquet (zstd), Hive-style partitions, JSONL manifest |
| Query | DuckDB (embedded), pandas, NumPy |
| App | Streamlit 1.65, Plotly |
| Checks | `verify.py` (file vs manifest), `report.py` (coverage and problems), probe scripts |

There is no warehouse server and no orchestrator. That was deliberate: an earlier version of this project ran on a warehouse trial that expired and took its dashboard with it. Everything here runs from files.

## Data

**Coverage** <!-- TODO: update after 2022-2024 ingest finishes -->

| Tier | Years | Content |
|---|---|---|
| Results, standings, drivers, teams, circuits | 1950 - 2026 | Jolpica |
| Full detail | 2022 - 2026 | Races, qualifying, sprints, sprint qualifying: laps, sectors, tyres, weather, race control, car telemetry, GPS position |
| Laps only | Practice sessions | No telemetry |

As of this draft: 2025 and 2026 complete (120 and 85 sessions), 2024 in progress, 2022 and 2023 queued. Total <!-- TODO: final size --> on disk.

**Typical size per session** (zstd Parquet): race with telemetry 9-16 MB, qualifying 4-5 MB, sprint 4-7 MB, practice (laps only) about 0.1 MB.

**Lake layout**

```
data/lake/
  laps/ telemetry_car/ telemetry_pos/ weather/ race_control/ results/
  circuit_corners/ circuit_marshal_sectors/
  track_status/ session_status/           (sessions ingested from 2024 on)
     year=YYYY/round=RR/session=CODE/part.parquet
  history/   results, driver_standings, constructor_standings, drivers, constructors, circuits
  _manifest/sessions.jsonl               one record per ingest attempt
```

Round numbers follow FastF1's numbering for the season. They do not always match the official calendar (the 2026 calendar was changed), so history tables are never joined to sessions by round number.

## Ingestion

- **One session at a time**, written then recorded in the manifest, so an interrupted run loses at most the session in progress.
- **Rate limits.** FastF1 enforces about 500 requests an hour. The batch runner detects the limit, waits, and retries. Observed behaviour: a burst of roughly 40 sessions, then about an hour before the first retry succeeds. A season takes 2-3 hours unattended. <!-- TODO: confirm wording after the 2022-2023 runs -->
- **Resumable.** Finished sessions are skipped; `--retry-failed` redoes failures; `--dry-run` prints the plan.
- **Scratch cache** is deleted after every session, so disk use stays flat.
- **Status per session:** ok, partial or failed, with the reason.
- **A launcher script** refuses to start a second run. (An accidental double launch early on made two runs collide on the shared cache; `verify.py` was written to prove nothing was damaged. It found nothing, and the duplicate manifest lines are harmless.)

## What the data-quality checks found

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
python3.11 -m venv ~/.venvs/f1-pitwall && source ~/.venvs/f1-pitwall/bin/activate
pip install fastf1 pandas pyarrow duckdb requests          # TODO: add requirements files
python3.11 -m venv ~/.venvs/f1-app
~/.venvs/f1-app/bin/pip install streamlit plotly duckdb pandas pyarrow numpy

# ingest one season (race, qualifying, sprints); --dry-run first to see the plan
python batch.py --years 2024 --codes R,Q,S,SQ,SS --dry-run
scripts/start_batch.sh --years 2024 --codes R,Q,S,SQ,SS --cooldown 5 --max-waits 30
scripts/status.sh                                             # progress at a glance

# history, checks, app
python history.py
python report.py && python verify.py
~/.venvs/f1-app/bin/streamlit run app/Home.py
```

## Repository layout

```
ingest.py        one session -> partitioned Parquet + manifest record
batch.py         season loop: schedule, skips, rate-limit waits, retries
history.py       Jolpica 1950-now -> Parquet (cached raw responses)
report.py        coverage and problems per season
verify.py        every ingested file against its manifest record
scripts/         start_batch.sh (refuses a second run), status.sh
app/             Streamlit app: pitwall.py (data access), engine.py (race state), racelib.py, pages/
*_probe.py       measurement scripts behind the numbers above
```

## Decisions and dead ends

- **Files instead of a warehouse.** The earlier version used a warehouse trial that expired. This one has nothing to expire.
- **Direction-aware map matching made things worse** (Miami exact order fell from 93% to 87%), so it was dropped. A stricter lap-length check helped (93% to 96%).
- **Circuit-specific pit loss did not help** against a single global figure.
- **A live-gap rejoin model was no better** than lap-end times.
- **Streamlit, not a Next.js front end,** for now: all the logic is Python, and a web front end would need a server. A smooth replay would be a static page built from precomputed files; parked.
- **Live timing was dropped:** live car positions need an F1 TV subscription.

## Limitations

- GPS position is already snapped to a common line, so cars cannot be shown side by side.
- The simulated safety car is placed about 500 m ahead of the leader (no safety car GPS exists).
- Red-flag periods end at the next pit-exit-open, safety car, track-clear or race-start message; no message states the end.
- Wind speed is assumed to be in m/s; DRS open codes are an interpretation of the documentation.
- Gaps are lap-timing based at the lines and GPS based in between; accuracy is validated on four races only.

## Roadmap

<!-- TODO: edit -->
- Re-run every figure above on the full 2022-2026 dataset
- Public deployment (hosting undecided)
- A smooth static replay page
- CI and tests (in progress)

## Credits and licence

Built on [FastF1](https://github.com/theOehrly/Fast-F1) (MIT) and the Jolpica API. The design was informed by several open-source F1 projects (f1-race-replay, F1ReplayTiming, undercut-f1); no code from them is used here. <!-- TODO: choose a licence for this repository and add a LICENSE file -->

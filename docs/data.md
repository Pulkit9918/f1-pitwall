# Data and ingestion

[Back to the README](../README.md)

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
- **Rate limits.** FastF1 limits itself to about 500 requests an hour (200 for ergast.com hosts), counted in a sliding window inside the Python process; it raises an error when the window is full. The batch runner detects this, waits in 5-minute steps (up to 30 in a row; the first runs used 15-minute steps), and retries. Observed over 15 waits in the full ingest: a burst of 20-82 sessions (median 40), then a wait of 17-61 minutes (median 50) before ingesting resumes. Runs of 60, 103 and 106 sessions took 1 h 13 min, 3 h 35 min and 2 h 40 min unattended; the last overnight run (332 sessions, 2022-2024 practice plus 2018-2021 races and qualifying) took 7 h 39 min, about six hours of it waiting. The median session takes 16 seconds to ingest, so the rate limit, not the work, sets the wall-clock time.
- **Resumable.** Finished sessions are skipped; `--retry-failed` redoes failures; `--dry-run` prints the plan.
- **Scratch cache** is deleted after every session, so disk use stays flat.
- **Status per session:** ok, partial or failed, with the reason.
- **Data contracts** (`contracts.py`, pandera) are checked on every table before it is written. Hard rules (required columns, key columns not null, numeric columns numeric) fail the table, which is then recorded as failed in the ingest log. Soft rules (plausible value ranges, known code sets) never block a write: findings are stored on the log record and printed in the session report, and a rule only fires when more than its tolerance of the rows break it. The rules were derived from a profile of the whole lake, not guessed, and `scripts/check_contracts.py` validates the eight main tables across the whole lake against them: no hard failures, and no soft findings once two rules were set from the data (throttle is 0-100 or the code 104; gear above 8 is tolerated up to 0.5% of rows, see the raw-feed findings below).
- **A launcher script** refuses to start a second run. (An accidental double launch early on made two runs collide on the shared cache; `verify.py` was written to prove nothing was damaged. It found nothing, and the duplicate log lines are harmless.)
- **Backfill.** `scripts/backfill_track_status.py` adds `track_status` and `session_status` to sessions that were ingested before those tables existed (206 sessions in 2019, 2025 and 2026). It only writes the missing tables, skips sessions that already have them, and logs to `backfill.jsonl`.

## What the data-quality checks found (raw feed)

| Finding | Handling |
|---|---|
| Car telemetry runs at about 4 Hz (0.24 s median step), with feed gaps of 1.4-1.8 s | Interpolate within gaps; flag long gaps |
| Throttle reads 104 in about one sample in five (19-25% of samples per season; every one of the 269 sessions with telemetry has some, up to 65% of a session). 104 is the only value above 100, so it looks like a code, not a percentage; its meaning is not verified | Stored raw, clamped to 100 for display, accepted by the data contract as the code 104 |
| Gear above 8 (values from 9 up to 128) in a tiny share of samples: 96 of 269 sessions, median 0.01% of the session's samples, worst 0.17% | Stored raw, counted; the data contract tolerates up to 0.5% of rows |
| DRS is always 0 in 2026 (DRS was removed); 2025 uses codes 0, 1, 2, 3, 8, 10, 12, 14. Across the whole lake the codes seen are 0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15 | Shown as n/a for 2026. Open = 10, 12, 14 is an interpretation of the FastF1 documentation |
| Monaco 2026 race: GPS position data covers only 5.1% of the race time (dense for roughly the first two laps, then a few sparse samples up to 6,743 s, while the laps run to 11,975 s). Lap timing also has a 2,264 s gap between laps 67 and 68, cause not checked | No usable track map or scrubber for that race. It is the only race or sprint in the lake affected (checked by counting 10 s bins with samples in every R and S session) |
| Some 2026 sessions (Spain, the relocated Bahrain race) have no circuit corner data | Corner numbers omitted |
| 2026 round 16 is labelled "Bahrain" but was run at Sepang, Malaysia | Circuits are keyed by location, not event name |
| Lap boundaries from timing match GPS within about 0.1 s on almost every lap, but a few Miami laps matched a second place on the reference line | Stricter lap-length check, see the engine section |

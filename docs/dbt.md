# The dbt layer, reconciliation and known data gaps

[Back to the README](../README.md)

## Transformation layer (dbt)

Run from the repository root: `dbt build --project-dir dbt --profiles-dir dbt`. The models read the Parquet lake in place and write a DuckDB file under `data/`.

| Layer | Models | What happens |
|---|---|---|
| Sources | `lake.*`, `history.*`, `manifest.runs` | Parquet files and the JSON ingest log, with not-null checks on key columns |
| Silver (11) | laps, results, race control, weather, track status, sessions, session clock, three history tables, ingest runs | Typed columns, duplicates removed, explicit keys such as `session_key = 2025-R07-R` |
| Gold (42) | `dim_circuit`, `dim_constructor`, `dim_driver`, `dim_historical_driver`, `dim_layout_length`, `dim_session`, `dim_session_circuit`, `fct_circuit_degradation`, `fct_circuit_pit_loss`, `fct_constructor_points_progression`, `fct_constructor_standing`, `fct_driver_standing`, `fct_ingest_session`, `fct_ingest_summary`, `fct_lap`, `fct_lap_gap`, `fct_lap_position`, `fct_lap_sample`, `fct_lap_sample_total`, `fct_lap_sector`, `fct_lap_trace`, `fct_lap_trace_lap`, `fct_pit_loss`, `fct_pit_loss_neutralised`, `fct_pit_loss_ratio`, `fct_pit_now`, `fct_pit_now_check`, `fct_pit_prediction_check`, `fct_pit_prediction_heldout`, `fct_pit_prediction_heldout_score`, `fct_pit_prediction_score`, `fct_pit_stop`, `fct_points_progression`, `fct_race_control_event`, `fct_race_control_period`, `fct_result`, `fct_season_result`, `fct_session_weather`, `fct_stint`, `fct_stint_degradation`, `fct_stop_battle`, `fct_track_status_period` | Facts and dimensions that the exporters, the API and the app read |
| Reconciliation (4) | `rec_finish_order`, `rec_lake_vs_manifest`, `rec_weekend_coverage`, `rec_telemetry_coverage` | The pipeline checked against official results and against its own log; telemetry checked against the laps table |

The last build had 258 steps: 57 models, 1 seed and 200 tests. Result: 251 passed, 7 warnings, 0 errors. The warnings are `finish_order_reconciles`, `lap_sector_sum_matches_lap`, `lap_trace_coverage`, `pit_lane_time_plausible`, `pit_loss_plausible`, `session_missing_laps`, `telemetry_coverage_flags`. 26 gold models have enforced contracts (declared column names and types that the build checks).

**Race control periods.** `fct_race_control_period` holds safety car, VSC and red flag periods read from the wording of the race control messages. It is a SQL version of `build_periods` in `app/racecontrol.py`, which stays as the reference. Over the 269 sessions that have a session clock it gives 264 periods, identical to the Python (`experiments/rc_periods_reconcile.py`). The 438 older sessions get periods in UTC only and are not compared against the Python on real data. The session clock (`silver_session_clock`) comes from lap start dates and equals the position-sample clock the app uses in all 269 sessions (`experiments/rc_offset.py`). Messages in the same second are common (478 of 707 sessions), but ordering them differently changed no period (`experiments/rc_ties.py`). Against the separate track status feed, 262 of 264 periods start within 5 s of a matching change (median 0.3 s). The two exceptions: a VSC message about ten minutes after the last lap of the 2022 French GP, and a second "safety car deployed" message 8 s after "in this lap" in the 2026 British GP, which starts a new period 540 s after the nearest status change, inside what the status feed shows as one continuous safety car. The cause of either is not known.

**Telemetry coverage.** The two telemetry tables (139.5 million car rows and 142.2 million position rows over 269 sessions) are declared as sources, and `rec_telemetry_coverage` checks them against the laps table in 1.4 s. Telemetry is expected for every session except practice: all 269 qualifying, race and sprint sessions from 2022 on have both tables, and none of the 276 practice sessions has either. The median sample rate is 3.74 Hz for car data and 3.82 Hz for position. In 23 sessions telemetry has more drivers than the laps table; the results table accounts for 19 of the 30 extra drivers (16 did not start, one retired, one withdrew, one had an accident), 9 are in qualifying sessions where the status is blank, and 2 are in races with a blank status. The test `telemetry_coverage_flags` warns on two sessions (listed under known data gaps). Its tolerances (60 s, 3 Hz) were set just outside the range seen in this lake, so they say what is unusual here, not what is wrong in general.

**Documentation.** Every model and every column has a description, written from the model SQL; where a meaning could not be verified, the description says so. `dbt docs generate` builds the catalog and the lineage graph (`dbt docs serve --project-dir dbt --profiles-dir dbt` to browse it). `scripts/doc_coverage.py --check` reads dbt's own artifacts and fails if any model, or any column of a gold model, lacks a description. CI runs it after the synthetic-lake build, so the coverage cannot slip silently.

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
| 2024 British GP, race (ZHO, lap 26) | A stop with a measured pit loss of 1.3 s, below the 5 s plausibility floor. The driver's median gap to the field over the eight laps around the stop was 6.8 s, which the method subtracts from the in-lap and the out-lap | Cause unknown (`pit_loss_plausible`). Changing track conditions around the stop are a candidate; not tested |
| 2026 Monaco GP, race | Position telemetry ends 5,233 s (87 minutes) before the last lap and averages 1.2 samples per second against about 3.8 elsewhere; car telemetry is complete | Source gap, caught by `telemetry_coverage_flags`; cause unknown |
| 2023 round 17, sprint shootout | Car and position telemetry both start 78 s after the first lap began | Source gap, caught by `telemetry_coverage_flags`; cause unknown |
| 2022 rounds 18 and 21, 2023 round 16, 2024 round 4 (nine replays) | The replay export drops the corner numbers or the marshal sectors: the corner coordinates are far from the drawn circuit (round 21), or the marshal posts do not run once around the lap in order (the others) | Not investigated |

For the four lap-count cases I compared the raw Parquet files with the gold tables for the winner: the row counts agree, so the transformation does not lose laps and the disagreement is between the source's timing laps and its classification. The explanations above are readings of this data, not confirmed against official documents.

**Data problems the tests found, and what was done**

- **Garage visits** in qualifying and practice were counted as pit stops (4,466 false warnings). Pit-stop plausibility now applies to race sessions only.
- **Red-flag laps** (Monaco 2024 lap 1) triggered lap-time warnings; laps under a red flag are excluded from that check.
- **Shared drives**: in 1950-1964 a driver could take over another car in the same race, which gave 71 duplicate result keys. `fct_season_result` now numbers the extra drives (`drive_number`) and suffixes the key.
- **Missing driver ids**: FastF1 gives `nan` or an empty id for some drivers (Bearman, Piastri, and practice-only drivers in 2025-2026, 59 session rows). The id is filled from the Jolpica history by season and driver code; drivers who have never raced get a placeholder id `ff1-<code>`, and `driver_id_source` records which rule applied. FastF1 also writes missing names as the text `None None`; those become null.

CI builds the same project on a small synthetic lake (`dbt/ci/make_ci_lake.py`) that contains deliberate bad rows: a duplicate lap, a null lap number, a `nan` driver id, a practice-only driver, a shared drive, and a log that the lake must match. The real data is not needed in CI.

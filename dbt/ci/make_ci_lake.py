"""Write a tiny synthetic Parquet lake with the real column names and types, for CI and local checks.

usage (from the repository root):  python dbt/ci/make_ci_lake.py [output_dir]
Default output: ci_lake/   Then:   F1_LAKE=ci_lake F1_DBT_DB=ci_lake/f1.duckdb dbt build --project-dir dbt --profiles-dir dbt
Only needs the duckdb package. One 2099 race (3 drivers, 6 laps, one pit stop, one safety car) and one qualifying.
"""

import shutil
import sys
from pathlib import Path

import duckdb

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "ci_lake")
if OUT.exists():
    shutil.rmtree(OUT)

LAPS_COLS = (
    "event VARCHAR, Driver VARCHAR, DriverNumber VARCHAR, LapNumber DOUBLE, Stint DOUBLE, "
    "SpeedI1 DOUBLE, SpeedI2 DOUBLE, SpeedFL DOUBLE, SpeedST DOUBLE, IsPersonalBest BOOLEAN, "
    "Compound VARCHAR, TyreLife DOUBLE, FreshTyre BOOLEAN, Team VARCHAR, LapStartDate TIMESTAMP_NS, "
    "TrackStatus VARCHAR, Position DOUBLE, Deleted BOOLEAN, DeletedReason VARCHAR, "
    "FastF1Generated BOOLEAN, IsAccurate BOOLEAN, Time_s DOUBLE, LapTime_s DOUBLE, "
    "PitOutTime_s DOUBLE, PitInTime_s DOUBLE, Sector1Time_s DOUBLE, Sector2Time_s DOUBLE, "
    "Sector3Time_s DOUBLE, Sector1SessionTime_s DOUBLE, Sector2SessionTime_s DOUBLE, "
    "Sector3SessionTime_s DOUBLE, LapStartTime_s DOUBLE")
RESULTS_COLS = (
    "event VARCHAR, DriverNumber VARCHAR, BroadcastName VARCHAR, Abbreviation VARCHAR, "
    "DriverId VARCHAR, TeamName VARCHAR, TeamColor VARCHAR, TeamId VARCHAR, FirstName VARCHAR, "
    "LastName VARCHAR, FullName VARCHAR, HeadshotUrl VARCHAR, CountryCode VARCHAR, Position DOUBLE, "
    "ClassifiedPosition VARCHAR, GridPosition DOUBLE, Status VARCHAR, Points DOUBLE, Laps DOUBLE, "
    "Q1_s DOUBLE, Q2_s DOUBLE, Q3_s DOUBLE, Time_s DOUBLE")
RC_COLS = ("event VARCHAR, Time TIMESTAMP_NS, Category VARCHAR, Message VARCHAR, Status VARCHAR, "
           "Flag VARCHAR, Scope VARCHAR, Sector DOUBLE, RacingNumber VARCHAR, Lap DOUBLE")

DRIVERS = {"AAA": (1, "aaa_driver", 90.0), "BBB": (2, "bbb_driver", 91.0), "CCC": (3, "ccc_driver", 95.0)}
N_LAPS = 6

con = duckdb.connect()


def write(table, session, cols, rows, year=2099, rnd="01"):
    n = len(cols.split(","))
    con.execute(f"CREATE OR REPLACE TABLE t ({cols})")
    if rows:
        con.executemany(f"INSERT INTO t VALUES ({','.join(['?'] * n)})", rows)
    d = OUT / table / f"year={year}" / f"round={rnd}" / f"session={session}"
    d.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY t TO '{d / 'part.parquet'}' (FORMAT parquet)")


# ---- race: AAA leads, BBB second, CCC third; BBB pits at the end of lap 3 ----
lap_rows = []
for name, (num, _id, lt) in DRIVERS.items():
    t_end = 0.0
    stint = 1
    for n in range(1, N_LAPS + 1):
        pit_in = pit_out = None
        status = "4" if n == 5 else "1"
        if name == "BBB" and n == 3:
            pit_in = t_end + lt + 18.0 - 20.0
        if name == "BBB" and n == 4:
            pit_out = t_end + 8.0
            stint = 2
        this_lt = lt + (20.0 if name == "BBB" and n in (3, 4) else 0.0)
        t_end += this_lt
        pos = {"AAA": 1, "BBB": 2, "CCC": 3}[name]
        lap_rows.append((
            "Synth Grand Prix", name, str(num), float(n), float(stint), None, None, None, None, False,
            "MEDIUM" if stint == 1 else "HARD", float(n), True, "Test", None, status, float(pos), False, None,
            False, True, t_end, this_lt, pit_out, pit_in, this_lt / 3, this_lt / 3, this_lt / 3,
            t_end - 2 * this_lt / 3, t_end - this_lt / 3, t_end, t_end - this_lt))
# one duplicate row (same lap twice) and one row with no lap number, both to be removed in silver
lap_rows.append(lap_rows[0])
lap_rows.append(("Synth Grand Prix", "AAA", "1", None, 1.0) + (None,) * 4 + (False, "MEDIUM", 1.0, True, "Test",
                 None, "1", 1.0, False, None, False, True, 1.0, 90.0, None, None, 30.0, 30.0, 30.0,
                 1.0, 1.0, 1.0, 1.0))
write("laps", "R", LAPS_COLS, lap_rows)

res_rows = []
for pos, (name, (num, did, _lt)) in enumerate(DRIVERS.items(), start=1):
    res_rows.append(("Synth Grand Prix", str(num), name, name, did, "Test Team", "ffffff", "test", name,
                     name, name + " Driver", "", "AUS", float(pos), str(pos), float(pos), "Finished",
                     float(25 - 7 * (pos - 1)), float(N_LAPS), None, None, None, 600.0 + pos))
# patch_dbt_6: FastF1 gave CCC no driver id ('nan'); silver_results must fill it from the history
res_rows = [r[:4] + ("nan",) + r[5:] if r[3] == "CCC" else r for r in res_rows]
write("results", "R", RESULTS_COLS, res_rows)

rc_rows = [
    ("Synth Grand Prix", "2099-01-01 12:10:00", "SafetyCar", "SAFETY CAR DEPLOYED", None, None, None, None, None, 5.0),
    ("Synth Grand Prix", "2099-01-01 12:12:00", "Flag", "TRACK CLEAR", None, "CLEAR", "Track", None, None, 6.0),
    ("Synth Grand Prix", "2099-01-01 12:13:00", "Other",
     "CAR 2 (BBB) TIME 1:30.000 DELETED - TRACK LIMITS AT TURN 3 LAP 6 12:12:50", None, None, None, None, None, 6.0),
    ("Synth Grand Prix", "2099-01-01 12:14:00", "Flag", "CHEQUERED FLAG", None, "CHEQUERED", None, None, None, 6.0),
]
write("race_control", "R", RC_COLS, rc_rows)

# ---- qualifying: results and laps only ----
q_laps = []
for name, (num, _id, lt) in DRIVERS.items():
    for n in (1, 2, 3):
        q_laps.append((
            "Synth Grand Prix", name, str(num), float(n), 1.0, None, None, None, None, False, "SOFT",
            float(n), True, "Test", None, "1", None, False, None, False, True, n * lt, lt - 5.0, None, None,
            (lt - 5.0) / 3, (lt - 5.0) / 3, (lt - 5.0) / 3, 0.0, 0.0, 0.0, (n - 1) * lt))
write("laps", "Q", LAPS_COLS, q_laps)
q_res = [("Synth Grand Prix", str(num), name, name, did, "Test Team", "ffffff", "test", name, name,
          name + " Driver", "", "AUS", float(pos), str(pos), None, "", 0.0, None, 80.0 + pos, 79.0 + pos,
          78.0 + pos, None)
         for pos, (name, (num, did, _lt)) in enumerate(DRIVERS.items(), start=1)]
# patch_dbt_7: a practice-only driver with no id and the name 'None None' (becomes the surrogate id ff1-zzz)
q_res.append(("Synth Grand Prix", "99", "ZZZ", "ZZZ", "nan", "Test Team", "ffffff", "test", "None", "None",
              "None None", "", "AUS", 4.0, "4", None, "", 0.0, None, 85.0, 84.0, 83.0, None))
write("results", "Q", RESULTS_COLS, q_res)
write("race_control", "Q", RC_COLS, [])

# ---- weather, track status and history (added by patch_dbt_5) ----
W_COLS = ("event VARCHAR, AirTemp DOUBLE, Humidity DOUBLE, Pressure DOUBLE, Rainfall BOOLEAN, "
          "TrackTemp DOUBLE, WindDirection BIGINT, WindSpeed DOUBLE, Time_s DOUBLE")
write("weather", "R", W_COLS, [("Synth Grand Prix", 25.0 + i, 50.0, 1010.0, i == 3, 35.0 + i, 90, 2.0 + i, 60.0 * i)
                               for i in range(5)])
write("weather", "Q", W_COLS, [("Synth Grand Prix", 24.0, 55.0, 1010.0, False, 33.0, 80, 1.0, 30.0)])
TS_COLS = "event VARCHAR, Status VARCHAR, Message VARCHAR, Time_s DOUBLE"
write("track_status", "R", TS_COLS, [("Synth Grand Prix", "1", "AllClear", 0.0),
                                     ("Synth Grand Prix", "4", "SCDeployed", 370.0),
                                     ("Synth Grand Prix", "1", "AllClear", 450.0)])

HIST = OUT / "history"
HIST.mkdir(parents=True, exist_ok=True)


def hist(name, cols, rows):
    n = len(cols.split(","))
    con.execute(f"CREATE OR REPLACE TABLE h ({cols})")
    con.executemany(f"INSERT INTO h VALUES ({','.join(['?'] * n)})", rows)
    con.execute(f"COPY h TO '{HIST / (name + '.parquet')}' (FORMAT parquet)")


hist("circuits", "circuit_id VARCHAR, circuit_name VARCHAR, locality VARCHAR, country VARCHAR, lat DOUBLE, long DOUBLE",
     [("synth", "Synth Circuit", "Synthville", "Australia", -37.8, 144.9)])
hist("constructors", "constructor_id VARCHAR, name VARCHAR, nationality VARCHAR", [("test", "Test Team", "Australian")])
hist("drivers", "driver_id VARCHAR, given_name VARCHAR, family_name VARCHAR, date_of_birth VARCHAR, "
     "nationality VARCHAR, code VARCHAR, number DOUBLE",
     [(did, name, "Driver", "1990-01-01", "Australian", name, float(num)) for name, (num, did, _lt) in DRIVERS.items()])
hist("results", "season BIGINT, round BIGINT, race_name VARCHAR, date VARCHAR, circuit_id VARCHAR, driver_id VARCHAR, "
     "code VARCHAR, driver VARCHAR, number DOUBLE, constructor_id VARCHAR, constructor VARCHAR, grid DOUBLE, "
     "position DOUBLE, position_text VARCHAR, points DOUBLE, laps DOUBLE, status VARCHAR, time_ms DOUBLE, "
     "fastest_rank DOUBLE, fastest_lap DOUBLE, fastest_time VARCHAR",
     [(2099, 1, "Synth Grand Prix", "2099-01-01", "synth", did, name, name + " Driver", float(num), "test",
       "Test Team", float(num), float(num), str(num), float(25 - 7 * (num - 1)), 6.0, "Finished", 600000.0 + num,
       float(num), 3.0, "1:30.000") for name, (num, did, _lt) in DRIVERS.items()])
# patch_dbt_6: CCC also drove a second car in the same race (a shared drive)
con.execute("INSERT INTO h SELECT * REPLACE (9.0 AS grid, 12.0 AS position, '12' AS position_text, "
            "0.0 AS points, 2.0 AS laps, 'Engine' AS status, NULL AS time_ms, NULL AS fastest_rank, "
            "NULL AS fastest_lap, NULL AS fastest_time) FROM h WHERE code = 'CCC'")
con.execute(f"COPY h TO '{HIST / 'results.parquet'}' (FORMAT parquet)")

hist("driver_standings", "season BIGINT, round BIGINT, position DOUBLE, position_text VARCHAR, points DOUBLE, "
     "wins DOUBLE, driver_id VARCHAR, driver VARCHAR, constructor VARCHAR",
     [(2099, 1, float(num), str(num), float(25 - 7 * (num - 1)), 1.0 if num == 1 else 0.0, did, name + " Driver",
       "Test Team") for name, (num, did, _lt) in DRIVERS.items()])
hist("constructor_standings", "season BIGINT, round BIGINT, position DOUBLE, points DOUBLE, wins DOUBLE, "
     "constructor_id VARCHAR, constructor VARCHAR, nationality VARCHAR",
     [(2099, 1, 1.0, 50.0, 1.0, "test", "Test Team", "Australian")])

# patch_dbt_8: an ingest log that matches the synthetic files. The race's track_status is only in the backfill log.
import json

MAN = OUT / "_manifest"
MAN.mkdir(parents=True, exist_ok=True)
found = {}
for p in sorted(OUT.glob("*/year=*/round=*/session=*/part.parquet")):
    table = p.parts[-5]
    key = (int(p.parts[-4].split("=")[1]), int(p.parts[-3].split("=")[1]), p.parts[-2].split("=")[1])
    found.setdefault(key, {})[table] = con.execute(f"select count(*) from read_parquet('{p}')").fetchone()[0]
with open(MAN / "sessions.jsonl", "w", encoding="utf-8") as f, open(MAN / "backfill.jsonl", "w", encoding="utf-8") as g:
    for (y, r, c), tabs in found.items():
        logged = {t: {"rows": n, "bytes": 1000} for t, n in tabs.items() if not (c == "R" and t == "track_status")}
        f.write(json.dumps({"year": y, "requested_event": r if c == "R" else "Synth Grand Prix", "session": c,
                            "fastf1_version": "synthetic", "ingested_at": "2099-01-02T03:04:05.123456+00:00",
                            "with_telemetry": False, "round": r, "event": "Synth Grand Prix", "tables": logged,
                            "status": "ok", "warnings": [], "seconds": 1.5}) + "\n")
        if c == "R":
            g.write(json.dumps({"year": y, "round": r, "session": c, "kind": "backfill",
                                "at": "2099-01-03T00:00:00+00:00", "status": "ok", "seconds": 1.0,
                                "tables": {"track_status": {"rows": tabs["track_status"], "bytes": 1000}}}) + "\n")

print(f"Wrote a synthetic lake to {OUT}/")

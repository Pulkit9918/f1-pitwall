"""Tests for scripts/export_replay.py on a small mock lake that has the same columns as the real one."""
import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
duckdb = pytest.importorskip("duckdb")

SPEC = importlib.util.spec_from_file_location("export_replay", Path(__file__).resolve().parents[1] / "scripts" / "export_replay.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules["export_replay"] = mod
SPEC.loader.exec_module(mod)

BASE_EPOCH = 1_750_000_000.0   # wall clock at session time 0
DRIVERS = {1: "VER", 4: "NOR", 16: "LEC", 44: "HAM"}
LAPS = 5
# team name and colour as the lake has them
TEAMS = {"VER": ("Red Bull", "3671c6"), "NOR": ("McLaren", "zzz"), "LEC": ("Ferrari", "#E80020"), "HAM": ("Ferrari", None)}


def track(theta, figure_eight):
    if figure_eight:   # crosses itself, like Suzuka
        return 4000 * math.sin(theta), 2000 * math.sin(2 * theta)
    return 4000 * math.cos(theta), 2500 * math.sin(theta)


def write_parquet(con, path, ddl, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"create or replace table tmp ({ddl})")
    con.executemany(f"insert into tmp values ({','.join('?' * len(ddl.split(',')))})", rows)
    con.execute(f"copy tmp to '{path}' (format parquet)")


def make_lake(root, figure_eight=False, year=2026, rnd=6, code="R", with_car=True, pre_laps=0):
    root = Path(root)
    lake, db = root / "lake", root / "f1_dbt.duckdb"
    con = duckdb.connect()
    key = f"{year}-R{rnd:02d}-{code}"
    pos, car, laps = [], [], []
    for n, (num, d) in enumerate(DRIVERS.items()):
        period = 60.0 + n * 0.8
        start_theta = -0.04 - 0.02 * n            # on the grid, just before the line
        pre = pre_laps * period        # laps driven before the race start (out lap, formation lap)
        t = 0.0
        while t <= LAPS * period + 20 + pre:
            theta = start_theta + 2 * math.pi * (t - pre) / period
            x, y = track(theta, figure_eight)
            pos.append((num, t, x + (n % 3) * 15, y, 0, "OnTrack", rnd, code, year, BASE_EPOCH + t))
            if with_car:
                car.append((num, t, 200 + n, 5, 80, 8, False, rnd, code, year))
            t += 0.5
        # lap n ends when theta reaches 2*pi*n
        prev_end = pre
        for lap in range(1, LAPS + 1):
            end = pre + (2 * math.pi * lap - start_theta) * period / (2 * math.pi)
            laps.append((key, d, lap, prev_end, end - prev_end, end, True))
            prev_end = end
    base = f"{lake}/telemetry_pos/year={year}/round={rnd}/session={code}/part-0.parquet"
    Path(base).parent.mkdir(parents=True, exist_ok=True)
    con.execute("create or replace table tmp (event varchar, driver_number smallint, date_utc timestamp, "
                "session_time_s float, x integer, y integer, z integer, status varchar)")
    con.executemany("insert into tmp values ('Test', ?, to_timestamp(?)::timestamp, ?, ?, ?, ?, ?)", [
        (r[0], r[9], r[1], int(r[2]), int(r[3]), r[4], r[5]) for r in pos])
    con.execute(f"copy tmp to '{base}' (format parquet)")
    if with_car:
        cbase = f"{lake}/telemetry_car/year={year}/round={rnd}/session={code}/part-0.parquet"
        write_parquet(con, cbase, "driver_number smallint, session_time_s float, speed smallint, ngear smallint, "
                      "throttle smallint, drs smallint, rpm smallint, brake boolean",
                      [(r[0], r[1], r[2], r[3], r[4], r[5], 9000, r[6]) for r in car])
    write_parquet(con, f"{lake}/results/year={year}/round={rnd}/session={code}/part-0.parquet",
                  "DriverNumber varchar, Abbreviation varchar, TeamName varchar, TeamColor varchar",
                  [(str(n), d, TEAMS[d][0], TEAMS[d][1]) for n, d in DRIVERS.items()])
    write_parquet(con, f"{lake}/weather/year={year}/round={rnd}/session={code}/part-0.parquet",
                  "AirTemp double, TrackTemp double, Humidity double, Rainfall boolean, WindSpeed double, "
                  "WindDirection bigint, Time_s double",
                  [(20.0 + i, 30.0 + i, 55.0, i >= 3, 2.0, 180, 60.0 * i) for i in range(5)])
    write_parquet(con, f"{lake}/race_control/year={year}/round={rnd}/session={code}/part-0.parquet",
                  'Time timestamp, Category varchar, Message varchar, Flag varchar, "Lap" bigint, RacingNumber varchar',
                  [(duckdb.sql(f"select to_timestamp({BASE_EPOCH + 100})::timestamp").fetchone()[0], "Flag", "YELLOW IN TURN 3",
                    "YELLOW", 2, None),
                   (duckdb.sql(f"select to_timestamp({BASE_EPOCH + 130})::timestamp").fetchone()[0], "Other",
                    "CAR 4 (NOR) TIME 1:30.000 DELETED", "", 3, "4"),
                   (duckdb.sql(f"select to_timestamp({BASE_EPOCH + 999999})::timestamp").fetchone()[0], "Other",
                    "TOO LATE", "", 3, None)])
    write_parquet(con, f"{lake}/track_status/year={year}/round={rnd}/session={code}/part-0.parquet",
                  "Status varchar, Message varchar, Time_s double",
                  [("1", "AllClear", 0.0), ("2", "Yellow", 100.0), ("1", "AllClear", 110.0)])
    g = duckdb.connect(str(db))
    g.execute("create schema gold")
    g.execute("create table gold.dim_session_circuit(session_key varchar, year bigint, round bigint, session_code varchar)")
    g.execute("insert into gold.dim_session_circuit values (?, ?, ?, ?)", [key, year, rnd, code])
    g.execute("create table gold.fct_lap(session_key varchar, driver_code varchar, lap_number integer, "
              "lap_start_time_s double, lap_time_s double, time_s double, is_clean_lap boolean)")
    g.executemany("insert into gold.fct_lap values (?, ?, ?, ?, ?, ?, ?)", laps)
    g.close()
    return lake, db, key


def decode(entry):
    return np.concatenate([[entry["p0"]], entry["p0"] + np.cumsum(entry["dp"])]) / 10000.0


@pytest.mark.parametrize("figure_eight,pre_laps", [(False, 0), (True, 0), (False, 2), (True, 3)])
def test_progress_follows_the_laps(tmp_path, figure_eight, pre_laps):
    # pre_laps: laps the cars drive before the race start; progress must still be zero at the start of lap 1
    lake, db, key = make_lake(tmp_path, figure_eight, pre_laps=pre_laps)
    out = tmp_path / "out"
    lines = []
    r = mod.export(db, lake, out, log=lines.append)
    assert r["written"] == 1 and not r["skipped"]
    doc = json.loads((out / f"{key}.json").read_text())
    assert doc["kind"] == "race" and doc["step"] == 1.0 and len(doc["track"]["pts"]) == mod.DRAW_POINTS
    assert set(doc["drivers"]) == set(DRIVERS.values())
    for code, e in doc["drivers"].items():
        cum = decode(e)
        assert len(cum) == doc["n"]
        assert cum[0] < 0                       # on the grid, behind the line
        assert (np.diff(cum[e["a"]:e["b"] + 1]) > -0.02).all(), code   # never jumps back, even where a figure-8 crosses itself
        assert cum[e["b"]] == pytest.approx(LAPS + (20 / (60 + 0.8 * list(DRIVERS.values()).index(code))), abs=0.1)
    # the built-in check agrees on every car
    assert any("agrees with the lap count for 4 of 4 cars" in s for s in lines), lines
    # the outline fits the box and the drawn points stay inside it
    xs = [p[0] for p in doc["track"]["pts"]]
    ys = [p[1] for p in doc["track"]["pts"]]
    assert max(doc["track"]["w"], doc["track"]["h"]) == pytest.approx(mod.VIEW, abs=0.2)
    assert 0 <= min(xs) and max(xs) <= doc["track"]["w"] + 0.2 and 0 <= min(ys) and max(ys) <= doc["track"]["h"] + 0.2


def test_telemetry_weather_messages_and_status(tmp_path):
    lake, db, key = make_lake(tmp_path)
    out = tmp_path / "out"
    mod.export(db, lake, out)
    doc = json.loads((out / f"{key}.json").read_text())
    e = doc["drivers"]["NOR"]
    assert e["spd"][50] == 201 and e["gear"][50] == 5 and e["thr"][50] == 80 and e["drs"][50] == 8 and e["brk"][50] == 0
    assert doc["weather"]["t"] == [0.0, 60.0, 120.0, 180.0, 240.0] and doc["weather"]["rain"] == [0, 0, 0, 1, 1]
    # wall-clock messages become session seconds; the one far outside the session is dropped
    assert [m[0] for m in doc["messages"]] == [100.0, 130.0]
    assert doc["messages"][0][1:] == ["Flag", "YELLOW", 2, "YELLOW IN TURN 3", None]
    assert doc["messages"][1][5] == "NOR"
    assert doc["track_status"] == [[0.0, "1", "AllClear"], [100.0, "2", "Yellow"], [110.0, "1", "AllClear"]]


def test_session_without_car_data_still_exports(tmp_path):
    lake, db, key = make_lake(tmp_path, with_car=False)
    mod.export(db, lake, tmp_path / "out")
    doc = json.loads((tmp_path / "out" / f"{key}.json").read_text())
    assert "spd" not in doc["drivers"]["VER"]


def test_index_skip_and_force(tmp_path):
    lake, db, key = make_lake(tmp_path)
    out = tmp_path / "out"
    mod.export(db, lake, out)
    index = json.loads((out / "index.json").read_text())
    assert index["generator"] == "export_replay" and [s["key"] for s in index["sessions"]] == [key]
    (out / f"{key}.json").write_text(json.dumps({"kind": "race", "n": 7, "drivers": {}}))
    mod.export(db, lake, out)                   # existing file is kept
    assert json.loads((out / f"{key}.json").read_text())["n"] == 7
    mod.export(db, lake, out, force=True)       # and rewritten when asked
    assert json.loads((out / f"{key}.json").read_text())["n"] > 7


def test_sessions_outside_the_request_and_missing_telemetry(tmp_path):
    lake, db, key = make_lake(tmp_path)
    g = duckdb.connect(str(db))
    g.execute("insert into gold.dim_session_circuit values ('2026-R06-Q', 2026, 6, 'Q')")
    g.close()
    r = mod.export(db, lake, tmp_path / "out")
    assert r["written"] == 1 and r["skipped"] == [("2026-R06-Q", "no position telemetry")]
    r = mod.export(db, lake, tmp_path / "out2", sessions=("R",))
    assert not r["skipped"]


def test_foreign_folder_is_refused(tmp_path):
    lake, db, key = make_lake(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    (out / "precious.txt").write_text("keep me")
    with pytest.raises(SystemExit):
        mod.export(db, lake, out)
    assert (out / "precious.txt").read_text() == "keep me" and not (out / f"{key}.json").exists()


def test_missing_database_exits(tmp_path):
    with pytest.raises(SystemExit):
        mod.export(tmp_path / "nope.duckdb", tmp_path, tmp_path / "out")


def test_circuit_is_drawn_from_a_lap_the_telemetry_covers(tmp_path):
    # the position data stops before the session does: the fastest lap in the lap table is far beyond it
    lake, db, key = make_lake(tmp_path)
    g = duckdb.connect(str(db))
    g.execute("insert into gold.fct_lap values (?, 'VER', 99, 450.0, 20.0, 470.0, true)", [key])
    g.execute("insert into gold.fct_lap values (?, 'VER', 98, 430.0, 20.0, 450.0, true)", [key])
    g.close()
    lines = []
    r = mod.export(db, lake, tmp_path / "out", log=lines.append)
    assert r["written"] == 1 and not r["skipped"]
    assert any("position data ends" in s for s in lines), lines
    # VER's last lap (99) is past the end of the data, so VER is left out of the lap-count check; the others agree
    assert any("agrees with the lap count for 3 of 3 cars" in s for s in lines), lines


def test_circuit_skips_a_fastest_lap_with_no_position_samples(tmp_path):
    # the fastest lap is inside the telemetry's time range, but its driver has only placeholder (0, 0) rows there
    lake, db, key = make_lake(tmp_path)
    f = f"{lake}/telemetry_pos/year=2026/round=6/session=R/part-0.parquet"
    c = duckdb.connect()
    c.execute(f"create table t as select * from read_parquet('{f}')")
    c.execute("update t set x = 0, y = 0 where driver_number = 1 and session_time_s between 60 and 120")
    c.execute(f"copy t to '{f}' (format parquet)")
    g = duckdb.connect(str(db))
    g.execute("insert into gold.fct_lap values (?, 'VER', 98, 60.0, 50.0, 110.0, true)", [key])
    g.close()
    lines = []
    r = mod.export(db, lake, tmp_path / "out", log=lines.append)
    assert r["written"] == 1 and not r["skipped"], (r, lines)


def test_session_with_mostly_missing_position_data_is_skipped(tmp_path):
    # the lap table runs far beyond the position data (as with Monaco 2026, where positions stop five laps in)
    lake, db, key = make_lake(tmp_path)
    g = duckdb.connect(str(db))
    g.execute("insert into gold.fct_lap values (?, 'VER', 99, 8000.0, 30.0, 8030.0, true)", [key])
    g.close()
    r = mod.export(db, lake, tmp_path / "out")
    assert r["written"] == 0 and len(r["skipped"]) == 1 and "covers only" in r["skipped"][0][1], r
    assert not (tmp_path / "out" / f"{key}.json").exists()


def test_team_names_and_colours(tmp_path):
    lake, db, key = make_lake(tmp_path)
    mod.export(db, lake, tmp_path / "out")
    doc = json.loads((tmp_path / "out" / f"{key}.json").read_text())
    assert doc["teams"] == {"VER": ["Red Bull", "#3671C6"], "NOR": ["McLaren", None],
                            "LEC": ["Ferrari", "#E80020"], "HAM": ["Ferrari", None]}


def test_no_team_columns_means_no_teams(tmp_path):
    lake, db, key = make_lake(tmp_path)
    f = f"{lake}/results/year=2026/round=6/session=R/part-0.parquet"
    duckdb.sql(f"copy (select DriverNumber, Abbreviation from read_parquet('{f}')) to '{f}.new' (format parquet)")
    Path(f).unlink()
    Path(f + ".new").rename(f)
    mod.export(db, lake, tmp_path / "out")
    assert "teams" not in json.loads((tmp_path / "out" / f"{key}.json").read_text())


def test_a_retired_car_inside_its_last_lap_still_agrees(tmp_path):
    # HAM stops half way round his 4th lap: that lap has no lap time, and his progress there is 3.5, not 4
    lake, db, key = make_lake(tmp_path)
    period = 60.0 + 3 * 0.8
    end3 = (2 * math.pi * 3 + 0.10) * period / (2 * math.pi)     # start_theta of the 4th car is -0.10
    g = duckdb.connect(str(db))
    g.execute("delete from gold.fct_lap where driver_code = 'HAM' and lap_number >= 4")
    g.execute("insert into gold.fct_lap values (?, 'HAM', 4, ?, NULL, ?, true)", [key, end3, end3 + 0.5 * period])
    g.close()
    lines = []
    mod.export(db, lake, tmp_path / "out", log=lines.append)
    assert any("agrees with the lap count for 4 of 4 cars" in s for s in lines), lines


def test_a_hole_in_one_cars_position_data_does_not_cost_a_lap(tmp_path):
    # no samples for HAM for 40 s (more than half his 62.4 s lap): the car cannot have gone backwards, so he drove on
    lake, db, key = make_lake(tmp_path)
    f = f"{lake}/telemetry_pos/year=2026/round=6/session=R/part-0.parquet"
    c = duckdb.connect()
    c.execute(f"create table t as select * from read_parquet('{f}')")
    c.execute("delete from t where driver_number = 44 and session_time_s between 130 and 170")
    c.execute(f"copy t to '{f}' (format parquet)")
    lines = []
    out = tmp_path / "out"
    mod.export(db, lake, out, log=lines.append)
    assert any("agrees with the lap count for 4 of 4 cars" in s for s in lines), lines
    assert any("whole-lap slips corrected" in s for s in lines), lines     # the 40 s hole cost him a lap, the lap table put it back
    e = json.loads((out / f"{key}.json").read_text())["drivers"]["HAM"]
    assert decode(e)[e["b"]] == pytest.approx(LAPS + 20 / (60 + 2.4), abs=0.1)


def test_a_bad_sample_that_jumps_back_is_ignored(tmp_path):
    # a few HAM samples are placed a third of a lap behind where he is: progress must not dip
    lake, db, key = make_lake(tmp_path)
    f = f"{lake}/telemetry_pos/year=2026/round=6/session=R/part-0.parquet"
    c = duckdb.connect()
    c.execute(f"create table t as select * from read_parquet('{f}')")
    c.execute("update t set x = 4000, y = 0 where driver_number = 44 and session_time_s between 200 and 203")
    c.execute(f"copy t to '{f}' (format parquet)")
    out = tmp_path / "out"
    mod.export(db, lake, out)
    e = json.loads((out / f"{key}.json").read_text())["drivers"]["HAM"]
    assert (np.diff(decode(e)[e["a"]:e["b"] + 1]) > -0.02).all()


def test_a_last_lap_with_no_time_may_be_a_car_that_kept_driving(tmp_path):
    # HAM's 4th lap has no time in the lap table, and the table's end for it is 0.4 of a lap late: progress reads 4.4
    lake, db, key = make_lake(tmp_path)
    period = 60.0 + 3 * 0.8
    end3 = (2 * math.pi * 3 + 0.10) * period / (2 * math.pi)
    g = duckdb.connect(str(db))
    g.execute("delete from gold.fct_lap where driver_code = 'HAM' and lap_number >= 4")
    g.execute("insert into gold.fct_lap values (?, 'HAM', 4, ?, NULL, ?, true)", [key, end3, end3 + 1.4 * period])
    g.close()
    lines = []
    mod.export(db, lake, tmp_path / "out", log=lines.append)
    assert any("agrees with the lap count for 4 of 4 cars" in s for s in lines), lines


def test_a_session_whose_positions_do_not_match_the_laps_is_skipped(tmp_path):
    # after 100 s every car's positions are scrambled in time (as in 2026 round 11), so progress cannot be trusted
    lake, db, key = make_lake(tmp_path)
    f = f"{lake}/telemetry_pos/year=2026/round=6/session=R/part-0.parquet"
    c = duckdb.connect()
    c.execute(f"create table t as select * from read_parquet('{f}')")
    c.execute("create table late as select driver_number, session_time_s, x, y, row_number() over (partition by driver_number "
              "order by session_time_s) as r from t where session_time_s > 100")
    c.execute("create table sh as select driver_number, x, y, row_number() over (partition by driver_number order by "
              "hash(session_time_s * 7)) as r from late")
    c.execute("update t set x = s.x, y = s.y from (select l.driver_number, l.session_time_s, sh.x, sh.y from late l join sh "
              "using (driver_number, r)) s where t.driver_number = s.driver_number and t.session_time_s = s.session_time_s")
    c.execute(f"copy t to '{f}' (format parquet)")
    r = mod.export(db, lake, tmp_path / "out")
    assert r["written"] == 0 and "does not match the lap table" in r["skipped"][0][1], r
    assert not (tmp_path / "out" / f"{key}.json").exists()


def test_correct_slips_fixes_whole_laps_only():
    grid = np.arange(0.0, 400.0)
    ends = [(n, 100.0 * n) for n in range(1, 4)]            # a lap every 100 s
    ok = grid / 100.0
    lost = ok.copy()
    lost[150:] -= 1.0                                        # a lap lost half way through lap 2
    assert mod.correct_slips(grid, lost, 0.0, ends, 399.0) == 1
    assert np.allclose(lost, ok)
    gained = ok.copy()
    gained[250:] += 2.0
    assert mod.correct_slips(grid, gained, 0.0, ends, 399.0) == 1 and gained[300] == pytest.approx(3.0, abs=0.02)
    half = ok.copy()
    half[250:] += 0.5                                        # a car part way round a lap, or garbage: left alone
    keep = half.copy()
    assert mod.correct_slips(grid, half, 0.0, ends, 399.0) == 0 and (half == keep).all()
    short = ok.copy()
    assert mod.correct_slips(grid, short, 0.0, ends, 150.0) == 0   # laps after the data ends are not checked

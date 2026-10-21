import importlib.util
import json
from pathlib import Path

import duckdb
import pytest

SPEC = importlib.util.spec_from_file_location("export_static", Path(__file__).resolve().parents[1] / "scripts" / "export_static.py")
ex = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ex)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "f1_dbt.duckdb"
    con = duckdb.connect(str(path))
    con.execute("create schema gold")
    con.execute("""create table gold.dim_session as select * from (values
        ('2025-R01-R', 2025, 1, 'R', 'Race', 'Australian Grand Prix', true, true, true),
        ('2025-R01-FP1', 2025, 1, 'FP1', 'Practice 1', 'Australian Grand Prix', true, false, false),
        ('2025-R02-R', 2025, 2, 'R', 'Race', 'Chinese Grand Prix', false, true, false),
        ('2020-R01-R', 2020, 1, 'R', 'Race', 'Austrian Grand Prix', true, true, true)
      ) t(session_key, year, round, session_code, session_name, event, has_laps, has_results, has_race_control)""")
    con.execute("""create table gold.dim_session_circuit as select * from (values
        ('2025-R01-R', 'albert_park', 'Albert Park', 'Australia'), ('2025-R01-FP1', 'albert_park', 'Albert Park', 'Australia'),
        ('2025-R02-R', 'shanghai', 'Shanghai', 'China'), ('2020-R01-R', 'red_bull_ring', 'Red Bull Ring', 'Austria')
      ) t(session_key, circuit_id, circuit_name, country)""")
    con.execute("""create table gold.fct_lap as select * from (values
        ('2025-R01-R', 'Red Bull', 2025, 'VER', 1, 1, 'MEDIUM', 1.0, 1, '1', true, false, true, 90.5123456, 0.0, 90.5, null, null, 30.0, 30.0, 30.5, true),
        ('2025-R01-R', 'Red Bull', 2025, 'VER', 2, 1, 'MEDIUM', 2.0, 1, '1', true, false, true, 'nan'::double, 90.5, 181.0, null, null, null, null, null, false),
        ('2025-R01-R', 'Ferrari', 2025, 'LEC', 1, 1, 'HARD', 1.0, 2, '1', true, false, true, 91.0, 0.0, 91.0, null, null, 30.0, 30.0, 31.0, true),
        ('2025-R01-FP1', 'Ferrari', 2025, 'LEC', 1, 1, 'SOFT', 1.0, 1, '1', true, false, true, 95.0, 0.0, 95.0, null, null, 31.0, 31.0, 33.0, true),
        ('2020-R01-R', 'Mercedes', 2020, 'HAM', 1, 1, 'SOFT', 1.0, 1, '1', true, false, true, 70.0, 0.0, 70.0, null, null, 20.0, 20.0, 30.0, true)
      ) t(session_key, team, year, driver_code, lap_number, stint, compound, tyre_life, position, track_status, is_green,
          deleted, is_accurate, lap_time_s, lap_start_time_s, time_s, pit_in_time_s, pit_out_time_s, sector1_s, sector2_s, sector3_s, is_clean_lap)""")
    con.execute("""create table gold.fct_stint as select * from (values
        ('s1', '2025-R01-R', 2025, 'VER', 1, 'MEDIUM', 1, 2, 2, 1, 90.5), ('s2', '2025-R01-R', 2025, 'LEC', 1, 'HARD', 1, 1, 1, 1, 91.0)
      ) t(stint_key, session_key, year, driver_code, stint, compound, start_lap, end_lap, laps, clean_laps, median_clean_lap_s)""")
    con.execute("create table gold.fct_stint_degradation as select * from (values ('s1', 0.0512345)) t(stint_key, degradation_s_per_lap)")
    con.execute("""create table gold.fct_pit_stop as select * from (values
        ('2025-R01-R', 'VER', 20, 1000.0, 1022.5, 22.5, 'MEDIUM', 'HARD', '1', '1', true, 1)
      ) t(session_key, driver_code, in_lap, pit_in_time_s, pit_out_time_s, pit_lane_time_s, compound_before,
          compound_after, in_lap_track_status, out_lap_track_status, is_green_stop, position_before)""")
    con.execute("""create table gold.fct_race_control_period as select * from (values
        ('2025-R01-R', 2025, 2, 'VSC', 600.0, 700.0, false, true), ('2025-R01-R', 2025, 1, 'SC', 100.0, 300.0, false, true)
      ) t(session_key, year, period_no, kind, start_s, end_s, is_open, has_session_clock)""")
    con.execute("""create table gold.dim_circuit as select * from (values
        ('albert_park', 'Albert Park', 'Melbourne', 'Australia', -37.8, 144.9),
        ('shanghai', 'Shanghai', 'Shanghai', 'China', 31.3, 121.2),
        ('red_bull_ring', 'Red Bull Ring', 'Spielberg', 'Austria', 47.2, 14.7),
        ('monza', 'Monza', 'Monza', 'Italy', 45.6, 9.3)) t(circuit_id, circuit_name, locality, country, lat, long)""")
    con.execute("""create table gold.fct_circuit_pit_loss as select * from (values
        ('albert_park', 'Albert Park', 50, 3, 3, 22.5, 21.0, 24.0, true)) t(circuit_id, circuit_name, stops, sessions, seasons,
        median_pit_loss_s, p25_pit_loss_s, p75_pit_loss_s, is_reliable)""")
    con.execute("""create table gold.fct_circuit_degradation as select * from (values
        ('albert_park', 'v1', 'albert_park|v1', 'SOFT', 10, 3, 3, 0.08, 0.06, 0.1, 0.01, true)
      ) t(circuit_id, layout_id, circuit_layout_key, compound, stints, races, seasons, median_degradation_s_per_lap,
          p25_degradation_s_per_lap, p75_degradation_s_per_lap, approx_se_median_s_per_lap, is_reliable)""")
    con.close()
    return path


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def test_export_layout_and_filters(db, tmp_path):
    out = tmp_path / "data"
    r = ex.export(db, out, from_year=2022)
    assert r["session_files"] == 2                      # the no-laps 2025 race and the 2020 race are not written
    assert sorted(p.name for p in (out / "sessions").iterdir()) == ["2025-R01-FP1.json", "2025-R01-R.json"]
    sessions = read(out / "sessions.json")["sessions"]
    assert [s["session_key"] for s in sessions] == ["2025-R01-FP1", "2025-R01-R", "2025-R02-R"]
    assert sessions[2]["circuit_name"] == "Shanghai"
    m = read(out / "manifest.json")
    assert m["from_year"] == 2022 and m["sessions"] == 3 and m["session_files"] == 2 and m["seasons"] == [2025]


def test_session_file_content(db, tmp_path):
    out = tmp_path / "data"
    ex.export(db, out)
    d = read(out / "sessions" / "2025-R01-R.json")
    assert d["drivers"] == [{"code": "LEC", "team": "Ferrari"}, {"code": "VER", "team": "Red Bull"}]
    assert d["laps"]["driver_code"] == ["LEC", "VER", "VER"]
    assert d["laps"]["lap_number"] == [1, 1, 2]
    assert d["laps"]["lap_time_s"] == [91.0, 90.512, None]           # rounded to 3 decimals; NaN becomes null
    assert d["stints"]["degradation_s_per_lap"] == [None, 0.051]       # left join: LEC's stint has none
    assert d["pit_stops"]["pit_lane_time_s"] == [22.5]
    assert [p["kind"] for p in d["race_control_periods"]] == ["SC", "VSC"]
    assert read(out / "sessions" / "2025-R01-FP1.json")["pit_stops"]["in_lap"] == []


def test_circuits_only_those_in_exported_sessions(db, tmp_path):
    out = tmp_path / "data"
    ex.export(db, out)
    cs = read(out / "circuits.json")["circuits"]
    assert [c["circuit_id"] for c in cs] == ["albert_park", "shanghai"]      # monza has no session, 2020 is filtered
    assert cs[0]["pit_loss"]["median_pit_loss_s"] == 22.5 and cs[1]["pit_loss"] is None
    assert cs[0]["degradation"][0]["compound"] == "SOFT"


def test_refuses_a_foreign_folder_and_rewrites_its_own(db, tmp_path):
    out = tmp_path / "data"
    out.mkdir()
    (out / "mine.txt").write_text("keep me")
    with pytest.raises(SystemExit):
        ex.export(db, out)
    assert (out / "mine.txt").exists()
    out2 = tmp_path / "data2"
    ex.export(db, out2)
    (out2 / "stale.json").write_text("{}")
    ex.export(db, out2)
    assert not (out2 / "stale.json").exists() and (out2 / "manifest.json").exists()


def test_missing_database_exits(tmp_path):
    with pytest.raises(SystemExit):
        ex.export(tmp_path / "absent.duckdb", tmp_path / "out")

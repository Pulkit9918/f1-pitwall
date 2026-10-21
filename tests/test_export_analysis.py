"""Tests for scripts/export_analysis.py on a small mock gold schema with the real column names."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
SPEC = importlib.util.spec_from_file_location("export_analysis", Path(__file__).resolve().parents[1] / "scripts" / "export_analysis.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules["export_analysis"] = mod
SPEC.loader.exec_module(mod)


@pytest.fixture()
def db(tmp_path):
    c = duckdb.connect(str(tmp_path / "g.duckdb"))
    c.execute("create schema gold")
    c.execute("""create table gold.fct_lap_gap(lap_key varchar, session_key varchar, year int, driver_code varchar, lap_number int,
                 position int, gap_to_leader_s double, interval_s double)""")
    c.execute("""create table gold.fct_pit_now(pit_now_key varchar, regime varchar, pit_loss_s double, predicted_position int,
                 predicted_position_fast int, predicted_position_slow int, margin_s double)""")
    c.execute("""create table gold.fct_stop_battle(session_key varchar, year int, kind varchar, attacker_code varchar, defender_code varchar,
                 first_stopper_code varchar, first_stop_lap int, second_stop_lap int, gap_before_s double, attacker_ahead_after boolean,
                 margin_after_s double, is_neutralised boolean)""")
    c.execute("create table gold.fct_pit_stop(session_key varchar, driver_code varchar, in_lap bigint, session_code varchar)")
    c.execute("""create table gold.fct_pit_loss_ratio(regime varchar, stops int, median_loss_s double, p25_loss_s double, p75_loss_s double,
                 ratio_to_green double, is_reliable boolean)""")
    S = "2025-R01-R"
    rows = [("AAA", 1, 1, 0.0, None), ("AAA", 2, 1, 0.0, None), ("BBB", 1, 2, 1.234, 1.234), ("BBB", 3, 2, 5.55, 5.55)]  # BBB has no lap 2
    for d, lap, pos, gl, itv in rows:
        c.execute("insert into gold.fct_lap_gap values (?,?,2025,?,?,?,?,?)", [f"{S}-{d}-{lap}", S, d, lap, pos, gl, itv])
        c.execute("insert into gold.fct_pit_now values (?,?,?,?,?,?,?)", [f"{S}-{d}-{lap}", "sc" if lap == 2 else "green", 22.04, 3, 2, 4, 1.26])
    c.execute("insert into gold.fct_lap_gap values ('old-1','2019-R01-R',2019,'ZZZ',1,1,0.0,NULL)")
    c.execute("insert into gold.fct_stop_battle values (?,2025,'undercut','BBB','AAA','BBB',1,3,1.234,true,2.5,false)", [S])
    c.execute("insert into gold.fct_pit_stop values (?,?,2,'R'),(?,?,NULL,'R'),('2025-R01-FP1','AAA',5,'FP1')", [S, "BBB", S, "AAA"])
    c.execute("insert into gold.fct_pit_loss_ratio values ('green',10,22.7,20.8,25.1,1.0,true),('sc',5,17.0,1.8,38.4,0.751,false)")
    c.close()
    return tmp_path / "g.duckdb"


def test_exports_arrays_by_lap_and_respects_from_year(db, tmp_path):
    out = tmp_path / "out"
    keys = mod.export(db, out, from_year=2022, log=lambda *_: None)
    assert keys == ["2025-R01-R"]                       # 2019 is before from_year
    doc = json.loads((out / "2025-R01-R.json").read_text())
    assert doc["laps"] == 3 and doc["drivers"] == ["AAA", "BBB"]
    b = doc["series"]["BBB"]
    assert b["leader"] == [1.2, None, 5.5] or b["leader"] == [1.2, None, 5.6]   # rounded to 0.1, missing lap is null
    assert b["pos"] == [2, None, 2]
    assert b["regime"] == "g.g"                          # a lap with no row is "."
    assert doc["series"]["AAA"]["regime"] == "gs."
    assert doc["series"]["AAA"]["loss"] == [22.0, 22.0, None]
    assert doc["stops"] == [{"driver": "BBB", "lap": 2}]  # no null laps, no practice sessions
    assert doc["battles"][0]["kind"] == "undercut" and doc["battles"][0]["attacker_ahead"] is True
    assert doc["loss_ratio"]["sc"]["reliable"] is False and doc["loss_ratio"]["sc"]["p75_loss_s"] == 38.4


def test_refuses_foreign_folder_and_missing_db(db, tmp_path):
    foreign = tmp_path / "foreign"; foreign.mkdir(); (foreign / "keep.txt").write_text("x")
    with pytest.raises(SystemExit):
        mod.export(db, foreign, log=lambda *_: None)
    assert (foreign / "keep.txt").exists() and not (foreign / "index.json").exists()
    with pytest.raises(SystemExit):
        mod.export(tmp_path / "nope.duckdb", tmp_path / "o2", log=lambda *_: None)


def test_rerun_into_own_folder(db, tmp_path):
    out = tmp_path / "out"
    mod.export(db, out, log=lambda *_: None)
    mod.export(db, out, log=lambda *_: None)
    assert json.loads((out / "index.json").read_text())["generator"] == "export_analysis"

"""Tests for scripts/export_seasons.py on a small mock gold schema with the real column names."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
SPEC = importlib.util.spec_from_file_location("export_seasons", Path(__file__).resolve().parents[1] / "scripts" / "export_seasons.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules["export_seasons"] = mod
SPEC.loader.exec_module(mod)


@pytest.fixture()
def db(tmp_path):
    c = duckdb.connect(str(tmp_path / "g.duckdb"))
    c.execute("create schema gold")
    c.execute("create table gold.dim_historical_driver as select * from (values ('ver','Max Verstappen'),('nor','Lando Norris'),('lec','Charles Leclerc')) t(driver_id,full_name)")
    c.execute("create table gold.dim_constructor as select * from (values ('red_bull','Red Bull'),('mclaren','McLaren'),('ferrari','Ferrari')) t(constructor_id,name)")
    c.execute("create table gold.fct_driver_standing as select * from (values ('s1',2024,2,1,60.0,1,'ver','Red Bull'),('s2',2024,2,2,40.0,0,'nor','McLaren')) t(standing_key,season,round,position,points,wins,driver_id,constructor_name)")
    c.execute("create table gold.fct_constructor_standing as select * from (values ('c1',2024,2,1,60.0,1,'red_bull')) t(standing_key,season,round,position,points,wins,constructor_id)")
    c.execute("create table gold.fct_season_result as select * from (values (1,'r1',1,2024,1,'Bahrain GP',date '2024-03-02','bahrain','ver','VER','red_bull',1,1,25.0,57,'Finished',1000,1,true,true,true),(2,'r2',1,2024,1,'Bahrain GP',date '2024-03-02','bahrain','nor','NOR','mclaren',5,2,18.0,57,'Finished',1001,2,false,true,true),(3,'r3',1,2024,1,'Bahrain GP',date '2024-03-02','bahrain','lec','LEC','ferrari',0,NULL,0.0,10,'Engine',NULL,NULL,false,false,false),(4,'r4',1,2017,1,'Old GP',date '2017-03-26','x','ver','VER','red_bull',1,1,25.0,57,'Finished',1,1,true,true,true)) t(race_key,result_key,drive_number,season,round,race_name,race_date,circuit_id,driver_id,driver_code,constructor_id,grid,position,points,laps,status,time_ms,fastest_rank,is_win,is_podium,is_classified_finish)")
    c.execute("create table gold.fct_points_progression as select * from (values ('p1',2024,1,'ver','red_bull',25.0,0.0,false,25.0,1),('p2',2024,1,'nor','mclaren',18.0,0.0,false,18.0,2)) t(progression_key,season,round,driver_id,constructor_id,points_in_round,sprint_points,sprint_points_imputed,cumulative_points,championship_position)")
    c.execute("create table gold.fct_constructor_points_progression as select * from (values ('p1',2024,1,'red_bull',25.0,1)) t(progression_key,season,round,constructor_id,cumulative_points,championship_position)")
    c.close()
    return tmp_path / "g.duckdb"


def test_exports_season_and_respects_from_year(db, tmp_path):
    out = tmp_path / "out"
    idx = mod.export(db, out, from_year=2018, log=lambda *_: None)
    assert [s["season"] for s in idx] == [2024]          # 2017 is before from_year
    doc = json.loads((out / "2024.json").read_text())
    assert doc["drivers"][0]["name"] == "Max Verstappen" and doc["drivers"][0]["points"] == 60
    race = doc["races"][0]
    assert race["podium"] == ["ver", "nor"]
    by = {r["code"]: r for r in race["results"]}
    assert by["NOR"]["gained"] == 3                       # grid 5 -> finished 2
    assert by["LEC"]["gained"] is None and by["LEC"]["position"] is None   # pit-lane start, did not finish
    assert by["VER"]["fastest"] is True
    assert doc["progression"]["drivers"][0]["cum"] == [25]
    assert doc["progression"]["drivers"][0]["code"] == "VER"      # the picker labels drivers by code


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
    assert json.loads((out / "index.json").read_text())["generator"] == "export_seasons"

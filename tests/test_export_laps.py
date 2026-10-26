"""Tests for scripts/export_laps.py on a small mock gold schema with the real column names."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
SPEC = importlib.util.spec_from_file_location("export_laps", Path(__file__).resolve().parents[1] / "scripts" / "export_laps.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules["export_laps"] = mod
SPEC.loader.exec_module(mod)
S = "2025-R01-Q"


@pytest.fixture()
def db(tmp_path):
    c = duckdb.connect(str(tmp_path / "g.duckdb"))
    c.execute("create schema gold")
    c.execute("""create table gold.fct_lap(session_key varchar, lap_key varchar, year int, driver_code varchar, team varchar, lap_number int,
                 compound varchar, tyre_life double, track_status varchar, is_clean_lap boolean, deleted boolean, lap_time_s double,
                 pit_in_time_s double, pit_out_time_s double, sector1_s double, sector2_s double, sector3_s double)""")
    c.execute("""create table gold.fct_lap_sector(lap_key varchar, session_key varchar, driver_code varchar, sector smallint, time_s double, status varchar)""")
    c.execute("create table gold.dim_session_circuit(session_key varchar, year int, round int, session_code varchar, event varchar, circuit_name varchar, country varchar)")
    c.execute("insert into gold.dim_session_circuit values (?,2025,1,'Q','Synth GP','Synth Circuit','X'),('2019-R01-Q',2019,1,'Q','Old','Old','X')", [S])
    lap = lambda k, y, d, n, t, s, **o: c.execute("insert into gold.fct_lap values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        k, f"{k}-{d}-{n}", y, d, "Team " + d, n, o.get("comp", "SOFT"), o.get("age", 1.0), "1", o.get("clean", True), o.get("deleted", False), t,
        o.get("pit_in"), None, *s])
    lap(S, 2025, "AAA", 1, 90.0, (30.0, 35.0, 25.0))
    lap(S, 2025, "AAA", 2, 89.0, (29.5, 34.5, 25.0), age=2.0)
    lap(S, 2025, "BBB", 1, 91.0, (30.5, None, None), clean=False, pit_in=5.0)
    lap(S, 2025, "BBB", 2, None, (None, None, None), deleted=True)
    lap("2019-R01-Q", 2019, "ZZZ", 1, 95.0, (1.0, 1.0, 1.0))
    for d, n, sec, t, st in (("AAA", 1, 1, 30.0, "purple"), ("AAA", 1, 2, 35.0, "purple"), ("AAA", 1, 3, 25.0, "purple"),
                             ("AAA", 2, 1, 29.5, "purple"), ("AAA", 2, 2, 34.5, "purple"), ("AAA", 2, 3, 25.0, "yellow"), ("BBB", 1, 1, 30.5, "green")):
        c.execute("insert into gold.fct_lap_sector values (?,?,?,?,?,?)", [f"{S}-{d}-{n}", S, d, sec, t, st])
    c.close()
    return tmp_path / "g.duckdb"


def test_laps_are_columns_with_colours_flags_and_session_bests(db, tmp_path):
    out = tmp_path / "out"
    assert mod.export(db, out, from_year=2022, log=lambda *_: None)["written"] == 1
    top = json.loads((out / "index.json").read_text())
    assert top["generator"] == "export_laps" and [s["key"] for s in top["sessions"]] == [S] and top["sessions"][0]["laps"] == 4
    doc = json.loads((out / f"{S}.json").read_text())
    a, b = doc["drivers"]
    assert (a["code"], a["team"], a["n"], a["t"]) == ("AAA", "Team AAA", [1, 2], [90.0, 89.0])
    assert a["c"] == ["ppp", "ppy"] and a["s1"] == [30.0, 29.5] and a["a"] == [1, 2] and a["o"] == [1, 1]
    assert b["c"] == ["g--", "---"] and b["s2"] == [None, None] and b["i"] == [1, 0] and b["x"] == [0, 1] and b["o"] == [0, 1]
    assert doc["best"]["1"] == {"t": 29.5, "d": "AAA"} and doc["best"]["3"] == {"t": 25.0, "d": "AAA"}
    assert doc["event"] == "Synth GP" and doc["session_code"] == "Q"


def test_refuses_a_folder_it_did_not_write(db, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "mine.txt").write_text("keep")
    with pytest.raises(SystemExit):
        mod.export(db, out, log=lambda *_: None)
    assert (out / "mine.txt").read_text() == "keep" and not (out / "index.json").exists()


def test_can_write_again_over_its_own_output(db, tmp_path):
    out = tmp_path / "out"
    mod.export(db, out, log=lambda *_: None)
    assert mod.export(db, out, log=lambda *_: None)["written"] == 1

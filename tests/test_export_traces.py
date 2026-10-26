"""Tests for scripts/export_traces.py on a small mock gold schema with the real column names."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
duckdb = pytest.importorskip("duckdb")
SPEC = importlib.util.spec_from_file_location("export_traces", Path(__file__).resolve().parents[1] / "scripts" / "export_traces.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules["export_traces"] = mod
SPEC.loader.exec_module(mod)

P = 8
S = "2025-R01-R"


def add_lap(c, key, driver, lap, speed_ok, times, speeds=None, reason="ok", year=2025):
    lk = f"{key}-{driver}-{lap}"
    traced = reason == "ok"
    c.execute("insert into gold.fct_lap_trace_lap values (?,?,?,?,?,?,?,?,?,?,?)",
              [lk, key, year, driver, lap, 5000.0, traced, speed_ok and traced, reason, 90.0 + lap, "x"])
    c.execute("insert into gold.fct_lap values (?,?,?,?,?,?,?)", [lk, driver, "Team " + driver, "MEDIUM", 3.0 + lap, "1", 90.0 + lap])
    if not traced:
        return
    for i in range(P):
        has = speed_ok
        c.execute("insert into gold.fct_lap_trace values (?,?,?,?,?,?,?,?,?,?,?,?)", [
            lk, key, driver, lap, i, 5000.0 * i / (P - 1), times[i],
            (200 + i) if has else None, (80 + i) if has else None, (i + 1) if has else None,
            (0 if i < 4 else 12) if has else None, (i % 2 == 0) if has else None])


@pytest.fixture()
def db(tmp_path):
    c = duckdb.connect(str(tmp_path / "g.duckdb"))
    c.execute("create schema gold")
    c.execute("""create table gold.fct_lap_trace_lap(lap_key varchar, session_key varchar, year int, driver_code varchar, lap_number int,
                 ref_length_m double, has_trace boolean, speed_ok boolean, trace_reason varchar, lap_time_s double, circuit_layout_key varchar)""")
    c.execute("create table gold.fct_lap(lap_key varchar, driver_code varchar, team varchar, compound varchar, tyre_life double, track_status varchar, lap_time_s double)")
    c.execute("""create table gold.fct_lap_trace(lap_key varchar, session_key varchar, driver_code varchar, lap_number int, point_idx smallint,
                 dist_m float, time_s float, speed_kph smallint, throttle_pct smallint, gear smallint, drs smallint, brake boolean)""")
    c.execute("create table gold.dim_session_circuit(session_key varchar, year int, round int, session_code varchar, event varchar, circuit_name varchar, country varchar)")
    c.execute("insert into gold.dim_session_circuit values (?,2025,1,'R','Synth Grand Prix','Synth Circuit','Australia'),('2019-R01-R',2019,1,'R','Old GP','Old','X')", [S])
    base = [0.0, 10.004, 21.996, 33.5, 45.0, 56.25, 67.5, 90.0]
    add_lap(c, S, "AAA", 1, True, None, reason="standing_start")
    add_lap(c, S, "AAA", 2, True, base)
    add_lap(c, S, "AAA", 3, False, [x * 1.01 for x in base])          # traced, but the speed channel is not trusted
    add_lap(c, S, "BBB", 2, True, [x * 0.99 for x in base])
    add_lap(c, S, "BBB", 3, True, None, reason="pit_lap")
    add_lap(c, "2019-R01-R", "ZZZ", 2, True, base, year=2019)
    c.close()
    return tmp_path / "g.duckdb"


def test_session_index_lists_every_lap_with_its_status(db, tmp_path):
    out = tmp_path / "out"
    r = mod.export(db, out, from_year=2024, log=lambda *_: None)
    assert r["written"] == 1 and not r["skipped"]
    top = json.loads((out / "index.json").read_text())
    assert top["generator"] == "export_traces" and [s["key"] for s in top["sessions"]] == [S]   # 2019 is before from_year
    assert top["sessions"][0]["drivers"] == 2 and top["sessions"][0]["laps"] == 3
    idx = json.loads((out / S / "index.json").read_text())
    assert idx["points"] == P and idx["dist"][0] == 0.0 and idx["dist"][-1] == 5000.0 and idx["ref_length_m"] == 5000.0
    a, b = idx["drivers"]
    assert (a["code"], a["team"]) == ("AAA", "Team AAA")
    assert a["laps"][0] == {"n": 1, "t": 91.0, "c": "MEDIUM", "a": 4, "s": "1", "r": "standing_start"}
    assert a["laps"][1]["k"] == 1 and a["laps"][2]["k"] == 0 and "r" not in a["laps"][2]
    assert b["laps"][1]["r"] == "pit_lap"


def test_driver_file_decodes_to_the_traces(db, tmp_path):
    out = tmp_path / "out"
    mod.export(db, out, log=lambda *_: None)
    doc = json.loads((out / S / "AAA.json").read_text())
    assert doc["driver"] == "AAA" and doc["points"] == P and sorted(doc["laps"]) == ["2", "3"]    # lap 1 has no trace
    lap = doc["laps"]["2"]
    cum = np.concatenate([[0], np.cumsum(lap["dt"])]) / 100
    assert np.allclose(cum, [0.0, 10.0, 22.0, 33.5, 45.0, 56.25, 67.5, 90.0], atol=0.0051)        # to the hundredth
    assert lap["v"] == [200 + i for i in range(P)] and lap["th"] == [80 + i for i in range(P)]
    assert lap["g"] == "12345678" and lap["d"] == "0000cccc" and lap["b"] == "10101010"
    assert set(doc["laps"]["3"]) == {"dt"}                                   # no speed channel: only the time trace


def test_refuses_foreign_folder_missing_db_and_reruns(db, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "mine.txt").write_text("not yours")
    with pytest.raises(SystemExit) as e:
        mod.export(db, out, log=lambda *_: None)
    assert "was not written by this script" in str(e.value) and (out / "mine.txt").exists() and not (out / "index.json").exists()
    with pytest.raises(SystemExit):
        mod.export(tmp_path / "missing.duckdb", tmp_path / "out2", log=lambda *_: None)
    ok = tmp_path / "ok"
    mod.export(db, ok, log=lambda *_: None)
    mod.export(db, ok, log=lambda *_: None)                                    # a folder it wrote itself is fine
    assert (ok / S / "BBB.json").exists()


def test_digits():
    assert mod.digits([0, 5, 9, 12, 99, -3], 10) == "059990"        # clipped to 0..9
    assert mod.digits([0, 9, 10, 14, 15, 30], 16) == "09aeff"

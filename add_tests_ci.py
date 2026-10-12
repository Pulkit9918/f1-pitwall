#!/usr/bin/env python3
"""Adds a pytest suite (synthetic data), requirements files and a GitHub Actions workflow.

Existing requirements / pytest.ini / workflow files are left alone. Run from the project folder:
    python add_tests_ci.py
"""

import py_compile
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app" / "engine.py").exists():
    sys.exit("Run this from ~/Desktop/f1-pitwall (app/engine.py not found here).")

FILES = {}

FILES["tests/conftest.py"] = '''
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "app", ROOT):
    sys.path.insert(0, str(_p))


@pytest.fixture
def lake(tmp_path, monkeypatch):
    """A tiny synthetic lake: three cars on a circular track, six laps."""
    import streamlit as st

    import pitwall as pw
    from synth import make_session

    monkeypatch.setattr(pw, "LAKE", tmp_path)
    monkeypatch.setattr(pw, "MANIFEST", tmp_path / "_manifest" / "sessions.jsonl")
    st.cache_data.clear()
    st.cache_resource.clear()
    make_session(tmp_path)
    yield tmp_path
    st.cache_data.clear()
    st.cache_resource.clear()
'''

FILES["tests/synth.py"] = '''
"""Synthetic session: three cars lapping a circular track at constant speeds."""

import numpy as np
import pandas as pd

R = 10_000                    # circle radius in position units (1/10 m)
LAP_TIMES = {"AAA": 90.0, "BBB": 91.0, "CCC": 95.0}
NUMBERS = {"AAA": 1, "BBB": 2, "CCC": 3}
N_LAPS = 6


def make_session(root, year=2099, rnd=1, code="R"):
    def path(table):
        p = root / table / f"year={year}" / f"round={rnd:02d}" / f"session={code}"
        p.mkdir(parents=True, exist_ok=True)
        return p / "part.parquet"

    rows = []
    for name, lt in LAP_TIMES.items():
        for n in range(1, N_LAPS + 1):
            start, end = (n - 1) * lt, n * lt
            rows.append({
                "Driver": name, "DriverNumber": str(NUMBERS[name]), "Team": "Test",
                "LapNumber": float(n), "LapTime_s": lt,
                "LapStartTime_s": start, "Time_s": end,
                "Sector1Time_s": lt / 3, "Sector2Time_s": lt / 3, "Sector3Time_s": lt / 3,
                "Sector1SessionTime_s": start + lt / 3,
                "Sector2SessionTime_s": start + 2 * lt / 3,
                "Sector3SessionTime_s": end,
                "PitInTime_s": np.nan, "PitOutTime_s": np.nan,
                "Compound": "MEDIUM", "TyreLife": float(n), "Stint": 1.0,
                "TrackStatus": "1", "Position": np.nan})
    laps = pd.DataFrame(rows)
    laps["Position"] = laps.groupby("LapNumber")["Time_s"].rank(method="first")
    laps.to_parquet(path("laps"), index=False)

    pd.DataFrame({
        "Abbreviation": list(NUMBERS), "Position": [1.0, 2.0, 3.0],
        "GridPosition": [1.0, 2.0, 3.0], "Status": ["Finished"] * 3,
    }).to_parquet(path("results"), index=False)

    frames = []
    for name, lt in LAP_TIMES.items():
        t = np.arange(0.0, N_LAPS * lt + 20.0, 0.25)
        theta = 2 * np.pi * ((t / lt) % 1.0)
        frames.append(pd.DataFrame({
            "driver_number": np.full(len(t), NUMBERS[name], dtype="int16"),
            "session_time_s": t.astype("float32"),
            "x": np.round(R * np.cos(theta)).astype("int32"),
            "y": np.round(R * np.sin(theta)).astype("int32")}))
    pd.concat(frames).to_parquet(path("telemetry_pos"), index=False)
'''

FILES["tests/test_pitwall.py"] = '''
import pitwall as pw


def test_fmt_lap():
    assert pw.fmt_lap(95.123) == "1:35.123"
    assert pw.fmt_lap(5.2) == "0:05.200"
    assert pw.fmt_lap(None) == ""
    assert pw.fmt_lap(float("nan")) == ""


def test_unit_conversions():
    assert pw.spd(100, False) == 100
    assert abs(pw.spd(100, True) - 62.1371) < 1e-3
    assert pw.tmp(0, True) == 32
    assert pw.tmp(100, True) == 212
    assert pw.spd_unit(True) == "mph"
    assert pw.spd_unit(False) == "km/h"


def test_partition_path(tmp_path, monkeypatch):
    monkeypatch.setattr(pw, "LAKE", tmp_path)
    p = pw.part("laps", 2025, 3, "FP1")
    assert p == tmp_path / "laps" / "year=2025" / "round=03" / "session=FP1" / "part.parquet"
'''

FILES["tests/test_engine.py"] = '''
import numpy as np
import pytest

import engine as eg


def test_rotate_quarter_turn():
    out = eg.rotate(np.array([[1.0, 0.0]]), 90)
    assert np.allclose(out, [[0.0, 1.0]], atol=1e-9)


def test_project_onto_a_straight_line():
    ref = np.array([[0.0, 0.0], [50.0, 0.0], [100.0, 0.0]])
    s = np.array([0.0, 50.0, 100.0])
    s_out, d_out = eg.project(np.array([[30.0, 5.0], [90.0, -2.0]]), ref, s)
    assert np.allclose(s_out, [30.0, 90.0])
    assert np.allclose(d_out, [5.0, 2.0])


def test_build_and_snapshot_on_a_synthetic_circuit(lake):
    state = eg.build(2099, 1, "R")
    assert state is not None
    assert set(state["drivers"]) == {"AAA", "BBB", "CCC"}
    assert state["drivers"]["AAA"]["approx"] == set()

    snap = eg.snapshot(state, 200.0)
    assert list(snap["driver"]) == ["AAA", "BBB", "CCC"]
    progress = dict(zip(snap["driver"], snap["P"]))
    assert progress["AAA"] == pytest.approx(200 / 90, abs=0.02)
    assert progress["BBB"] == pytest.approx(200 / 91, abs=0.02)
    assert progress["CCC"] == pytest.approx(200 / 95, abs=0.02)
    # B reached A's current spot 2.2 s ago; C reached B's spot 8.4 s ago
    gaps = dict(zip(snap["driver"], snap["int_s"]))
    assert gaps["BBB"] == pytest.approx(2.2, abs=0.5)
    assert gaps["CCC"] == pytest.approx(8.4, abs=0.8)


def test_finished_cars_are_marked(lake):
    state = eg.build(2099, 1, "R")
    snap = eg.snapshot(state, 545.0)
    assert list(snap["driver"]) == ["AAA", "BBB", "CCC"]
    status = dict(zip(snap["driver"], snap["status"]))
    assert status["AAA"] == "FIN"
    assert status["CCC"] == ""
'''

FILES["tests/test_racelib.py"] = '''
import numpy as np
import pandas as pd
import pytest

import racelib as rl


def lap(driver, n, end, lap_time=90.0, status="1", pit_in=np.nan, pit_out=np.nan, pos=1.0):
    return {"Driver": driver, "LapNumber": float(n), "Time_s": end, "LapTime_s": lap_time,
            "LapStartTime_s": end - lap_time, "TrackStatus": status, "PitInTime_s": pit_in,
            "PitOutTime_s": pit_out, "Position": pos, "Compound": "MEDIUM", "TyreLife": float(n)}


def test_status_ranges_find_safety_car_and_vsc():
    rows = []
    for d in ("A", "B", "C", "D"):
        for n in range(1, 9):
            status = "4" if n in (3, 4) else ("67" if n == 7 else "1")
            rows.append(lap(d, n, 90.0 * n, status=status))
    assert rl.status_ranges(pd.DataFrame(rows)) == [(3, 4, "SC"), (7, 7, "VSC")]


def test_flag_laps_priority():
    statuses = {2: "2", 3: "4", 4: "6", 5: "245"}
    rows = [lap(d, n, 90.0 * n, status=statuses.get(n, "1"))
            for d in ("A", "B") for n in range(1, 7)]
    assert rl.flag_laps(pd.DataFrame(rows)) == {2: "YEL", 3: "SC", 4: "VSC", 5: "RED"}


def test_gap_table():
    rows = [lap("A", 1, 90.0), lap("A", 2, 180.0), lap("B", 1, 95.0), lap("B", 2, 186.0)]
    g = rl.gap_table(pd.DataFrame(rows))
    assert g[g["Driver"] == "B"].sort_values("lap")["gap_s"].tolist() == pytest.approx([5.0, 6.0])
    assert g[g["Driver"] == "A"]["gap_s"].tolist() == pytest.approx([0.0, 0.0])


def pit_scenario():
    rows = []
    for n in range(1, 11):
        rows.append(lap("X", n, 90.0 * n,
                        pit_in=(90.0 * n - 5) if n == 5 else np.nan,
                        pit_out=(90.0 * n + 15) if n == 6 else np.nan))
        rows.append(lap("Y", n, 90.0 * n + 10.0))
    return rl.driver_frames(pd.DataFrame(rows))


def test_actual_stops_finds_the_in_lap():
    frames = pit_scenario()
    assert rl.actual_stops(frames["X"]) == [5]
    assert rl.actual_stops(frames["Y"]) == []


def test_predict_rejoin_depends_on_the_pit_loss():
    frames = pit_scenario()
    # X leads Y by 10 s. A 22.4 s stop drops X behind Y; a 5 s stop would not.
    assert rl.predict_rejoin(frames, "X", 5, 22.4)["position"] == 2
    assert rl.predict_rejoin(frames, "X", 5, 5.0)["position"] == 1


def test_tower_marks_retired_cars_and_computes_gaps():
    rows = []
    for n in range(1, 6):
        rows.append(lap("A", n, 90.0 * n))
        rows.append(lap("B", n, 90.0 * n + 5.0))
    rows += [lap("D", 1, 92.0), lap("D", 2, 184.0)]
    laps = pd.DataFrame(rows)
    drv = pd.DataFrame({"Driver": ["A", "B", "D"]})
    results = pd.DataFrame({"Abbreviation": ["A", "B", "D"],
                            "Status": ["Finished", "Finished", "Retired"]})
    out = rl.tower(laps, drv, results, 5)
    status = dict(zip(out["Driver"], out["status"]))
    assert status["D"] == "OUT"
    assert out.loc[out["Driver"] == "B", "gap to leader"].iloc[0] == pytest.approx(5.0)
    assert out.loc[out["Driver"] == "A", "order"].iloc[0] == 1
'''

FILES["tests/test_history.py"] = '''
import history

RACE = {
    "season": "2025", "round": "1", "raceName": "Australian Grand Prix", "date": "2025-03-16",
    "Circuit": {"circuitId": "albert_park"},
    "Results": [
        {"number": "4", "position": "1", "positionText": "1", "points": "25",
         "Driver": {"driverId": "norris", "permanentNumber": "1", "code": "NOR",
                    "givenName": "Lando", "familyName": "Norris"},
         "Constructor": {"constructorId": "mclaren", "name": "McLaren"},
         "grid": "1", "laps": "57", "status": "Finished",
         "Time": {"millis": "6126304", "time": "1:42:06.304"},
         "FastestLap": {"rank": "1", "lap": "43", "Time": {"time": "1:22.167"}}},
        {"number": "1", "position": "2", "positionText": "2", "points": "18",
         "Driver": {"driverId": "max_verstappen", "permanentNumber": "3", "code": "VER",
                    "givenName": "Max", "familyName": "Verstappen"},
         "Constructor": {"constructorId": "red_bull", "name": "Red Bull"},
         "grid": "3", "laps": "57", "status": "Finished",
         "Time": {"millis": "6127199", "time": "+0.895"},
         "FastestLap": {"rank": "3", "lap": "43", "Time": {"time": "1:23.081"}}},
    ],
}


def test_num():
    assert history.num("5") == 5.0
    assert history.num(None) is None
    assert history.num("x") is None


def test_collect_results(monkeypatch):
    def fake_pages(path, pause):
        yield {"limit": "100", "offset": "0", "total": "2",
               "RaceTable": {"season": "2025", "Races": [RACE]}}

    monkeypatch.setattr(history, "pages", fake_pages)
    rows = history.collect_results("2025", 0)
    assert len(rows) == 2
    first = rows[0]
    assert first["driver"] == "Lando Norris"
    assert first["constructor"] == "McLaren"
    assert first["points"] == 25.0
    assert first["grid"] == 1.0
    assert first["position"] == 1.0
    assert first["time_ms"] == 6126304.0
    assert first["fastest_time"] == "1:22.167"
    assert first["season"] == 2025 and first["round"] == 1


def test_collect_driver_standings(monkeypatch):
    page = {"StandingsTable": {"StandingsLists": [{
        "season": "1950", "round": "7", "DriverStandings": [{
            "position": "1", "positionText": "1", "points": "30", "wins": "3",
            "Driver": {"driverId": "farina", "givenName": "Nino", "familyName": "Farina"},
            "Constructors": [{"constructorId": "alfa", "name": "Alfa Romeo"}]}]}]}}
    monkeypatch.setattr(history, "pages", lambda path, pause: iter([page]))
    rows = history.collect_driver_standings("1950", 0)
    assert rows[0]["driver"] == "Nino Farina"
    assert rows[0]["points"] == 30.0 and rows[0]["wins"] == 3.0
    assert rows[0]["constructor"] == "Alfa Romeo"
    assert rows[0]["round"] == 7


def test_collect_constructor_standings(monkeypatch):
    page = {"StandingsTable": {"StandingsLists": [{
        "season": "2025", "round": "24", "ConstructorStandings": [{
            "position": "1", "positionText": "1", "points": "833", "wins": "14",
            "Constructor": {"constructorId": "mclaren", "name": "McLaren",
                            "nationality": "British"}}]}]}}
    monkeypatch.setattr(history, "pages", lambda path, pause: iter([page]))
    rows = history.collect_constructor_standings("2025", 0)
    assert rows[0]["constructor"] == "McLaren"
    assert rows[0]["points"] == 833.0 and rows[0]["wins"] == 14.0


class FakeResponse:
    def __init__(self, status, data=None, headers=None):
        self.status_code = status
        self._data = data or {}
        self.headers = headers or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def test_get_retries_after_a_429_and_then_serves_from_the_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "RAW", tmp_path)
    monkeypatch.setattr(history.time, "sleep", lambda s: None)
    answers = [FakeResponse(429, headers={"Retry-After": "0"}), FakeResponse(200, {"ok": 1})]
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return answers.pop(0)

    monkeypatch.setattr(history.requests, "get", fake_get)
    assert history.get("seasons.json?limit=1", 0) == {"ok": 1}
    assert len(calls) == 2
    assert history.get("seasons.json?limit=1", 0) == {"ok": 1}      # raw cache: no new request
    assert len(calls) == 2


def test_pages_follows_the_offsets(monkeypatch):
    paths = []

    def fake_get(path, pause):
        paths.append(path)
        return {"MRData": {"limit": "100", "offset": "0", "total": "250"}}

    monkeypatch.setattr(history, "get", fake_get)
    pages = list(history.pages("2025/results.json", 0))
    assert len(pages) == 3
    assert paths[-1].endswith("limit=100&offset=200")
'''

NEW_ONLY = {
    "pytest.ini": "[pytest]\ntestpaths = tests\nfilterwarnings =\n    ignore::DeprecationWarning\n",
    "requirements-app.txt": ("streamlit>=1.37\nplotly>=5.20\nduckdb>=1.0\npandas>=2.0\n"
                             "pyarrow>=14\nnumpy>=1.26\n"),
    "requirements-ingest.txt": "fastf1>=3.8\npandas>=2.0\npyarrow>=14\nduckdb>=1.0\nrequests>=2.31\n",
    "requirements-dev.txt": "pytest>=8\nruff>=0.5\nrequests>=2.31\n",
    ".github/workflows/ci.yml": """name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: requirements*.txt
      - name: Install
        run: pip install -r requirements-app.txt -r requirements-dev.txt
      - name: Static check (syntax errors and undefined names only)
        run: ruff check --select E9,F63,F7,F82 .
      - name: Tests
        run: pytest -q
""",
}

for rel, text in FILES.items():
    f = ROOT / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text.strip("\n") + "\n")
    print("OK       wrote", rel)

for rel, text in NEW_ONLY.items():
    f = ROOT / rel
    if f.exists():
        print("SKIPPED ", rel, "already exists; left alone")
    else:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
        print("OK       wrote", rel)

bad = 0
for rel in FILES:
    try:
        py_compile.compile(str(ROOT / rel), doraise=True)
    except py_compile.PyCompileError as e:
        bad += 1
        print("SYNTAX ERROR in", rel, "->", str(e)[:300])
print("\nAll test files compile." if not bad else "\nSend me this output.")

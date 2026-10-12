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

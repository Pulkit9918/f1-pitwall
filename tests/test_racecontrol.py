import numpy as np
import pandas as pd
import pytest

import racecontrol as rcc

BASE = pd.Timestamp("2026-10-11 12:00:00")
GRID = np.arange(0.0, 4000.0, 1.0)
LEAD = GRID / 90.0


def m(t, text, cat="Other", flag=None, scope=None, sector=np.nan, lap=1):
    return {"Time": BASE + pd.Timedelta(seconds=t), "t": float(t), "Category": cat,
            "Message": text, "Flag": flag, "Scope": scope, "Sector": sector, "Lap": lap}


def frame(rows):
    return pd.DataFrame(rows)


def test_safety_car_period_and_its_pit_in_times():
    d = frame([
        m(100, "SAFETY CAR DEPLOYED", "SafetyCar"),
        m(400, "SAFETY CAR IN THIS LAP", "SafetyCar"),
        m(480, "SAFETY CAR LIGHTS OFF"),
        m(510, "TRACK CLEAR", "Flag", "CLEAR", "Track"),
    ])
    periods = rcc.build_periods(d, GRID, LEAD, 4000.0)
    assert len(periods) == 1
    p = periods[0]
    assert (p["kind"], p["t0"], p["t1"]) == ("SC", 100.0, 510.0)
    assert p["t_in"] == 400.0 and p["t_off"] == 480.0
    assert p["p0"] == pytest.approx(100 / 90)
    assert p["p1"] == pytest.approx(510 / 90)


def test_vsc_period_and_both_wordings():
    d = frame([m(1000, "VSC DEPLOYED", "SafetyCar"), m(1090, "VSC ENDING", "SafetyCar"),
               m(2000, "VIRTUAL SAFETY CAR DEPLOYED", "SafetyCar"),
               m(2060, "VIRTUAL SAFETY CAR ENDING", "SafetyCar")])
    got = [(p["kind"], p["t0"], p["t1"]) for p in rcc.build_periods(d, GRID, LEAD, 4000.0)]
    assert got == [("VSC", 1000.0, 1090.0), ("VSC", 2000.0, 2060.0)]


def test_red_flag_runs_to_pit_exit_open_and_ignores_infringement_notes():
    d = frame([
        m(1900, "INCIDENT INVOLVING CAR 10 (GAS) NOTED - RED FLAG INFRINGEMENT"),
        m(2000, "RED FLAG", "Flag", "RED", "Track"),
        m(2100, "RACE WILL RESUME AT 15:45"),
        m(2600, "GREEN LIGHT - PIT EXIT OPEN", "Flag", "GREEN", "Track"),
    ])
    got = [(p["kind"], p["t0"], p["t1"]) for p in rcc.build_periods(d, GRID, LEAD, 4000.0)]
    assert got == [("RED", 2000.0, 2600.0)]


def test_safety_car_turns_into_red_and_back():
    d = frame([
        m(100, "SAFETY CAR DEPLOYED", "SafetyCar"),
        m(300, "RED FLAG", "Flag", "RED", "Track"),
        m(700, "SAFETY CAR DEPLOYED", "SafetyCar"),
        m(900, "SAFETY CAR IN THIS LAP", "SafetyCar"),
        m(960, "TRACK CLEAR", "Flag", "CLEAR", "Track"),
    ])
    got = [(p["kind"], p["t0"], p["t1"]) for p in rcc.build_periods(d, GRID, LEAD, 4000.0)]
    assert got == [("SC", 100.0, 300.0), ("RED", 300.0, 700.0), ("SC", 700.0, 960.0)]


def test_formation_lap_is_ignored_and_an_open_period_closes_at_the_end():
    d = frame([m(10, "FORMATION LAP(S) BEHIND SAFETY CAR"),
               m(3500, "SAFETY CAR DEPLOYED", "SafetyCar")])
    got = [(p["kind"], p["t0"], p["t1"]) for p in rcc.build_periods(d, GRID, LEAD, 4000.0)]
    assert got == [("SC", 3500.0, 4000.0)]


def test_steward_status():
    d = frame([
        m(10, "FIA STEWARDS: INCIDENT INVOLVING CARS 77 (BOT) AND 11 (PER) UNDER INVESTIGATION"),
        m(20, "FIA STEWARDS: 10 SECOND TIME PENALTY FOR CAR 1 (VER) - CAUSING A COLLISION"),
        m(30, "FIA STEWARDS: INCIDENT INVOLVING CAR 77 (BOT) NO FURTHER ACTION"),
        m(40, "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 11 (PER) - SPEEDING IN THE PIT LANE"),
        m(50, "FIA STEWARDS: PENALTY SERVED FOR CAR 11 (PER)"),
    ])
    out = rcc.steward_status(d, ["BOT", "PER", "VER", "HAM"])
    assert out == {"BOT": "", "PER": "served", "VER": "PEN 10s", "HAM": ""}


def test_deleted_laps():
    d = frame([
        m(50, "CAR 63 (RUS) TIME 1:20.011 DELETED - TRACK LIMITS AT TURN 12 LAP 5 11:30:13"),
        m(60, "CAR 44 (HAM) TIME 1:21.500 DELETED - TRACK LIMITS AT TURN 4 LAP 7 11:32:00"),
        m(70, "WAVED BLUE FLAG FOR CAR 77 (BOT) TIMED AT 20:38:16"),
    ])
    out = rcc.deleted_laps(d)
    assert list(out["driver"]) == ["RUS", "HAM"]
    assert list(out["lap"]) == [5, 7]
    assert out.iloc[0]["reason"] == "TRACK LIMITS AT TURN 12"


def test_tz_offset_from_a_quoted_local_time():
    d = frame([m(16 * 60, "WAVED BLUE FLAG FOR CAR 77 (BOT) TIMED AT 20:16:00")])
    assert rcc.estimate_tz_offset(d) == 8 * 3600
    assert rcc.estimate_tz_offset(frame([m(10, "TRACK CLEAR")])) is None


def test_resume_targets_use_the_offset():
    d = frame([m(1800, "RACE WILL RESUME AT 20:45")])       # 12:30 UTC; +8 h means 12:45 UTC
    assert rcc.resume_targets(d, 8 * 3600) == [(1800.0, 2700.0)]
    assert rcc.resume_targets(d, None) == []


def test_build_events_keeps_flags_and_steward_decisions():
    d = frame([
        m(50, "TRACK CLEAR", "Flag", "CLEAR", "Track"),
        m(60, "YELLOW IN TRACK SECTOR 6", "Flag", "YELLOW", "Sector", 6.0, 3),
        m(70, "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 44 (HAM)", lap=4),
        m(80, "SAFETY CAR DEPLOYED", "SafetyCar", lap=5),
    ])
    ev = rcc.build_events(d, 0.0, 4000)
    assert [round(e["t"]) for e in ev] == [60, 70, 80]
    assert ev[0]["label"].startswith("L3 | 1:00 | YELLOW IN TRACK SECTOR 6")

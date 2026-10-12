#!/usr/bin/env python3
"""Race scrubber round three: race-control logic moved into app/racecontrol.py (with tests), a
red-flag countdown with skip-to-restart, lap-deletion counts, and an 'if pit now' column.
Safe to run twice (the previous page is kept as 8_Race_scrubber.py.bak7).

Run from the project folder:  python add_scrubber_v3.py
"""

import py_compile
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app" / "engine.py").exists():
    sys.exit("Run this from ~/Desktop/f1-pitwall (app/engine.py not found here).")


def note(ok: bool, msg: str) -> None:
    print(("OK       " if ok else "SKIPPED  ") + msg)


RACECONTROL = '''
"""Pure parsers for race control messages: flag periods, events, stewards' status, lap deletions
and restart times. No Streamlit and no file access, so they can be tested directly.

Expects a DataFrame with the columns Time (UTC timestamp), t (session seconds), Category, Message,
Flag, Scope, Sector and Lap."""

import re
from collections import Counter

import numpy as np
import pandas as pd


def steward_status(rc, names):
    """Latest investigation / penalty state per driver from the message text."""
    out = {n: "" for n in names}
    for msg in rc["Message"].astype(str):
        up = msg.upper()
        for c in re.findall(r"\\(([A-Z]{3})\\)", up):
            if c not in out:
                continue
            if "NO FURTHER" in up or "NO INVESTIGATION" in up:
                out[c] = ""
            elif "PENALTY SERVED" in up:
                out[c] = "served"
            elif "PENALTY" in up:
                m = re.search(r"(\\d+) SECOND", up)
                out[c] = f"PEN {m.group(1)}s" if m else "PEN"
            elif "UNDER INVESTIGATION" in up or "NOTED" in up:
                out[c] = "INV"
    return out


def build_periods(d, grid, lead, end):
    """Safety car, VSC and red flag periods (session seconds) from the message wording.

    grid / lead: the leader's progress over time, used to place each period on the lap axis."""
    periods, cur = [], None

    def close(t1):
        nonlocal cur
        if cur is not None:
            cur["t1"] = t1
            periods.append(cur)
            cur = None

    for r in d.itertuples():
        msg = str(r.Message).upper()
        flag = str(r.Flag).upper() if pd.notna(r.Flag) else ""
        t = float(r.t)
        if "BEHIND SAFETY CAR" in msg or "FORMATION" in msg:
            continue
        is_red = (flag == "RED" or msg.startswith("RED FLAG")) and "INFRINGEMENT" not in msg
        is_sc = "SAFETY CAR DEPLOYED" in msg and "VIRTUAL" not in msg
        is_vsc = "VSC DEPLOYED" in msg or "VIRTUAL SAFETY CAR DEPLOYED" in msg
        is_vsc_end = "VSC ENDING" in msg or "VIRTUAL SAFETY CAR ENDING" in msg
        if is_red:
            if not (cur and cur["kind"] == "RED"):
                close(t)
                cur = {"kind": "RED", "t0": t}
            continue
        if cur and cur["kind"] == "RED":
            if is_sc or "PIT EXIT OPEN" in msg or "TRACK CLEAR" in msg or "RACE START" in msg:
                close(t)
            else:
                continue                      # still red-flagged
        if is_sc:
            close(t)
            cur = {"kind": "SC", "t0": t}
        elif is_vsc:
            close(t)
            cur = {"kind": "VSC", "t0": t}
        elif cur and cur["kind"] == "SC":
            if "LIGHTS OFF" in msg:
                cur.setdefault("t_off", t)
            elif "IN THIS LAP" in msg:
                cur.setdefault("t_in", t)
            elif "TRACK CLEAR" in msg:
                close(t)
        elif cur and cur["kind"] == "VSC" and is_vsc_end:
            close(t)
    close(end)
    periods = [q for q in periods if q["t1"] > q["t0"]]
    for q in periods:
        q["p0"] = float(np.interp(q["t0"], grid, lead))
        q["p1"] = float(np.interp(q["t1"], grid, lead))
    return periods


def build_events(d, start, duration):
    """Race events for a jump-to-event box: safety cars, red flags, yellows, stewards' decisions."""
    out, seen = [], set()
    for r in d.itertuples():
        msg = str(r.Message).upper()
        flag = str(r.Flag).upper() if pd.notna(r.Flag) else ""
        scope = str(r.Scope) if pd.notna(r.Scope) else ""
        keep = (str(r.Category) == "SafetyCar" or flag in ("RED", "CHEQUERED")
                or msg.startswith("RED FLAG")
                or (scope == "Sector" and flag in ("YELLOW", "DOUBLE YELLOW"))
                or ("FIA STEWARDS" in msg and ("PENALTY" in msg or "INVESTIGAT" in msg)))
        t_race = float(r.t) - start
        if not keep or t_race < -5 or t_race > duration + 5:
            continue
        sig = (round(t_race), msg)
        if sig in seen:
            continue
        seen.add(sig)
        lap = int(r.Lap) if pd.notna(r.Lap) else None
        mm, ss = divmod(int(max(0, t_race)), 60)
        out.append({"t": max(0.0, t_race),
                    "label": f"L{lap if lap is not None else '-'} | {mm}:{ss:02d} | {msg[:80]}"})
    return out[:200]


def deleted_laps(d):
    """Lap-time deletions (track limits and similar) from messages such as
    'CAR 63 (RUS) TIME 1:20.011 DELETED - TRACK LIMITS AT TURN 12 LAP 5 11:30:13'."""
    rows = []
    for r in d.itertuples():
        up = str(r.Message).upper()
        if "DELETED" not in up:
            continue
        m = re.search(r"\\(([A-Z]{3})\\)", up)
        if not m:
            continue
        lap = re.search(r"\\bLAP (\\d+)\\b", up)
        reason = up.split(" - ", 1)[1] if " - " in up else ""
        reason = re.sub(r"\\s*\\bLAP \\d+.*$", "", reason).strip()
        rows.append({"t": float(r.t), "driver": m.group(1),
                     "lap": int(lap.group(1)) if lap else None, "reason": reason})
    return pd.DataFrame(rows, columns=["t", "driver", "lap", "reason"])


def estimate_tz_offset(d):
    """Local-time offset from UTC in seconds, from messages that quote a local clock time
    (for example 'TIMED AT 20:38:16' next to a UTC timestamp of 12:38:16). None if unknown."""
    votes = Counter()
    for r in d.itertuples():
        text = str(r.Message).upper()
        if "RESUME" in text or "ESTIMATED" in text:
            continue
        for hh, mm, ss in re.findall(r"\\b(\\d{1,2}):(\\d{2}):(\\d{2})\\b", text):
            local = int(hh) * 3600 + int(mm) * 60 + int(ss)
            ts = pd.Timestamp(r.Time)
            utc = ts.hour * 3600 + ts.minute * 60 + ts.second
            diff = (local - utc + 12 * 3600) % 86400 - 12 * 3600
            off = int(round(diff / 900.0)) * 900
            if -12 * 3600 <= off <= 14 * 3600:
                votes[off] += 1
    return votes.most_common(1)[0][0] if votes else None


def resume_targets(d, tz_offset):
    """(session second of the announcement, session second of the announced restart)."""
    out = []
    if tz_offset is None:
        return out
    for r in d.itertuples():
        up = str(r.Message).upper()
        m = re.search(r"(?:RESUME AT|RESUMPTION -) (\\d{1,2}):(\\d{2})", up)
        if not m:
            continue
        local = int(m.group(1)) * 3600 + int(m.group(2)) * 60
        ts = pd.Timestamp(r.Time)
        msg_utc = ts.hour * 3600 + ts.minute * 60 + ts.second
        delta = (local - tz_offset - msg_utc) % 86400
        if delta > 43200:
            delta -= 86400
        out.append((float(r.t), float(r.t) + delta))
    return out
'''

REJOIN_LIVE = '''
# ---- live rejoin prediction ------------------------------------------------------------

def rejoin_live(drivers, frames, name, T, loss, pace_cache=None):
    """Predicted position if `name` pitted at session time T, from the race-state engine.

    A car ends up ahead after the stop if it is within `loss` seconds of the driver, ahead or
    behind. Cars behind are extrapolated at their recent pace. Not modelled: other cars pitting,
    traffic after the stop, safety cars. Returns None for a car that has finished or retired."""
    di = drivers[name]
    if T > di["last_end"] + 1:
        return None
    p_i = float(np.interp(T, di["tv"], di["pv"], left=0.0, right=di["pv"][-1]))
    own = pace(frames[name], int(np.floor(p_i)) + 1) if name in frames else float("nan")
    fallback = own if not np.isnan(own) else 95.0
    ahead = 1
    for j, dj in drivers.items():
        if j == name or T > dj["last_end"] + 1:
            continue
        p_j = float(np.interp(T, dj["tv"], dj["pv"], left=0.0, right=dj["pv"][-1]))
        if p_j > p_i:
            pv = dj["pv_inc"]
            g = 1e9 if (p_i < pv[0] or p_i > pv[-1]) else T - float(np.interp(p_i, pv, dj["tv"]))
        else:
            lap_j = int(np.floor(p_j)) + 1
            if pace_cache is not None and (j, lap_j) in pace_cache:
                pace_j = pace_cache[(j, lap_j)]
            else:
                pace_j = pace(frames[j], lap_j) if j in frames else float("nan")
                if pace_cache is not None:
                    pace_cache[(j, lap_j)] = pace_j
            if np.isnan(pace_j):
                pace_j = fallback
            g = -(p_i - p_j) * pace_j
        ahead += int(g + loss > 0)
    return ahead
'''

TEST_RACECONTROL = '''
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
'''

TEST_ENGINE_APPEND = '''

def test_rejoin_live_on_the_synthetic_circuit(lake):
    import pitwall as pw
    import racelib as rl

    state = eg.build(2099, 1, "R")
    frames = rl.driver_frames(pw.laps(2099, 1, "R"))
    drivers = state["drivers"]
    # at t=200 AAA leads BBB by about 2.2 s and CCC by about 11 s
    assert rl.rejoin_live(drivers, frames, "AAA", 200.0, 22.4) == 3
    assert rl.rejoin_live(drivers, frames, "AAA", 200.0, 5.0) == 2
    assert rl.rejoin_live(drivers, frames, "AAA", 200.0, 1.0) == 1
'''

PAGE = '''
import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as eg
import pitwall as pw
import racecontrol as rcc
import racelib as rl

import time

st.set_page_config(page_title="Race scrubber", layout="wide")
st.title("Race scrubber")

p = pw.pick_session(need_telemetry=True, key="scrub")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
state = eg.build(year, rnd, code)
if state is None:
    st.error("No usable position data for this session, so the race state cannot be built.")
    st.stop()
laps = pw.laps(year, rnd, code)
drv = pw.drivers(year, rnd, code)
colors = dict(zip(drv["Driver"], drv["color"]))
numbers = dict(zip(drv["Driver"], drv["number"]))
names = list(state["drivers"])
imp = pw.imperial()          # sidebar widget: must live outside the fragment

duration = int(state["end"] - state["start"])
last_lap = max(1, int(np.ceil(state["lead"][-1])))
key = f"scrub_{year}_{rnd}_{code}"
play_key, speed_key = f"{key}_play", f"{key}_speed"
clock_key, tick_key, ev_key = f"{key}_clock", f"{key}_tick", f"{key}_event"
st.session_state.setdefault(key, min(60, duration))
st.session_state.setdefault(play_key, False)
st.session_state.setdefault(speed_key, 4)
st.session_state.setdefault(ev_key, -1)
L_m = state["L"] / 10.0
rot = p.get("rotation")
has_rot = rot is not None and pd.notna(rot)
PIT_LOSS = 22.4

SPEEDS = [0.5, 1, 2, 4, 5, 10, 20, 30, 60]
SKIPS = [("-5m", -300), ("-1m", -60), ("-30s", -30), ("-5s", -5),
         ("+5s", 5), ("+30s", 30), ("+1m", 60), ("+5m", 300)]
FLAG_STYLE = {"YEL": ("Yellow", "#ffd60a"), "VSC": ("Virtual safety car", "#ff9f1c"),
              "SC": ("Safety car", "#e76f51"), "RED": ("Red flag", "#d00000")}
SEC_STYLE = {"purple": "background-color: #7b2cbf; color: #ffffff",
             "green": "background-color: #2d6a4f; color: #ffffff",
             "yellow": "background-color: #ffd166; color: #111111"}
LABEL_POS = ["top center", "bottom center", "middle right", "middle left"]
flags = rl.flag_laps(laps)
frames = rl.driver_frames(laps)
pace_cache = {}

_seg = np.sqrt((np.diff(state["ref_xy"], axis=0) ** 2).sum(1))
_s = np.concatenate([[0.0], np.cumsum(_seg)])


def point_at(frac):
    """A point on the reference line, as a fraction of the lap from the start/finish line."""
    s = (frac % 1.0) * _s[-1]
    return np.array([np.interp(s, _s, state["ref_xy"][:, 0]),
                     np.interp(s, _s, state["ref_xy"][:, 1])])


def t_at(name, P):
    d = state["drivers"][name]
    pv = d["pv_inc"]
    if P < pv[0] or P > pv[-1]:
        return np.nan
    return float(np.interp(P, pv, d["tv"]))


def rel_gap_text(ref, name, p_ref, p_name, T):
    diff = p_ref - p_name            # positive: `name` is behind `ref`
    if abs(diff) >= 1.0:
        n = int(np.floor(abs(diff) + 1e-9))
        return f"{'+' if diff > 0 else '-'}{n} lap" + ("s" if n > 1 else "")
    if diff > 0:
        t = t_at(ref, p_name)
        return "" if np.isnan(t) else f"+{T - t:.1f}"
    t = t_at(name, p_ref)
    return "" if np.isnan(t) else f"-{T - t:.1f}"


# ---- race control messages on the race clock ----
@st.cache_data(show_spinner=False)
def utc_offset(year: int, rnd: int, code: str):
    """UTC clock time of session second zero, from the first position sample."""
    path = pw.part("telemetry_pos", year, rnd, code)
    con = duckdb.connect()
    try:
        d, s = con.sql("SELECT date_utc, session_time_s FROM read_parquet('" + str(path) + "') "
                       "ORDER BY session_time_s LIMIT 1").fetchone()
    finally:
        con.close()
    return pd.Timestamp(d) - pd.Timedelta(seconds=float(s))


def prepare_rc():
    rc_all = pw.read("race_control", year, rnd, code)
    if rc_all.empty or not {"Time", "Message", "Category", "Flag"} <= set(rc_all.columns):
        return None
    try:
        off = utc_offset(year, rnd, code)
    except Exception:
        return None
    d = rc_all.copy()
    d["t"] = (pd.to_datetime(d["Time"]) - off).dt.total_seconds()
    d = d.sort_values("t").reset_index(drop=True)
    if not ((d["t"] > -600) & (d["t"] < state["end"] + 1800)).any():
        return None                          # the clock mapping looks wrong: switch the feature off
    return d


def build_marshal(d):
    """Marshal-sector extents along the reference line, and yellow / clear events in session seconds."""
    ms = pw.read("circuit_marshal_sectors", year, rnd, code)
    if ms.empty or not {"X", "Y", "Number"} <= set(ms.columns):
        return None
    if not {"Scope", "Flag", "Sector"} <= set(d.columns):
        return None
    s_pts, off = eg.project(ms[["X", "Y"]].to_numpy(float), state["ref_xy"], _s)
    if float(np.median(off)) > 500:          # over 50 m from the track: a different coordinate frame
        return None
    frac = s_pts / _s[-1]
    order = np.argsort(frac)
    starts = frac[order]
    ends = np.roll(starts, -1)
    ends[-1] += 1.0
    nums = ms["Number"].to_numpy()[order].astype(int)
    extents = {int(n): (float(a), float(b)) for n, a, b in zip(nums, starts, ends)}
    events_ = []
    for r in d[d["Scope"].isin(["Sector", "Track"]) & d["Flag"].notna()].itertuples():
        flag = str(r.Flag).upper()
        if r.Scope == "Track" and flag == "CLEAR":
            events_.append((float(r.t), "all", "CLEAR"))
        elif r.Scope == "Sector" and pd.notna(r.Sector):
            events_.append((float(r.t), int(r.Sector), flag))
    return {"extents": extents, "events": events_} if events_ else None


def yellow_now(t_now):
    active = {}
    for t, who, flag in marshal["events"]:
        if t > t_now:
            break
        if who == "all":
            active = {}
        elif flag in ("YELLOW", "DOUBLE YELLOW"):
            active[who] = flag
        elif flag == "CLEAR":
            active.pop(who, None)
    return active


rcd = prepare_rc()
periods = rcc.build_periods(rcd, state["grid"], state["lead"], state["end"]) if rcd is not None else None
events = rcc.build_events(rcd, state["start"], duration) if rcd is not None else []
marshal = build_marshal(rcd) if rcd is not None else None
dels = (rcc.deleted_laps(rcd) if rcd is not None
        else pd.DataFrame(columns=["t", "driver", "lap", "reason"]))
tz_off = rcc.estimate_tz_offset(rcd) if rcd is not None else None
resumes = rcc.resume_targets(rcd, tz_off) if rcd is not None else []


def sc_marker_on(T_s, lead_lap_):
    if periods is None:
        return flags.get(lead_lap_) == "SC"
    for q in periods:
        if q["kind"] == "SC":
            end_m = q.get("t_off") or ((q["t_in"] + 60.0) if q.get("t_in") else q["t1"])
            if q["t0"] <= T_s <= min(end_m, q["t1"] + 1):
                return True
    return False


@st.cache_data(show_spinner=False)
def car_arrays(year: int, rnd: int, code: str, num: int):
    df = pw.read("telemetry_car", year, rnd, code, f"driver_number = {num}")
    if df.empty:
        return None
    df = df.sort_values("session_time_s")
    out = {k: pd.to_numeric(df[k], errors="coerce").to_numpy(float)
           for k in ("session_time_s", "speed", "throttle", "ngear", "drs", "rpm")}
    out["brake"] = df["brake"].fillna(False).to_numpy(bool)
    out["rpm_max"] = float(np.nanmax(out["rpm"])) if np.isfinite(out["rpm"]).any() else 15000.0
    return out


def car_at(arr, t_now):
    t = arr["session_time_s"]
    i = int(np.clip(np.searchsorted(t, t_now), 1, len(t) - 1))
    if abs(t[i - 1] - t_now) < abs(t[i] - t_now):
        i -= 1
    if abs(t[i] - t_now) > 2.0:
        return None
    return {k: arr[k][i] for k in ("speed", "throttle", "ngear", "drs", "brake", "rpm")}


def neighbour_text(label, other, secs, d_progress):
    if other is None or d_progress >= 1.0:
        return f"{label}: -"
    gap = "-" if pd.isna(secs) else f"{secs:.2f} s"
    return f"{label} ({other}): {gap} ({d_progress * L_m:.0f} m)"


def add_cars(fig, sub, symbol, size, opacity, ring, text_size, grey=False):
    if sub.empty:
        return
    fig.add_trace(go.Scatter(
        x=sub["px"], y=sub["py"], mode="markers+text", text=sub["driver"], showlegend=False,
        textposition=[LABEL_POS[int(q) % 4] for q in sub["pos"]],
        textfont=dict(size=text_size), opacity=opacity,
        marker=dict(size=size, symbol=symbol, line=dict(width=ring, color="#ffffff"),
                    color=["#999999" if grey else colors.get(d, "#888888") for d in sub["driver"]]),
        hovertext=[f"P{r.pos} {r.driver}" for r in sub.itertuples()], hoverinfo="text"))


def bump(delta: int) -> None:
    st.session_state[key] = int(min(duration, max(0, st.session_state[key] + delta)))


def to_time(t_abs: float) -> None:
    st.session_state[key] = int(min(duration, max(0, t_abs - state["start"] - 2)))


def to_lap() -> None:
    n = int(st.session_state[f"{key}_lap"])
    idx = int(np.searchsorted(state["lead"], n - 1))
    t = state["grid"][min(idx, len(state["grid"]) - 1)] - state["start"]
    st.session_state[key] = int(min(duration, max(0, t)))


def to_event() -> None:
    i = st.session_state[ev_key]
    if i is not None and i >= 0:
        st.session_state[key] = int(min(duration, max(0, events[i]["t"] - 8)))
    st.session_state[ev_key] = -1


def toggle_play() -> None:
    turning_on = not st.session_state[play_key]
    if turning_on and st.session_state[key] >= duration - 1:
        st.session_state[key] = 0
    st.session_state[play_key] = turning_on
    st.session_state[tick_key] = time.time()
    st.session_state[clock_key] = float(st.session_state[key])


# ---- playback controls: outside the fragment, so a click re-evaluates the refresh interval ----
pc1, pc2, pc3, pc4 = st.columns([1, 1, 2, 4])
pc1.button("Pause" if st.session_state[play_key] else "Play", on_click=toggle_play,
           key=f"{key}_playbtn")
pc2.selectbox("Speed", SPEEDS, format_func=lambda v: f"{v:g}x", key=speed_key,
              label_visibility="collapsed")
if events:
    pc3.selectbox("Jump to event", [-1] + list(range(len(events))), key=ev_key, on_change=to_event,
                  format_func=lambda i: "Jump to a race event" if i < 0 else events[i]["label"],
                  label_visibility="collapsed")
pc4.caption("Auto-play refreshes about once a second, so fast speeds move in jumps.")


def render() -> None:
    if st.session_state[play_key]:
        now = time.time()
        dt = max(0.0, now - st.session_state.get(tick_key, now))
        st.session_state[tick_key] = now
        clock = st.session_state.get(clock_key, float(st.session_state[key]))
        if int(clock) != st.session_state[key]:      # the slider or a button moved it: re-sync
            clock = float(st.session_state[key])
        clock += st.session_state[speed_key] * dt
        st.session_state[clock_key] = clock
        if clock >= duration:
            st.session_state[key] = duration
            st.session_state[play_key] = False
            st.rerun(scope="app")
        st.session_state[key] = int(clock)

    timeline_box = st.container()

    bcols = st.columns([1] * 8 + [1.2, 1.7])
    for col, (label, delta) in zip(bcols[:8], SKIPS):
        col.button(label, on_click=bump, args=(delta,), key=f"{key}_skip{delta}")
    bcols[8].number_input("Lap", 1, last_lap, 1, key=f"{key}_lap", label_visibility="collapsed")
    bcols[9].button("Go to lap", on_click=to_lap)

    t_rel = st.slider("Seconds since the start", 0, duration, key=key)
    f1c, f2c = st.columns([3, 1])
    follow = f1c.multiselect("Follow drivers (highlighted on the map, live panel below)",
                             names, max_selections=3, key=f"{key}_follow")
    ref_choice = f2c.selectbox("Compare gaps against", ["(none)"] + names, key=f"{key}_ref")
    ref = None if ref_choice == "(none)" else ref_choice
    T = state["start"] + t_rel
    snap = eg.snapshot(state, T)
    m, s = divmod(int(t_rel), 60)
    lead_lap = int(min(np.floor(snap["P"].iloc[0]) + 1, last_lap))
    playing = f" | playing at {st.session_state[speed_key]:g}x" if st.session_state[play_key] else ""
    active = [FLAG_STYLE[q["kind"]][0].upper() for q in (periods or []) if q["t0"] <= T <= q["t1"]]
    tag = f" | {' / '.join(active)}" if active else ""
    st.caption(f"Race time {m}:{s:02d} | leader on lap {lead_lap} of {last_lap}{tag}{playing}")

    red = next((q for q in (periods or []) if q["kind"] == "RED" and q["t0"] <= T <= q["t1"]), None)
    if red is not None:
        ann = [r_ for r_ in resumes if red["t0"] <= r_[0] <= T]
        if ann:
            remaining = ann[-1][1] - T
            when = (f"restart announced in {int(remaining // 60)}:{int(remaining % 60):02d}"
                    if remaining > 0 else "restart is due now")
        else:
            when = "no restart time announced yet"
        w1, w2 = st.columns([6, 1])
        w1.warning(f"Red flag: {when}.")
        w2.button("Skip to restart", on_click=to_time, args=(red["t1"],),
                  key=f"{key}_skip_restart")

    rc = pw.read("race_control", year, rnd, code)
    rc_up = pd.DataFrame()
    if not rc.empty and "Lap" in rc.columns:
        rc_up = rc[pd.to_numeric(rc["Lap"], errors="coerce") <= lead_lap]
    stew = (rcc.steward_status(rc_up, names)
            if (not rc_up.empty and "Message" in rc_up.columns) else {})

    # ---- flag timeline: exact safety car / VSC / red periods when the messages allow it ----
    with timeline_box:
        tl = go.Figure()
        tl.add_trace(go.Bar(x=[n - 0.5 for n in range(1, last_lap + 1)], y=[1] * last_lap, width=1,
                            name="Green", marker=dict(color="#2e7d4f", line=dict(width=0)),
                            opacity=0.55, hoverinfo="skip"))
        yel = [n for n, c in flags.items() if c == "YEL"]
        if yel:
            tl.add_trace(go.Bar(x=[n - 0.5 for n in yel], y=[1] * len(yel), width=1, name="Yellow",
                                marker=dict(color=FLAG_STYLE["YEL"][1], line=dict(width=0)),
                                hovertext=[f"lap {n}: yellow" for n in yel], hoverinfo="text"))
        if periods is not None:
            for kind in ("VSC", "SC", "RED"):
                label, colr = FLAG_STYLE[kind]
                tl.add_trace(go.Bar(x=[None], y=[None], name=label, marker=dict(color=colr)))
            for q in periods:
                tl.add_vrect(x0=q["p0"], x1=max(q["p1"], q["p0"] + 0.2), line_width=0,
                             fillcolor=FLAG_STYLE[q["kind"]][1], opacity=0.95, layer="above")
        else:
            for kind in ("VSC", "SC", "RED"):
                label, colr = FLAG_STYLE[kind]
                ls = [n for n, c in flags.items() if c == kind]
                if ls:
                    tl.add_trace(go.Bar(x=[n - 0.5 for n in ls], y=[1] * len(ls), width=1,
                                        name=label, marker=dict(color=colr, line=dict(width=0)),
                                        hovertext=[f"lap {n}: {label}" for n in ls],
                                        hoverinfo="text"))
        tl.add_vline(x=float(snap["P"].iloc[0]), line_width=3, line_color="#6a00ff")
        tl.update_layout(barmode="overlay", bargap=0, height=100, uirevision="timeline",
                         margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=1.5, x=0))
        tl.update_xaxes(range=[0, last_lap])
        tl.update_yaxes(visible=False, range=[0, 1])
        st.plotly_chart(tl)

    # ---- weather strip ----
    w = pw.read("weather", year, rnd, code)
    if not w.empty:
        wr = w.loc[(w["Time_s"] - T).abs().idxmin()]
        if abs(wr["Time_s"] - T) < 300:
            cw = st.columns(5)
            cw[0].metric("Air", f"{pw.tmp(wr['AirTemp'], imp):.1f} {pw.tmp_unit(imp)}")
            cw[1].metric("Track", f"{pw.tmp(wr['TrackTemp'], imp):.1f} {pw.tmp_unit(imp)}")
            cw[2].metric("Humidity", f"{wr['Humidity']:.0f}%")
            cw[3].metric("Wind", f"{pw.spd(wr['WindSpeed'] * 3.6, imp):.0f} {pw.spd_unit(imp)}")
            cw[4].metric("Rain", "Wet" if wr["Rainfall"] else "Dry")

    rotate_map = has_rot and st.checkbox("Rotate to the official orientation", value=True)

    def tr(a):
        return eg.rotate(a, float(rot)) if rotate_map else a

    outline = tr(state["ref_xy"])
    cars = tr(snap[["x", "y"]].to_numpy())
    snap["px"], snap["py"] = cars[:, 0], cars[:, 1]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=outline[:, 0], y=outline[:, 1], mode="lines",
                             line=dict(color="#777777", width=9), hoverinfo="skip",
                             showlegend=False))
    if marshal is not None:
        for num_, flag_ in yellow_now(T).items():
            ext = marshal["extents"].get(num_)
            if ext is None:
                continue
            pts = tr(np.array([point_at(f_) for f_ in np.linspace(ext[0], ext[1], 30)]))
            fig.add_trace(go.Scatter(
                x=pts[:, 0], y=pts[:, 1], mode="lines", showlegend=False, hoverinfo="text",
                hovertext=f"{flag_.title()} in marshal sector {num_}",
                line=dict(color="#ff9f1c" if flag_ == "DOUBLE YELLOW" else "#ffd60a", width=13)))
    followed = snap["driver"].isin(follow)
    dim = 0.65 if follow else 1.0
    add_cars(fig, snap[(snap["status"] != "OUT") & ~followed], "circle", 12, dim, 1, 10)
    add_cars(fig, snap[(snap["status"] == "OUT") & ~followed], "x", 12, dim, 1, 10, True)
    add_cars(fig, snap[followed], "circle", 20, 1.0, 3, 14)
    if sc_marker_on(T, lead_lap):
        sc_xy = tr(point_at(float(snap["P"].iloc[0]) + 500.0 / L_m).reshape(1, 2))
        fig.add_trace(go.Scatter(
            x=[sc_xy[0, 0]], y=[sc_xy[0, 1]], mode="markers+text", text=["SC"],
            textposition="top center", showlegend=False, hoverinfo="text",
            hovertext="Safety car (simulated: about 500 m ahead of the leader)",
            marker=dict(size=22, color="#ff9f1c", line=dict(width=3, color="#ffffff"))))
    fig.update_layout(height=640, margin=dict(l=0, r=0, t=10, b=0), uirevision="map")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)

    tbl = snap.copy()
    if code in ("R", "S"):
        tbl["grid change"] = [
            "" if (pd.isna(g) or g <= 0) else ("=" if g == q else f"{int(g - q):+d}")
            for g, q in zip(tbl["grid"], tbl["pos"])]
    tbl = tbl.rename(columns={"tyre_age": "age", "last_lap": "last lap", "best_lap": "best lap"})
    tbl["gap"] = [g + " ~" if (a and g) else g for g, a in zip(tbl["gap"], tbl["approx"])]
    rel_col = None
    if ref is not None and ref in set(snap["driver"]):
        p_ref = float(snap.loc[snap["driver"] == ref, "P"].iloc[0])
        rel_col = f"vs {ref}"
        tbl[rel_col] = ["ref" if d_ == ref else rel_gap_text(ref, d_, p_ref, p_d, T)
                        for d_, p_d in zip(tbl["driver"], tbl["P"])]
    pit_col = None
    if code in ("R", "S") and not active:
        preds = [rl.rejoin_live(state["drivers"], frames, d_, T, PIT_LOSS, pace_cache)
                 for d_ in tbl["driver"]]
        pit_col = "if pit now"
        tbl[pit_col] = ["" if pr is None else f"P{pr} ({pr - int(q):+d})"
                        for pr, q in zip(preds, tbl["pos"])]
    tbl["stewards"] = [stew.get(d_, "") for d_ in tbl["driver"]]
    dsub = dels[dels["t"] <= T] if len(dels) else dels
    dcount = dsub.groupby("driver").size().to_dict() if len(dsub) else {}
    tbl["deleted"] = [dcount.get(d_, "") for d_ in tbl["driver"]]
    cols = (["pos", "driver"] + (["grid change"] if "grid change" in tbl else [])
            + ["gap", "interval"] + ([rel_col] if rel_col else []) + ([pit_col] if pit_col else [])
            + ["tyres", "age", "last lap", "S1", "S2", "S3", "best lap", "pits", "status",
               "stewards", "deleted"])
    show = tbl[cols]
    int_s = snap["int_s"].to_numpy()
    fl = snap["fl"].to_numpy()

    def paint(col):
        if col.name == "interval":
            return ["background-color: #ffd166; color: #111111" if (pd.notna(x) and x < 1.0)
                    else "" for x in int_s]
        if col.name == "best lap":
            return ["color: #b048ff; font-weight: 700" if f else "" for f in fl]
        if col.name == "driver":
            return ["font-weight: 700; text-decoration: underline" if d_ in follow else ""
                    for d_ in show["driver"]]
        if col.name in ("S1", "S2", "S3"):
            return [SEC_STYLE.get(c, "") for c in snap[f"c{col.name[1]}"]]
        return [""] * len(col)

    c_map, c_tab = st.columns([5, 6])
    c_map.plotly_chart(fig)
    c_tab.dataframe(show.style.apply(paint, axis=0), hide_index=True, height=640)

    if follow:
        st.subheader("Followed drivers")
        for col, name in zip(st.columns(len(follow)), follow):
            row = snap[snap["driver"] == name].iloc[0]
            i = int(row["pos"]) - 1
            ahead = snap.iloc[i - 1] if i > 0 else None
            behind = snap.iloc[i + 1] if i + 1 < len(snap) else None
            lap_now = int(min(np.floor(row["P"]) + 1, state["drivers"][name]["max_lap"]))
            arr = car_arrays(year, rnd, code, int(numbers[name]))
            v = car_at(arr, T) if arr is not None else None
            with col:
                st.markdown(f"**{name}** | P{int(row['pos'])} | lap {lap_now} | "
                            f"{row['status'] or 'on track'}"
                            + (f" | {stew[name]}" if stew.get(name) else ""))
                st.caption(neighbour_text(
                    "Ahead", None if ahead is None else ahead["driver"], row["int_s"],
                    99.0 if ahead is None else ahead["P"] - row["P"]))
                st.caption(neighbour_text(
                    "Behind", None if behind is None else behind["driver"],
                    None if behind is None else behind["int_s"],
                    99.0 if behind is None else row["P"] - behind["P"]))
                if v is None:
                    st.caption("No telemetry for this moment.")
                    continue
                c1, c2, c3 = st.columns(3)
                c1.metric("Speed", f"{pw.spd(v['speed'], imp):.0f} {pw.spd_unit(imp)}")
                c2.metric("Gear", "-" if np.isnan(v["ngear"]) else f"{int(v['ngear'])}")
                drs = "n/a" if year >= 2026 else ("OPEN" if v["drs"] in (10, 12, 14) else "closed")
                c3.metric("DRS", drs)
                thr = min(100.0, max(0.0, 0.0 if np.isnan(v["throttle"]) else v["throttle"]))
                st.progress(thr / 100.0, text=f"Throttle {thr:.0f}%")
                st.progress(1.0 if v["brake"] else 0.0,
                            text="Brake " + ("ON" if v["brake"] else "off"))
                rpm = 0.0 if np.isnan(v["rpm"]) else float(v["rpm"])
                st.progress(min(1.0, rpm / arr["rpm_max"]), text=f"RPM {rpm:,.0f}")

    st.subheader(f"Race control: latest messages up to lap {lead_lap}")
    if rc.empty or "Lap" not in rc.columns:
        st.caption("No race control messages with lap numbers for this session.")
    else:
        sub = rc_up.tail(8).iloc[::-1]
        rcols = [c for c in ("Lap", "Category", "Flag", "Message") if c in sub.columns]
        if sub.empty:
            st.caption("No messages yet.")
        else:
            st.dataframe(sub[rcols], hide_index=True, height=300)

    with st.expander("Legend"):
        st.markdown(
            "- **Play / Pause, speed, skips and Jump to a race event** sit above the scrubber. "
            "Auto-play refreshes about once a second, so 30x and 60x move in jumps; dragging the "
            "slider while it plays re-syncs it. The event box lists safety cars, VSCs, red flags, "
            "yellow sectors and stewards' penalties and investigations, and jumps to 8 seconds "
            "before the one you pick.\\n"
            "- **Timeline above the slider:** green = normal running. Safety car, virtual safety "
            "car and red flag periods are drawn at their exact start and end, read from the race "
            "control messages (SAFETY CAR DEPLOYED to TRACK CLEAR; VSC DEPLOYED to VSC ENDING). "
            "A red flag runs until the next pit-exit-open, safety car, track-clear or race-start "
            "message, which is my inference: no message says when it ends. Yellow flags are at lap "
            "resolution here. Sessions without usable messages fall back to lap resolution for "
            "everything. The purple line is the leader now.\\n"
            "- **Red flag banner:** shows the time left to the announced restart. Announced times "
            "are local clock times, so the countdown needs the circuit's time zone, which I infer "
            "from messages that quote a local time next to their UTC timestamp. 'Skip to restart' "
            "jumps to the end of the inferred red-flag period.\\n"
            "- **Dots:** team colour, with the driver code. A grey x is a retired car. The orange "
            "**SC** dot is a simulated safety car (no real GPS exists): about 500 m ahead of the "
            "leader from SAFETY CAR DEPLOYED until its lights go off.\\n"
            "- **Yellow track stretches:** marshal sectors under a yellow flag at this moment "
            "(orange for double yellow), from the race control messages, with the message sector "
            "numbers matched to the circuit's marshal sectors. Shown only for circuits with "
            "marshal-sector data.\\n"
            "- **Followed drivers** get a large ringed dot and a panel with gaps ahead and behind "
            "(seconds, and metres along the track), speed, gear, DRS, throttle, brake and RPM.\\n"
            "- **Compare gaps against:** adds a column with every car's gap to the chosen driver "
            "(+ behind them, - ahead of them), useful for watching a pit window.\\n"
            "- **If pit now (races and sprints):** the predicted position if that driver pitted at "
            "this instant, using a 22.4 s pit loss, with the change from the current position. "
            "Cars within the pit loss, ahead or behind, end up in front. Blank under a safety car, "
            "VSC or red flag, which the model was not validated for. Backtest of this live-gap "
            "version on 661 green-flag stops (2025-2026): exact 49.0%, within one place 75.9%. "
            "Not modelled: other cars pitting at the same time, traffic after the stop.\\n"
            "- **~ after a gap:** GPS matching looked unreliable on that car's current lap, so its "
            "progress is estimated from the lap timing.\\n"
            "- **PIT / OUT / FIN:** in the pit lane (with seconds so far) / retired / finished. "
            "**Stewards:** INV = under investigation, PEN 10s = a penalty, served = penalty "
            "served. **Deleted:** lap times deleted so far (track limits and similar), counted from "
            "the race control messages. A message naming two cars marks both.\\n"
            "- **Tyres:** compounds used so far, oldest first (S soft, M medium, H hard, "
            "I intermediate, W wet); age is laps on the current set.\\n"
            "- **S1 / S2 / S3:** the freshest completed sector time. Purple = fastest of anyone so "
            "far, green = the driver's own best, yellow = slower.\\n"
            "- **Yellow interval:** under one second to the car ahead. **Purple best lap:** "
            "fastest lap so far. **Grid change (races and sprints):** places gained (+) or lost "
            "(-).\\n"
            "- **DRS:** open when the code is 10, 12 or 14 (my reading of FastF1's documentation, "
            "not verified against these files). DRS no longer exists in 2026.\\n"
            "- **Wind** is shown in km/h or mph, converted from the feed's m/s (my reading of the "
            "documentation).")
    st.caption(
        "Positions come from GPS; the order and gaps come from each car's progress around the "
        "lap, anchored to the official timing at the line. Tested against the official order at "
        "the two sector timing lines on four races: exact 89-99.8% of the time, within one place "
        "98-100%. Not tested: lap 1 and the start, and races with broken position data. Flag "
        "periods are read from the race control messages.")


st.fragment(run_every=1.0 if st.session_state[play_key] else None)(render)()
'''

(ROOT / "app/racecontrol.py").write_text(RACECONTROL.strip("\n") + "\n")
note(True, "wrote app/racecontrol.py")

rl_path = ROOT / "app/racelib.py"
s = rl_path.read_text()
if "def rejoin_live(" in s:
    note(True, "racelib: rejoin_live already present")
else:
    rl_path.write_text(s.rstrip("\n") + "\n\n\n" + REJOIN_LIVE.strip("\n") + "\n")
    note(True, "racelib: rejoin_live added")

(ROOT / "tests").mkdir(exist_ok=True)
(ROOT / "tests/test_racecontrol.py").write_text(TEST_RACECONTROL.strip("\n") + "\n")
note(True, "wrote tests/test_racecontrol.py")

te = ROOT / "tests/test_engine.py"
if te.exists():
    ts = te.read_text()
    if "test_rejoin_live_on_the_synthetic_circuit" in ts:
        note(True, "tests/test_engine.py: live rejoin test already present")
    else:
        te.write_text(ts.rstrip("\n") + "\n" + TEST_ENGINE_APPEND)
        note(True, "tests/test_engine.py: live rejoin test added")
else:
    note(False, "tests/test_engine.py not found (run add_tests_ci.py first); live rejoin test not added")

page = ROOT / "app/pages/8_Race_scrubber.py"
if page.exists() and not (ROOT / "app/pages/8_Race_scrubber.py.bak7").exists():
    (ROOT / "app/pages/8_Race_scrubber.py.bak7").write_text(page.read_text())
page.write_text(PAGE.strip("\n") + "\n")
note(True, "scrubber page rewritten (previous copy kept as 8_Race_scrubber.py.bak7)")

print("\nChecking that everything compiles:")
bad = 0
for name in ("app/racecontrol.py", "app/racelib.py", "app/pages/8_Race_scrubber.py",
             "tests/test_racecontrol.py", "tests/test_engine.py"):
    f = ROOT / name
    if not f.exists():
        continue
    try:
        py_compile.compile(str(f), doraise=True)
        print("  ok      ", name)
    except py_compile.PyCompileError as e:
        bad += 1
        print("  SYNTAX ERROR in", name, "->", str(e)[:300])
print("\nNow run the tests, then reload the app." if not bad else "\nSend me this output.")

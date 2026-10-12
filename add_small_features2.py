#!/usr/bin/env python3
"""Small additions: more speeds and skips, compare-against driver, pit markers on the lap times
chart, a simulated safety car marker, and penalty / investigation status. Safe to run twice.

Run from the project folder:  python add_small_features2.py
"""

import py_compile
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app" / "engine.py").exists():
    sys.exit("Run this from ~/Desktop/f1-pitwall (app/engine.py not found here).")


def note(ok: bool, msg: str) -> None:
    print(("OK       " if ok else "SKIPPED  ") + msg)


def patch(path: str, old: str, new: str, label: str) -> None:
    f = ROOT / path
    if not f.exists():
        note(False, f"{label}: {path} does not exist")
        return
    s = f.read_text()
    if new in s:
        note(True, f"{label}: already applied")
        return
    n = s.count(old)
    if n != 1:
        note(False, f"{label}: expected 1 match in {path}, found {n}; file not changed")
        return
    f.write_text(s.replace(old, new))
    note(True, f"{label}: applied")


PAGE = '''
import re
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as eg
import pitwall as pw
import racelib as rl

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
clock_key, tick_key = f"{key}_clock", f"{key}_tick"
st.session_state.setdefault(key, min(60, duration))
st.session_state.setdefault(play_key, False)
st.session_state.setdefault(speed_key, 4)
L_m = state["L"] / 10.0
rot = p.get("rotation")
has_rot = rot is not None and pd.notna(rot)

SPEEDS = [0.5, 1, 2, 4, 5, 10, 20, 30, 60]
SKIPS = [("-5m", -300), ("-1m", -60), ("-30s", -30), ("-5s", -5),
         ("+5s", 5), ("+30s", 30), ("+1m", 60), ("+5m", 300)]


def bump(delta: int) -> None:
    st.session_state[key] = int(min(duration, max(0, st.session_state[key] + delta)))


def to_lap() -> None:
    n = int(st.session_state[f"{key}_lap"])
    idx = int(np.searchsorted(state["lead"], n - 1))
    t = state["grid"][min(idx, len(state["grid"]) - 1)] - state["start"]
    st.session_state[key] = int(min(duration, max(0, t)))


def toggle_play() -> None:
    turning_on = not st.session_state[play_key]
    if turning_on and st.session_state[key] >= duration - 1:
        st.session_state[key] = 0
    st.session_state[play_key] = turning_on
    st.session_state[tick_key] = time.time()
    st.session_state[clock_key] = float(st.session_state[key])


FLAG_STYLE = {"YEL": ("Yellow", "#ffd60a"), "VSC": ("Virtual safety car", "#ff9f1c"),
              "SC": ("Safety car", "#e76f51"), "RED": ("Red flag", "#d00000")}
SEC_STYLE = {"purple": "background-color: #7b2cbf; color: #ffffff",
             "green": "background-color: #2d6a4f; color: #ffffff",
             "yellow": "background-color: #ffd166; color: #111111"}
flags = rl.flag_laps(laps)

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


def steward_status(rc, names_):
    """Latest investigation / penalty state per driver from the race control message text."""
    out = {n: "" for n in names_}
    for msg in rc["Message"].astype(str):
        up = msg.upper()
        codes = re.findall(r"\\(([A-Z]{3})\\)", up)
        for c in codes:
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
        textposition="top center", textfont=dict(size=text_size), opacity=opacity,
        marker=dict(size=size, symbol=symbol, line=dict(width=ring, color="#ffffff"),
                    color=["#999999" if grey else colors.get(d, "#888888") for d in sub["driver"]]),
        hovertext=[f"P{r.pos} {r.driver}" for r in sub.itertuples()], hoverinfo="text"))


# ---- playback controls: outside the fragment, so a click re-evaluates the refresh interval ----
pc1, pc2, pc3 = st.columns([1, 1, 6])
pc1.button("Pause" if st.session_state[play_key] else "Play", on_click=toggle_play,
           key=f"{key}_playbtn")
pc2.selectbox("Speed", SPEEDS, format_func=lambda v: f"{v:g}x", key=speed_key,
              label_visibility="collapsed")
pc3.caption("Auto-play refreshes about once a second, so fast speeds move in jumps.")


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
    st.caption(f"Race time {m}:{s:02d} | leader on lap {lead_lap} of {last_lap}{playing}")

    rc = pw.read("race_control", year, rnd, code)
    rc_up = pd.DataFrame()
    if not rc.empty and "Lap" in rc.columns:
        rc_up = rc[pd.to_numeric(rc["Lap"], errors="coerce") <= lead_lap]
    stew = steward_status(rc_up, names) if (not rc_up.empty and "Message" in rc_up.columns) else {}

    # ---- flag timeline (lap resolution) ----
    with timeline_box:
        tl = go.Figure()
        clear = [n for n in range(1, last_lap + 1) if n not in flags]
        if clear:
            tl.add_trace(go.Bar(x=[n - 0.5 for n in clear], y=[1] * len(clear), width=1,
                                name="Green", marker=dict(color="#2e7d4f", line=dict(width=0)),
                                opacity=0.55, hoverinfo="skip"))
        for fc, (label, colr) in FLAG_STYLE.items():
            ls = [n for n, c in flags.items() if c == fc]
            if ls:
                tl.add_trace(go.Bar(x=[n - 0.5 for n in ls], y=[1] * len(ls), width=1, name=label,
                                    marker=dict(color=colr, line=dict(width=0)),
                                    hovertext=[f"lap {n}: {label}" for n in ls], hoverinfo="text"))
        tl.add_vline(x=float(snap["P"].iloc[0]), line_width=3, line_color="#6a00ff")
        tl.update_layout(barmode="overlay", bargap=0, height=100, uirevision="timeline",
                         margin=dict(l=0, r=0, t=0, b=0), legend=dict(orientation="h", y=1.5, x=0))
        tl.update_xaxes(range=[0, last_lap], title_text="Lap")
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
    followed = snap["driver"].isin(follow)
    dim = 0.65 if follow else 1.0
    add_cars(fig, snap[(snap["status"] != "OUT") & ~followed], "circle", 12, dim, 1, 10)
    add_cars(fig, snap[(snap["status"] == "OUT") & ~followed], "x", 12, dim, 1, 10, True)
    add_cars(fig, snap[followed], "circle", 20, 1.0, 3, 14)
    if flags.get(lead_lap) == "SC":
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
    tbl["stewards"] = [stew.get(d_, "") for d_ in tbl["driver"]]
    cols = (["pos", "driver"] + (["grid change"] if "grid change" in tbl else [])
            + ["gap", "interval"] + ([rel_col] if rel_col else [])
            + ["tyres", "age", "last lap", "S1", "S2", "S3", "best lap", "pits", "status",
               "stewards"])
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
            "- **Play / Pause and speed** sit above the scrubber. Auto-play refreshes about once a "
            "second, so 30x and 60x move in jumps; dragging the slider while it plays re-syncs it. "
            "The skip buttons jump 5 s, 30 s, 1 min or 5 min.\\n"
            "- **Timeline above the slider:** green = normal running; yellow, virtual safety car, "
            "safety car and red flag stretches at lap resolution; the purple line is the leader "
            "now.\\n"
            "- **Dots:** team colour, with the driver code. A grey x is a retired car. The orange "
            "**SC** dot is a simulated safety car (no real GPS exists): about 500 m ahead of the "
            "leader on laps flagged safety car.\\n"
            "- **Followed drivers** get a large ringed dot and a panel with gaps ahead and behind "
            "(seconds, and metres along the track), speed, gear, DRS, throttle, brake and RPM.\\n"
            "- **Compare gaps against:** adds a column with every car's gap to the chosen driver "
            "(+ behind them, - ahead of them), useful for watching a pit window.\\n"
            "- **~ after a gap:** GPS matching looked unreliable on that car's current lap, so its "
            "progress is estimated from the lap timing.\\n"
            "- **PIT / OUT / FIN:** in the pit lane / retired / finished. **Stewards:** INV = under "
            "investigation, PEN 10s = a penalty, served = penalty served, read from the text of "
            "the race control messages (a message naming two cars marks both).\\n"
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
        "98-100%. Not tested: lap 1 and the start, and races with broken position data. Flags "
        "are at lap resolution; exact timing needs the track-status data that newer ingests "
        "include.")


st.fragment(run_every=1.0 if st.session_state[play_key] else None)(render)()
'''

f = ROOT / "app/pages/8_Race_scrubber.py"
if f.exists() and not (ROOT / "app/pages/8_Race_scrubber.py.bak5").exists():
    (ROOT / "app/pages/8_Race_scrubber.py.bak5").write_text(f.read_text())
f.write_text(PAGE.strip("\n") + "\n")
note(True, "scrubber page rewritten (previous copy kept as 8_Race_scrubber.py.bak5)")

patch("app/pages/1_Race_explorer.py",
      '        st.plotly_chart(fig)\n        best = d.loc[d.groupby("Driver")["LapTime_s"].idxmin(),',
      '        pit = laps[laps["Driver"].isin(chosen) & laps["PitInTime_s"].notna()]\n'
      '        if not pit.empty:\n'
      '            fig.add_trace(go.Scatter(\n'
      '                x=pit["LapNumber"], y=[float(d["LapTime_s"].min())] * len(pit),\n'
      '                mode="markers", name="Pit in",\n'
      '                marker=dict(symbol="triangle-up", size=11, line=dict(width=1, color="#ffffff"),\n'
      '                            color=[colors.get(x, "#888888") for x in pit["Driver"]]),\n'
      '                hovertext=[f"{r.Driver} pits, lap {int(r.LapNumber)}" for r in pit.itertuples()],\n'
      '                hoverinfo="text"))\n'
      '        st.plotly_chart(fig)\n        best = d.loc[d.groupby("Driver")["LapTime_s"].idxmin(),',
      "Race explorer: pit markers on the lap times chart")

print("\nChecking that everything still compiles:")
bad = 0
for name in ("app/pages/8_Race_scrubber.py", "app/pages/1_Race_explorer.py"):
    try:
        py_compile.compile(str(ROOT / name), doraise=True)
        print("  ok      ", name)
    except py_compile.PyCompileError as e:
        bad += 1
        print("  SYNTAX ERROR in", name, "->", str(e)[:300])
print("\nDone. Reload the app in your browser." if not bad else "\nSend me this output.")

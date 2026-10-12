#!/usr/bin/env python3
"""Adds the Session timing page (qualifying / practice timing screen) and the scrubber's live
pit timer. Safe to run twice.

Run from the project folder:  python add_session_timing.py
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
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import pitwall as pw

st.set_page_config(page_title="Session timing", layout="wide")
st.title("Session timing")

p = pw.pick_session(key="timing")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
laps = pw.laps(year, rnd, code)
drv = pw.drivers(year, rnd, code)
if laps.empty:
    st.error("No lap data for this session.")
    st.stop()
if code in ("R", "S"):
    st.info("This screen is built for qualifying and practice. In a race, best laps and ideal laps "
            "mean less than the running order; the Race explorer and Race scrubber cover races.")
st.caption(f"{p['event']} | {pw.SESSION_NAMES.get(code, code)} | {year}")

colors = dict(zip(drv["Driver"], drv["color"]))
d = laps.copy()
for c in ("Sector1Time_s", "Sector2Time_s", "Sector3Time_s", "LapTime_s", "Time_s"):
    if c not in d.columns:
        d[c] = np.nan
deleted = (d["Deleted"].fillna(False).astype(bool) if "Deleted" in d.columns
           else pd.Series(False, index=d.index))
valid = d[~deleted]
timed = valid[valid["LapTime_s"].notna()]
if timed.empty:
    st.warning("No timed laps in this session.")
    st.stop()

best = (timed.loc[timed.groupby("Driver")["LapTime_s"].idxmin(),
                  ["Driver", "LapNumber", "LapTime_s", "Compound", "TyreLife"]]
        .set_index("Driver"))
sectors = valid.groupby("Driver")[["Sector1Time_s", "Sector2Time_s", "Sector3Time_s"]].min()
counts = timed.groupby("Driver").size().rename("timed")
dels = deleted.groupby(d["Driver"]).sum().rename("deleted")
tbl = best.join(sectors, how="left").join(counts).join(dels)
tbl["ideal"] = tbl[["Sector1Time_s", "Sector2Time_s", "Sector3Time_s"]].sum(axis=1, min_count=3)
tbl = tbl.sort_values("LapTime_s")
fastest = float(tbl["LapTime_s"].min())


def s3(v):
    return "" if pd.isna(v) else f"{v:.3f}"


show = pd.DataFrame({
    "pos": range(1, len(tbl) + 1),
    "driver": list(tbl.index),
    "best lap": [pw.fmt_lap(v) for v in tbl["LapTime_s"]],
    "gap": ["" if i == 0 else f"+{g:.3f}" for i, g in enumerate(tbl["LapTime_s"] - fastest)],
    "lap": tbl["LapNumber"].astype(int).to_numpy(),
    "tyre": tbl["Compound"].fillna("").to_numpy(),
    "age": pd.to_numeric(tbl["TyreLife"], errors="coerce").round().astype("Int64").to_numpy(),
    "S1": [s3(v) for v in tbl["Sector1Time_s"]],
    "S2": [s3(v) for v in tbl["Sector2Time_s"]],
    "S3": [s3(v) for v in tbl["Sector3Time_s"]],
    "ideal lap": [pw.fmt_lap(v) for v in tbl["ideal"]],
    "could gain": [s3(v) for v in (tbl["LapTime_s"] - tbl["ideal"])],
    "timed laps": tbl["timed"].to_numpy(),
    "deleted": tbl["deleted"].fillna(0).astype(int).to_numpy(),
})
SEC = {"S1": "Sector1Time_s", "S2": "Sector2Time_s", "S3": "Sector3Time_s"}
PURPLE = "background-color: #7b2cbf; color: #ffffff"


def paint(col):
    if col.name in SEC:
        v = tbl[SEC[col.name]].to_numpy(float)
    elif col.name == "ideal lap":
        v = tbl["ideal"].to_numpy(float)
    elif col.name == "best lap":
        v = tbl["LapTime_s"].to_numpy(float)
    else:
        return [""] * len(col)
    if np.isnan(v).all():
        return [""] * len(col)
    m = np.nanmin(v)
    return [PURPLE if (pd.notna(x) and abs(x - m) < 1e-6) else "" for x in v]


res = pw.read("results", year, rnd, code)
qcols = [c for c in ("Q1_s", "Q2_s", "Q3_s") if c in res.columns]
show_q = code in ("Q", "SQ", "SS") and qcols and {"Position", "Abbreviation"} <= set(res.columns)

tabs = st.tabs(["Timing", "Progression", "All laps"]
               + (["Qualifying result"] if show_q else [])
               + (["Deleted laps"] if deleted.any() else []))

with tabs[0]:
    st.dataframe(show.style.apply(paint, axis=0), hide_index=True,
                 height=min(900, 40 + 36 * len(show)))
    st.caption("Best laps and sectors come from laps whose time was not deleted. Purple = fastest "
               "of anyone in the session. Ideal lap = the sum of the driver's own three best "
               "sectors; 'could gain' is how much faster it is than their best lap.")

with tabs[1]:
    chosen = st.multiselect("Drivers", list(tbl.index), default=list(tbl.index[:8]), key="tm_prog")
    fig = go.Figure()
    for name in chosen:
        g = timed[timed["Driver"] == name].sort_values("Time_s")
        g = g.assign(so_far=g["LapTime_s"].cummin())
        fig.add_trace(go.Scatter(
            x=g["Time_s"] / 60, y=g["so_far"], mode="lines+markers", name=name,
            line=dict(shape="hv", color=colors.get(name)),
            hovertext=[f"{name} lap {int(n)}: {pw.fmt_lap(v)}" for n, v in
                       zip(g["LapNumber"], g["so_far"])], hoverinfo="text"))
    fig.update_yaxes(range=[fastest - 0.3, fastest * 1.08], title_text="Best lap so far (s)")
    fig.update_xaxes(title_text="Session time (minutes)")
    fig.update_layout(height=560)
    st.plotly_chart(fig)
    st.caption("Each line steps down when the driver sets a faster lap. The vertical range is cut "
               "at 108% of the fastest lap, so early slow laps are off the chart.")

with tabs[2]:
    chosen2 = st.multiselect("Drivers", list(tbl.index), default=list(tbl.index[:8]), key="tm_all")
    cut = st.slider("Hide laps slower than (% of the fastest lap)", 100, 200, 115)
    a = timed[timed["Driver"].isin(chosen2) & (timed["LapTime_s"] <= fastest * cut / 100)].copy()
    if a.empty:
        st.info("No laps to show.")
    else:
        a["minutes"] = a["Time_s"] / 60
        a["lap time"] = a["LapTime_s"].map(pw.fmt_lap)
        fig2 = px.scatter(a, x="minutes", y="LapTime_s", color="Compound",
                          color_discrete_map=pw.COMPOUND_COLORS,
                          hover_data={"Driver": True, "LapNumber": True, "lap time": True,
                                      "TyreLife": True, "minutes": False, "LapTime_s": False},
                          labels={"LapTime_s": "Lap time (s)", "minutes": "Session time (minutes)"})
        fig2.update_layout(height=560)
        st.plotly_chart(fig2)

nxt = 3
if show_q:
    with tabs[nxt]:
        q = res[["Position", "Abbreviation"] + qcols].copy().sort_values("Position")
        names_ = [c.replace("_s", "") for c in qcols]
        for c, nm in zip(qcols, names_):
            q[nm] = q[c].map(pw.fmt_lap)
        st.dataframe(q[["Position", "Abbreviation"] + names_], hide_index=True)
    nxt += 1
if deleted.any():
    with tabs[nxt]:
        dc = [c for c in ("Driver", "LapNumber", "LapTime_s", "DeletedReason") if c in d.columns]
        dd = d[deleted][dc].copy()
        if "LapTime_s" in dd.columns:
            dd["LapTime_s"] = dd["LapTime_s"].map(pw.fmt_lap)
        st.dataframe(dd.rename(columns={"LapTime_s": "lap time"}), hide_index=True)
'''

f = ROOT / "app/pages/9_Session_timing.py"
f.write_text(PAGE.strip("\n") + "\n")
note(True, "Session timing page written (app/pages/9_Session_timing.py)")

patch("app/engine.py",
      '        in_pit = any(a <= T <= b for a, b in d["pit_iv"])\n'
      '        status = "PIT" if in_pit else ""\n',
      '        pit_now = [T - a for a, b in d["pit_iv"] if a <= T <= b]\n'
      '        status = f"PIT {pit_now[0]:.0f}s" if pit_now else ""\n',
      "engine: live pit timer")

print("\nChecking that everything still compiles:")
bad = 0
for name in ("app/pages/9_Session_timing.py", "app/engine.py"):
    try:
        py_compile.compile(str(ROOT / name), doraise=True)
        print("  ok      ", name)
    except py_compile.PyCompileError as e:
        bad += 1
        print("  SYNTAX ERROR in", name, "->", str(e)[:300])
print("\nDone. Reload the app in your browser." if not bad else "\nSend me this output.")

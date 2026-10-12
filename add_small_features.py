#!/usr/bin/env python3
"""Adds the small features to the F1 Pitwall app. Safe to run twice.

  - Timing tower: OUT / PIT status, best lap, pit count, gap to any chosen driver
  - Safety car / VSC / red flag shading on the Lap times chart
  - DRS row in the multi-driver telemetry page (2025 and earlier)
  - Imperial units toggle (mph, deg F) on the weather, track map and comparison pages

Run it from the project folder:  python add_small_features.py
"""

import py_compile
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app" / "pitwall.py").exists():
    sys.exit("Run this from ~/Desktop/f1-pitwall (app/pitwall.py not found here).")


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


def append(path: str, marker: str, block: str, label: str) -> None:
    f = ROOT / path
    s = f.read_text()
    if marker in s:
        note(True, f"{label}: already present")
        return
    f.write_text(s.rstrip("\n") + "\n\n\n" + block.strip("\n") + "\n")
    note(True, f"{label}: added")


def write_page(path: str, text: str, label: str) -> None:
    f = ROOT / path
    if f.exists() and not (ROOT / (path + ".bak")).exists():
        (ROOT / (path + ".bak")).write_text(f.read_text())
    f.write_text(text.strip("\n") + "\n")
    note(True, f"{label}: written (old copy kept as {path}.bak)")


# ------------------------------------------------------------------ shared helpers

PITWALL_APPEND = '''
# ---- units ---------------------------------------------------------------------------

def imperial() -> bool:
    """Sidebar toggle for mph / deg F. Pages that show speeds or temperatures call this."""
    return st.sidebar.toggle("Imperial units (mph, °F)", key="imperial")


def spd(v, imp: bool):
    """km/h to mph when `imp` is true."""
    return v * 0.621371 if imp else v


def tmp(v, imp: bool):
    """deg C to deg F when `imp` is true."""
    return v * 9 / 5 + 32 if imp else v


def spd_unit(imp: bool) -> str:
    return "mph" if imp else "km/h"


def tmp_unit(imp: bool) -> str:
    return "°F" if imp else "°C"
'''

RACELIB_APPEND = '''
# ---- timing tower --------------------------------------------------------------------

FINISHED = ("Finished", "+", "Lapped")


def tower(laps: pd.DataFrame, drv: pd.DataFrame, results: pd.DataFrame, lap: int,
          ref: str | None = None) -> pd.DataFrame:
    """Timing tower at the end of `lap`: order across the line, gaps, tyres, best lap, pits.

    status: OUT = retired before this lap, PIT = pitted this lap, dash = classified finisher
    who has not completed this lap. Gaps are lap-resolution, not live."""
    d = laps.dropna(subset=["LapNumber"]).copy()
    d["LapNumber"] = d["LapNumber"].astype(int)
    upto = d[d["LapNumber"] <= lap]
    cur = d[d["LapNumber"] == lap].dropna(subset=["Time_s"]).sort_values("Time_s")
    if cur.empty:
        return cur
    best = upto.groupby("Driver")["LapTime_s"].min()
    pits = upto.groupby("Driver")["PitInTime_s"].apply(lambda s: int(s.notna().sum()))
    status = {}
    if not results.empty and {"Abbreviation", "Status"} <= set(results.columns):
        status = dict(zip(results["Abbreviation"], results["Status"].astype(str)))
    has_row = set(d.loc[d["LapNumber"] == lap, "Driver"])
    t_lead = float(cur["Time_s"].iloc[0])
    t_ref = None
    if ref is not None and (cur["Driver"] == ref).any():
        t_ref = float(cur.loc[cur["Driver"] == ref, "Time_s"].iloc[0])

    rows, prev = [], None
    for i, r in enumerate(cur.itertuples(), start=1):
        t = float(r.Time_s)
        row = {"order": i, "Driver": r.Driver,
               "status": "PIT" if pd.notna(r.PitInTime_s) else "",
               "gap to leader": round(t - t_lead, 3),
               "interval": None if prev is None else round(t - prev, 3)}
        if t_ref is not None:
            row[f"vs {ref} (s)"] = round(t - t_ref, 3)
        row.update({"last lap": pw.fmt_lap(r.LapTime_s), "best lap": pw.fmt_lap(best.get(r.Driver)),
                    "tyre": r.Compound, "tyre age": r.TyreLife, "pits": pits.get(r.Driver, 0)})
        rows.append(row)
        prev = t
    seen = {row["Driver"] for row in rows}
    for name in drv["Driver"]:
        if name in seen:
            continue
        finished = status.get(name, "").startswith(FINISHED)
        label = "no time" if name in has_row else ("-" if finished else "OUT")
        rows.append({"order": None, "Driver": name, "status": label,
                     "best lap": pw.fmt_lap(best.get(name)), "pits": pits.get(name, 0)})
    out = pd.DataFrame(rows)
    out["order"] = out["order"].astype("Int64")
    out["tyre age"] = pd.to_numeric(out["tyre age"], errors="coerce").round().astype("Int64")
    out["pits"] = out["pits"].astype("Int64")
    return out
'''

# ------------------------------------------------------------------ rewritten pages

PAGE_GAPS = '''
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import pitwall as pw
import racelib as rl

st.set_page_config(page_title="Race gaps", layout="wide")
st.title("Race gaps and positions")

p = pw.pick_session(key="gaps")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
laps = pw.laps(year, rnd, code)
drv = pw.drivers(year, rnd, code)
if laps.empty:
    st.error("No lap data for this session.")
    st.stop()
if code not in ("R", "S"):
    st.info("Positions and gaps mean most in races and sprints. For other sessions they show "
            "running order on track, which is less meaningful.")

colors = dict(zip(drv["Driver"], drv["color"]))
names = list(drv["Driver"])
shades = rl.status_ranges(laps)
if shades:
    st.caption("Shaded laps: " + ", ".join(
        f"{rl.STATUS_STYLE[c][0]} {a}-{b}" if a != b else f"{rl.STATUS_STYLE[c][0]} {a}"
        for a, b, c in shades))
else:
    st.caption("No safety car, virtual safety car or red flag laps found in this session.")


def shade(fig):
    for start, end, c in shades:
        fig.add_vrect(x0=start - 0.5, x1=end + 0.5, fillcolor=rl.STATUS_STYLE[c][1],
                      opacity=0.18, line_width=0, annotation_text=c,
                      annotation_position="top left")
    return fig


tab_pos, tab_gap, tab_tower = st.tabs(["Positions", "Gap to leader", "Timing tower"])

with tab_pos:
    chosen = st.multiselect("Drivers", names, default=names, key="pos_drivers")
    d = laps[laps["Driver"].isin(chosen) & laps["Position"].notna()].copy()
    d["lap"] = d["LapNumber"].astype(int)
    fig = px.line(d, x="lap", y="Position", color="Driver", color_discrete_map=colors)
    pits = d[d["PitInTime_s"].notna()]
    fig.add_trace(go.Scatter(x=pits["lap"], y=pits["Position"], mode="markers", name="Pit in",
                             hovertext=pits["Driver"],
                             marker=dict(symbol="x", size=9, color="#222222")))
    fig.update_yaxes(autorange="reversed", dtick=1)
    fig.update_layout(height=640, xaxis_title="Lap")
    st.plotly_chart(shade(fig))

with tab_gap:
    chosen = st.multiselect("Drivers", names, default=names[:8], key="gap_drivers")
    limit = st.slider("Hide gaps above (seconds)", 10, 300, 120)
    gt = rl.gap_table(laps)
    d = gt[gt["Driver"].isin(chosen) & (gt["gap_s"] <= limit)]
    fig = px.line(d, x="lap", y="gap_s", color="Driver", color_discrete_map=colors,
                  labels={"gap_s": "Gap to leader (s)", "lap": "Lap"})
    fig.update_layout(height=560)
    st.plotly_chart(shade(fig))
    st.caption("Gap at the end of each lap against the first car to complete that lap. "
               "Lapped cars show large gaps; use the slider to hide them.")

with tab_tower:
    results = pw.read("results", year, rnd, code)
    last_lap = int(laps["LapNumber"].max())
    c1, c2 = st.columns([3, 1])
    lap = c1.slider("Lap", 1, last_lap, min(last_lap, 10))
    ref = c2.selectbox("Compare against", ["(none)"] + names)
    ref = None if ref == "(none)" else ref
    snap = rl.tower(laps, drv, results, lap, ref)
    if snap.empty:
        st.info("No timing for this lap.")
    else:
        st.dataframe(snap, hide_index=True, height=min(800, 40 + 36 * len(snap)))
        st.caption("OUT = retired before this lap. PIT = pitted on this lap. A dash = classified "
                   "finisher who has not completed the lap. 'vs' columns: positive means that "
                   "driver crossed the line after the one you chose. Order and gaps are at the end "
                   "of the lap: one-lap resolution, not live.")
'''

PAGE_MULTI = '''
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import pitwall as pw
import racelib as rl

st.set_page_config(page_title="Multi-driver telemetry", layout="wide")
st.title("Multi-driver telemetry")

p = pw.pick_session(need_telemetry=True, key="multi")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
imp = pw.imperial()
laps = pw.laps(year, rnd, code)
drv = pw.drivers(year, rnd, code)
names = list(drv["Driver"])
colors = dict(zip(drv["Driver"], drv["color"]))

chosen = st.multiselect("Drivers (each uses their fastest lap)", names, default=names[:3],
                        max_selections=6)

traces = {}
for name in chosen:
    dl = laps[(laps["Driver"] == name) & laps["LapTime_s"].notna()]
    if dl.empty:
        st.warning(f"{name} has no timed laps.")
        continue
    row = dl.loc[dl["LapTime_s"].idxmin()]
    tr = rl.lap_trace(year, rnd, code, row)
    if tr is None:
        st.warning(f"No usable telemetry for {name}'s fastest lap.")
        continue
    traces[name] = (row, tr)
if len(traces) < 2:
    st.info("Pick at least two drivers with telemetry.")
    st.stop()

length = float(np.mean([tr["dist"][-1] for _, tr in traces.values()]))
grid = np.linspace(0, length, 800)
grids = {n: rl.on_grid(tr, length, grid) for n, (_, tr) in traces.items()}
ref = st.selectbox("Gap reference", list(grids))
has_drs = any(float(np.max(g.get("drs", [0]))) > 0 for g in grids.values())

dashes = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]
seen = {}
styles = {}
for n in grids:
    c = colors.get(n, "#636efa")
    styles[n] = dict(color=c, dash=dashes[seen.get(c, 0) % len(dashes)])
    seen[c] = seen.get(c, 0) + 1

n_rows = 5 if has_drs else 4
heights = [0.32, 0.18, 0.18, 0.16, 0.16] if has_drs else [0.36, 0.22, 0.22, 0.2]
fig = make_subplots(rows=n_rows, cols=1, shared_xaxes=True, vertical_spacing=0.025,
                    row_heights=heights)
for n, g in grids.items():
    label = f"{n} lap {int(traces[n][0]['LapNumber'])}"
    fig.add_trace(go.Scatter(x=grid, y=pw.spd(g["speed"], imp), name=label, line=styles[n]),
                  row=1, col=1)
    if n != ref:
        fig.add_trace(go.Scatter(x=grid, y=g["t"] - grids[ref]["t"], name=f"{n} vs {ref}",
                                 showlegend=False, line=styles[n]), row=2, col=1)
    fig.add_trace(go.Scatter(x=grid, y=g["throttle"], name=label, showlegend=False,
                             line=styles[n]), row=3, col=1)
    fig.add_trace(go.Scatter(x=grid, y=g["gear"], name=label, showlegend=False,
                             line=dict(**styles[n], shape="hv")), row=4, col=1)
    if has_drs:
        fig.add_trace(go.Scatter(x=grid, y=g["drs"], name=label, showlegend=False,
                                 line=dict(**styles[n], shape="hv")), row=5, col=1)
fig.add_hline(y=0, row=2, col=1, line_dash="dot", line_color="#888888")
fig.update_yaxes(title_text=pw.spd_unit(imp), row=1, col=1)
fig.update_yaxes(title_text=f"Gap to {ref} (s)", row=2, col=1)
fig.update_yaxes(title_text="Throttle %", row=3, col=1)
fig.update_yaxes(title_text="Gear", row=4, col=1)
if has_drs:
    fig.update_yaxes(title_text="DRS open", row=5, col=1)
fig.update_xaxes(title_text="Distance (m)", row=n_rows, col=1)
fig.update_layout(height=860 if has_drs else 780, hovermode="x unified",
                  legend=dict(orientation="h", y=1.05), margin=dict(l=0, r=0, t=30, b=0))
st.plotly_chart(fig)

rows = []
for n, (row, tr) in traces.items():
    g = grids[n]
    rec = {"Driver": n, "Lap": int(row["LapNumber"]), "Lap time": pw.fmt_lap(row["LapTime_s"]),
           "Top speed": f"{pw.spd(tr['speed'].max(), imp):.0f} {pw.spd_unit(imp)}",
           "Minimum speed": f"{pw.spd(tr['speed'].min(), imp):.0f} {pw.spd_unit(imp)}",
           "Full throttle": f"{100 * (tr['throttle'] >= 98).mean():.0f}%"}
    if has_drs:
        rec["DRS open"] = f"{100 * (g['drs'] > 0.5).mean():.0f}%"
    rows.append(rec)
st.dataframe(pd.DataFrame(rows), hide_index=True)
st.caption("Distance is integrated from speed and every lap is scaled to the same length, so the "
           "gap traces are indicative, not exact."
           + (" DRS is shown as open when the code is 10, 12 or 14 (my reading of FastF1's "
              "documentation; not verified against these files)." if has_drs else
              " No DRS row: this session has no open-DRS samples (DRS was removed in 2026)."))
'''

# ------------------------------------------------------------------ apply

print("Applying changes in", ROOT, "\n")

append("app/pitwall.py", "def imperial(", PITWALL_APPEND, "units helpers in pitwall.py")
append("app/racelib.py", "def tower(", RACELIB_APPEND, "timing tower in racelib.py")

patch("app/racelib.py",
      '    gear = pd.to_numeric(car["ngear"], errors="coerce").fillna(0).astype(float).to_numpy()\n',
      '    gear = pd.to_numeric(car["ngear"], errors="coerce").fillna(0).astype(float).to_numpy()\n'
      '    drs = np.isin(pd.to_numeric(car["drs"], errors="coerce").fillna(0).astype(float)\n'
      '                  .to_numpy(), (10, 12, 14)).astype(float)\n',
      "DRS in lap_trace")
patch("app/racelib.py",
      '            "brake": brake, "gear": gear}',
      '            "brake": brake, "gear": gear, "drs": drs}',
      "DRS in lap_trace result")
patch("app/racelib.py",
      'for k in ("t", "speed", "throttle", "brake", "gear")}',
      'for k in ("t", "speed", "throttle", "brake", "gear", "drs")}',
      "DRS in on_grid")

write_page("app/pages/5_Race_gaps.py", PAGE_GAPS, "Race gaps page with timing tower")
write_page("app/pages/6_Multi_driver_telemetry.py", PAGE_MULTI,
           "Multi-driver telemetry page with DRS and units")

RE = "app/pages/1_Race_explorer.py"
patch(RE, "import pitwall as pw\n", "import pitwall as pw\nimport racelib as rl\n",
      "Race explorer: import racelib")
patch(RE,
      '        st.plotly_chart(fig)\n        best = d.loc[d.groupby("Driver")["LapTime_s"].idxmin(),',
      '        for a_, b_, c_ in rl.status_ranges(laps):\n'
      '            fig.add_vrect(x0=a_ - 0.5, x1=b_ + 0.5, fillcolor=rl.STATUS_STYLE[c_][1],\n'
      '                          opacity=0.18, line_width=0, annotation_text=c_,\n'
      '                          annotation_position="top left")\n'
      '        st.plotly_chart(fig)\n        best = d.loc[d.groupby("Driver")["LapTime_s"].idxmin(),',
      "Race explorer: safety car shading on lap times")
patch(RE,
      '        a.metric("Air temp (avg)", f"{w[\'AirTemp\'].mean():.1f} °C")\n'
      '        b.metric("Track temp (avg)", f"{w[\'TrackTemp\'].mean():.1f} °C")\n'
      '        c.metric("Rain samples", f"{100 * w[\'Rainfall\'].mean():.0f}%")\n'
      '        st.line_chart(w.set_index("minutes")[["AirTemp", "TrackTemp"]])',
      '        imp = pw.imperial()\n'
      '        u = pw.tmp_unit(imp)\n'
      '        a.metric("Air temp (avg)", f"{pw.tmp(w[\'AirTemp\'].mean(), imp):.1f} {u}")\n'
      '        b.metric("Track temp (avg)", f"{pw.tmp(w[\'TrackTemp\'].mean(), imp):.1f} {u}")\n'
      '        c.metric("Rain samples", f"{100 * w[\'Rainfall\'].mean():.0f}%")\n'
      '        wt = w.set_index("minutes")[["AirTemp", "TrackTemp"]].apply(lambda s: pw.tmp(s, imp))\n'
      '        st.line_chart(wt)',
      "Race explorer: imperial temperatures")

TM = "app/pages/2_Track_map.py"
patch(TM, 'm = m.dropna(subset=["x", "y"])\n',
      'm = m.dropna(subset=["x", "y"])\nimp = pw.imperial()\nm["speed"] = pw.spd(m["speed"], imp)\n',
      "Track map: imperial speeds")
patch(TM, 'title="km/h"', "title=pw.spd_unit(imp)", "Track map: colourbar unit")
patch(TM, 'hovertemplate="%{customdata[0]:.0f} km/h<extra></extra>"',
      'hovertemplate="%{customdata[0]:.0f} " + pw.spd_unit(imp) + "<extra></extra>"',
      "Track map: hover unit")
patch(TM, 'b.metric("Top speed", f"{m[\'speed\'].max():.0f} km/h")',
      'b.metric("Top speed", f"{m[\'speed\'].max():.0f} {pw.spd_unit(imp)}")',
      "Track map: top speed unit")
patch(TM, 'c.metric("Minimum speed", f"{m[\'speed\'].min():.0f} km/h")',
      'c.metric("Minimum speed", f"{m[\'speed\'].min():.0f} {pw.spd_unit(imp)}")',
      "Track map: minimum speed unit")

DC = "app/pages/3_Driver_comparison.py"
patch(DC, "ga, gb = on_grid(a), on_grid(b)\n",
      'ga, gb = on_grid(a), on_grid(b)\nimp = pw.imperial()\n'
      'ga["speed"] = pw.spd(ga["speed"], imp)\ngb["speed"] = pw.spd(gb["speed"], imp)\n',
      "Driver comparison: imperial speeds")
patch(DC, "{gb['speed'].max():.0f} km/h\")", "{gb['speed'].max():.0f} {pw.spd_unit(imp)}\")",
      "Driver comparison: top speed unit")
patch(DC, 'title_text="km/h", row=1, col=1', "title_text=pw.spd_unit(imp), row=1, col=1",
      "Driver comparison: axis unit")

print("\nChecking every changed file still compiles:")
bad = 0
for f in ["app/pitwall.py", "app/racelib.py", *sorted(str(p.relative_to(ROOT))
                                                      for p in (ROOT / "app" / "pages").glob("*.py"))]:
    try:
        py_compile.compile(str(ROOT / f), doraise=True)
        print("  ok      ", f)
    except py_compile.PyCompileError as e:
        bad += 1
        print("  SYNTAX ERROR in", f, "->", str(e)[:300])
print("\nAll files compile." if not bad else f"\n{bad} file(s) have syntax errors; send me this output.")
print("Reload the app in your browser (or click Rerun).")

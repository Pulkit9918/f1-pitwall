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

dashes = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]
seen = {}
styles = {}
for n in grids:
    c = colors.get(n, "#636efa")
    styles[n] = dict(color=c, dash=dashes[seen.get(c, 0) % len(dashes)])
    seen[c] = seen.get(c, 0) + 1

fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.025,
                    row_heights=[0.36, 0.22, 0.22, 0.2])
for n, g in grids.items():
    label = f"{n} lap {int(traces[n][0]['LapNumber'])}"
    fig.add_trace(go.Scatter(x=grid, y=g["speed"], name=label, line=styles[n]), row=1, col=1)
    if n != ref:
        fig.add_trace(go.Scatter(x=grid, y=g["t"] - grids[ref]["t"], name=f"{n} vs {ref}",
                                 showlegend=False, line=styles[n]), row=2, col=1)
    fig.add_trace(go.Scatter(x=grid, y=g["throttle"], name=label, showlegend=False,
                             line=styles[n]), row=3, col=1)
    fig.add_trace(go.Scatter(x=grid, y=g["gear"], name=label, showlegend=False,
                             line=dict(**styles[n], shape="hv")), row=4, col=1)
fig.add_hline(y=0, row=2, col=1, line_dash="dot", line_color="#888888")
fig.update_yaxes(title_text="km/h", row=1, col=1)
fig.update_yaxes(title_text=f"Gap to {ref} (s)", row=2, col=1)
fig.update_yaxes(title_text="Throttle %", row=3, col=1)
fig.update_yaxes(title_text="Gear", row=4, col=1)
fig.update_xaxes(title_text="Distance (m)", row=4, col=1)
fig.update_layout(height=860, hovermode="x unified", legend=dict(orientation="h", y=1.05),
                  margin=dict(l=0, r=0, t=30, b=0))
st.plotly_chart(fig)

rows = []
for n, (row, tr) in traces.items():
    rows.append({"Driver": n, "Lap": int(row["LapNumber"]), "Lap time": pw.fmt_lap(row["LapTime_s"]),
                 "Top speed": f"{tr['speed'].max():.0f} km/h",
                 "Minimum speed": f"{tr['speed'].min():.0f} km/h",
                 "Full throttle": f"{100 * (tr['throttle'] >= 98).mean():.0f}%"})
st.dataframe(pd.DataFrame(rows), hide_index=True)
st.caption("Distance is integrated from speed and every lap is scaled to the same length, so the "
           "gap traces are indicative, not exact.")

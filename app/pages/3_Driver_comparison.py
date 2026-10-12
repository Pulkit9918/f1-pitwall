import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import pitwall as pw

st.set_page_config(page_title="Driver comparison", layout="wide")
st.title("Driver comparison")

p = pw.pick_session(need_telemetry=True, key="cmp")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
laps = pw.laps(year, rnd, code)
drv = pw.drivers(year, rnd, code)
names = list(drv["Driver"])
colors = dict(zip(drv["Driver"], drv["color"]))


def lap_picker(col_driver, col_lap, label, default_index):
    driver = col_driver.selectbox(f"Driver {label}", names,
                                  index=min(default_index, len(names) - 1),
                                  key=f"cmp_{label}_driver")
    dl = laps[(laps["Driver"] == driver) & laps["LapTime_s"].notna()].sort_values("LapNumber")
    if dl.empty:
        col_lap.warning("No timed laps")
        return driver, None
    times = dict(zip(dl["LapNumber"].astype(int), dl["LapTime_s"]))
    best = int(dl.loc[dl["LapTime_s"].idxmin(), "LapNumber"])
    lap_list = list(times)
    lap = col_lap.selectbox(f"Lap {label}", lap_list, index=lap_list.index(best),
                            format_func=lambda n: f"Lap {n} · {pw.fmt_lap(times[n])}",
                            key=f"cmp_{label}_lap_{driver}")
    return driver, dl[dl["LapNumber"] == lap].iloc[0]


c1, c2, c3, c4 = st.columns(4)
da, row_a = lap_picker(c1, c2, "A", 0)
db, row_b = lap_picker(c3, c4, "B", 1)
if row_a is None or row_b is None:
    st.stop()


def prepare(row):
    start, end = row["LapStartTime_s"], row["Time_s"]
    if pd.isna(start) or pd.isna(end):
        return None
    num = int(row["DriverNumber"])
    car = pw.read("telemetry_car", year, rnd, code,
                  f"driver_number = {num} AND session_time_s BETWEEN {start:.3f} AND {end:.3f}")
    if len(car) < 50:
        return None
    car = car.sort_values("session_time_s")
    t = car["session_time_s"].to_numpy(dtype=float) - float(start)
    speed = (pd.Series(pd.to_numeric(car["speed"], errors="coerce").astype(float).to_numpy())
             .interpolate().bfill().ffill().to_numpy())
    throttle = np.clip(pd.to_numeric(car["throttle"], errors="coerce").fillna(0)
                       .astype(float).to_numpy(), 0, 100)
    brake = car["brake"].fillna(False).astype(float).to_numpy()
    dist = np.cumsum(speed / 3.6 * np.diff(t, prepend=t[0]))
    dist = np.maximum.accumulate(dist) + np.arange(len(dist)) * 1e-6
    return {"t": t, "dist": dist, "speed": speed, "throttle": throttle, "brake": brake}


a, b = prepare(row_a), prepare(row_b)
if a is None or b is None:
    st.warning("Telemetry is missing for one of these laps.")
    st.stop()

length = (a["dist"][-1] + b["dist"][-1]) / 2
if length <= 0:
    st.warning("Could not work out a lap distance from the telemetry.")
    st.stop()
grid = np.linspace(0, length, 800)


def on_grid(x):
    d = x["dist"] * (length / x["dist"][-1])
    return {k: np.interp(grid, d, x[k]) for k in ("t", "speed", "throttle", "brake")}


ga, gb = on_grid(a), on_grid(b)
imp = pw.imperial()
ga["speed"] = pw.spd(ga["speed"], imp)
gb["speed"] = pw.spd(gb["speed"], imp)
delta = gb["t"] - ga["t"]

label_a = f"{da} lap {int(row_a['LapNumber'])}"
label_b = f"{db} lap {int(row_b['LapNumber'])}"
ca, cb = colors.get(da, "#636efa"), colors.get(db, "#ef553b")
style_b = dict(color=cb, dash="dot" if ca == cb else "solid")

ta, tb = float(row_a["LapTime_s"]), float(row_b["LapTime_s"])
m1, m2, m3 = st.columns(3)
m1.metric(label_a, pw.fmt_lap(ta))
m2.metric(label_b, pw.fmt_lap(tb), delta=f"{tb - ta:+.3f} s", delta_color="inverse")
m3.metric("Top speed (A / B)", f"{ga['speed'].max():.0f} / {gb['speed'].max():.0f} {pw.spd_unit(imp)}")

fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                    row_heights=[0.4, 0.2, 0.2, 0.2])
fig.add_trace(go.Scatter(x=grid, y=ga["speed"], name=label_a, line=dict(color=ca)), row=1, col=1)
fig.add_trace(go.Scatter(x=grid, y=gb["speed"], name=label_b, line=style_b), row=1, col=1)
fig.add_trace(go.Scatter(x=grid, y=delta, name=f"Gap {db} - {da} (s)", showlegend=False,
                         line=dict(color="#aaaaaa")), row=2, col=1)
fig.add_hline(y=0, row=2, col=1, line_dash="dot", line_color="#888888")
fig.add_trace(go.Scatter(x=grid, y=ga["throttle"], name=label_a, showlegend=False,
                         line=dict(color=ca)), row=3, col=1)
fig.add_trace(go.Scatter(x=grid, y=gb["throttle"], name=label_b, showlegend=False,
                         line=style_b), row=3, col=1)
fig.add_trace(go.Scatter(x=grid, y=ga["brake"], name=label_a, showlegend=False,
                         line=dict(color=ca, shape="hv")), row=4, col=1)
fig.add_trace(go.Scatter(x=grid, y=gb["brake"], name=label_b, showlegend=False,
                         line=dict(color=cb, shape="hv", dash=style_b["dash"])), row=4, col=1)
fig.update_yaxes(title_text=pw.spd_unit(imp), row=1, col=1)
fig.update_yaxes(title_text=f"Gap (s), {db} - {da}", row=2, col=1)
fig.update_yaxes(title_text="Throttle %", row=3, col=1)
fig.update_yaxes(title_text="Brake", row=4, col=1)
fig.update_xaxes(title_text="Distance (m)", row=4, col=1)
fig.update_layout(height=780, hovermode="x unified", legend=dict(orientation="h", y=1.06),
                  margin=dict(l=0, r=0, t=30, b=0))
st.plotly_chart(fig)
st.caption("Distance is integrated from speed and both laps are scaled to the same length, "
           "so the gap trace is indicative, not exact. A positive gap means B is behind A.")

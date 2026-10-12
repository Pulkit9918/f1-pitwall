import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import pitwall as pw

st.set_page_config(page_title="Track map", layout="wide")
st.title("Track map")

p = pw.pick_session(need_telemetry=True, key="map")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
laps = pw.laps(year, rnd, code)
drv = pw.drivers(year, rnd, code)

c1, c2, c3 = st.columns(3)
driver = c1.selectbox("Driver", list(drv["Driver"]))
dl = laps[(laps["Driver"] == driver) & laps["LapTime_s"].notna()].sort_values("LapNumber")
if dl.empty:
    st.warning("This driver has no timed laps in this session.")
    st.stop()
times = dict(zip(dl["LapNumber"].astype(int), dl["LapTime_s"]))
best = int(dl.loc[dl["LapTime_s"].idxmin(), "LapNumber"])
lap_list = list(times)
lap = c2.selectbox("Lap", lap_list, index=lap_list.index(best),
                   format_func=lambda n: f"Lap {n} · {pw.fmt_lap(times[n])}")
mode = c3.radio("Colour by", ["Speed", "Sector", "Throttle / brake"], horizontal=True)

row = dl[dl["LapNumber"] == lap].iloc[0]
start, end = row["LapStartTime_s"], row["Time_s"]
if pd.isna(start) or pd.isna(end):
    st.warning("This lap has no start or end timestamp.")
    st.stop()

num = int(row["DriverNumber"])
window = f"driver_number = {num} AND session_time_s BETWEEN {start - 1:.3f} AND {end + 1:.3f}"
pos = pw.read("telemetry_pos", year, rnd, code, window)
car = pw.read("telemetry_car", year, rnd, code, window)
if pos.empty or car.empty:
    st.warning("No telemetry for this lap.")
    st.stop()

pos = pos.assign(session_time_s=pos["session_time_s"].astype(float)).sort_values("session_time_s")
car = car.assign(session_time_s=car["session_time_s"].astype(float)).sort_values("session_time_s")
m = pd.merge_asof(pos[["session_time_s", "x", "y"]],
                  car[["session_time_s", "speed", "throttle", "brake"]],
                  on="session_time_s", direction="nearest", tolerance=0.3)
m = m[(m["session_time_s"] >= start) & (m["session_time_s"] <= end)].copy()
for col in ("x", "y", "speed", "throttle"):
    m[col] = pd.to_numeric(m[col], errors="coerce").astype(float)
m["brake"] = m["brake"].fillna(False).astype(bool)
m = m.dropna(subset=["x", "y"])
imp = pw.imperial()
m["speed"] = pw.spd(m["speed"], imp)

expected = (end - start) / 0.24
if len(m) < 0.8 * expected:
    st.warning(f"Position data for this lap looks incomplete ({len(m)} of about {expected:.0f} samples).")
if len(m) < 20:
    st.stop()


def rotate(a, deg):
    t = np.deg2rad(deg)
    return a @ np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])


rot = p.get("rotation")
has_rot = rot is not None and pd.notna(rot)
rotate_map = has_rot and st.checkbox("Rotate to the official orientation", value=True)

xy = m[["x", "y"]].to_numpy()
if rotate_map:
    xy = rotate(xy, float(rot))
m["px"], m["py"] = xy[:, 0], xy[:, 1]

if mode == "Sector":
    s1, s2 = row.get("Sector1SessionTime_s"), row.get("Sector2SessionTime_s")
    if pd.isna(s1) or pd.isna(s2):
        st.warning("No sector timestamps for this lap; showing speed instead.")
        mode = "Speed"
    else:
        m["cat"] = np.where(m["session_time_s"] <= s1, "Sector 1",
                            np.where(m["session_time_s"] <= s2, "Sector 2", "Sector 3"))
        palette = {"Sector 1": "#e8002d", "Sector 2": "#1e90ff", "Sector 3": "#ffd12e"}
if mode == "Throttle / brake":
    m["cat"] = np.select(
        [m["brake"].to_numpy(dtype=bool), (m["throttle"] >= 98).to_numpy(),
         (m["throttle"] <= 5).to_numpy()],
        ["Braking", "Full throttle", "Coasting"], default="Partial throttle")
    palette = {"Braking": "#e8002d", "Full throttle": "#39b54a",
               "Coasting": "#888888", "Partial throttle": "#ffd12e"}

fig = go.Figure()
fig.add_trace(go.Scatter(x=pd.concat([m["px"], m["px"].iloc[:1]]),
                         y=pd.concat([m["py"], m["py"].iloc[:1]]), mode="lines",
                         line=dict(color="#666666", width=8), hoverinfo="skip", showlegend=False))
if mode == "Speed":
    fig.add_trace(go.Scatter(
        x=m["px"], y=m["py"], mode="markers", showlegend=False,
        marker=dict(color=m["speed"], colorscale="Turbo", size=6, colorbar=dict(title=pw.spd_unit(imp), len=0.75, y=0.4)),
        customdata=m[["speed"]], hovertemplate="%{customdata[0]:.0f} " + pw.spd_unit(imp) + "<extra></extra>"))
else:
    for name, color in palette.items():
        sub = m[m["cat"] == name]
        fig.add_trace(go.Scatter(x=sub["px"], y=sub["py"], mode="markers", name=name,
                                 marker=dict(color=color, size=6)))

corners = pw.read("circuit_corners", year, rnd, code)
if not corners.empty and {"X", "Y", "Number"} <= set(corners.columns):
    cxy = corners[["X", "Y"]].to_numpy(dtype=float)
    ang = corners["Angle"].to_numpy(dtype=float) if "Angle" in corners.columns else np.zeros(len(corners))
    lab = cxy + np.column_stack([np.cos(np.deg2rad(ang)) * 500, np.sin(np.deg2rad(ang)) * 500])
    if rotate_map:
        lab = rotate(lab, float(rot))
    letters = corners["Letter"] if "Letter" in corners.columns else [""] * len(corners)
    texts = [f"{int(n)}{l if isinstance(l, str) else ''}" for n, l in zip(corners["Number"], letters)]
    fig.add_trace(go.Scatter(x=lab[:, 0], y=lab[:, 1], mode="text", text=texts,
                             textfont=dict(size=11), hoverinfo="skip", showlegend=False))
else:
    st.caption("No corner data for this circuit.")

fig.update_layout(height=680, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h"))
fig.update_xaxes(visible=False)
fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)
st.plotly_chart(fig)

a, b, c = st.columns(3)
a.metric("Lap time", pw.fmt_lap(times[lap]))
b.metric("Top speed", f"{m['speed'].max():.0f} {pw.spd_unit(imp)}")
c.metric("Minimum speed", f"{m['speed'].min():.0f} {pw.spd_unit(imp)}")

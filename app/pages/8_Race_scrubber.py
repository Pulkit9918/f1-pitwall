import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import engine as eg
import pitwall as pw

st.set_page_config(page_title="Race scrubber", layout="wide")
st.title("Race scrubber")

p = pw.pick_session(need_telemetry=True, key="scrub")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
state = eg.build(year, rnd, code)
if state is None:
    st.error("No usable position data for this session, so the race state cannot be built.")
    st.stop()
drv = pw.drivers(year, rnd, code)
colors = dict(zip(drv["Driver"], drv["color"]))
numbers = dict(zip(drv["Driver"], drv["number"]))
names = list(state["drivers"])
imp = pw.imperial()

duration = int(state["end"] - state["start"])
last_lap = max(1, int(np.ceil(state["lead"][-1])))
key = f"scrub_{year}_{rnd}_{code}"
st.session_state.setdefault(key, min(60, duration))


def bump(delta: int) -> None:
    st.session_state[key] = int(min(duration, max(0, st.session_state[key] + delta)))


def to_lap() -> None:
    n = int(st.session_state[f"{key}_lap"])
    idx = int(np.searchsorted(state["lead"], n - 1))
    t = state["grid"][min(idx, len(state["grid"]) - 1)] - state["start"]
    st.session_state[key] = int(min(duration, max(0, t)))


b1, b2, b3, b4, b5, b6 = st.columns([1, 1, 1, 1, 1, 2])
b1.button("-60 s", on_click=bump, args=(-60,))
b2.button("-10 s", on_click=bump, args=(-10,))
b3.button("+10 s", on_click=bump, args=(10,))
b4.button("+60 s", on_click=bump, args=(60,))
b5.number_input("Lap", 1, last_lap, 1, key=f"{key}_lap", label_visibility="collapsed")
b6.button("Go to lap", on_click=to_lap)

t_rel = st.slider("Seconds since the start", 0, duration, key=key)
follow = st.multiselect("Follow drivers (highlighted on the map, live telemetry below)",
                        names, max_selections=3, key=f"{key}_follow")
T = state["start"] + t_rel
snap = eg.snapshot(state, T)
m, s = divmod(int(t_rel), 60)
lead_lap = int(min(np.floor(snap["P"].iloc[0]) + 1, last_lap))
st.caption(f"Race time {m}:{s:02d} | leader on lap {lead_lap} of {last_lap}")

rot = p.get("rotation")
has_rot = rot is not None and pd.notna(rot)
rotate_map = has_rot and st.checkbox("Rotate to the official orientation", value=True)


def tr(a):
    return eg.rotate(a, float(rot)) if rotate_map else a


outline = tr(state["ref_xy"])
cars = tr(snap[["x", "y"]].to_numpy())
snap["px"], snap["py"] = cars[:, 0], cars[:, 1]

fig = go.Figure()
fig.add_trace(go.Scatter(x=outline[:, 0], y=outline[:, 1], mode="lines",
                         line=dict(color="#777777", width=9), hoverinfo="skip", showlegend=False))


def add_cars(sub, symbol, size, opacity, ring, text_size, grey=False):
    if sub.empty:
        return
    fig.add_trace(go.Scatter(
        x=sub["px"], y=sub["py"], mode="markers+text", text=sub["driver"], showlegend=False,
        textposition="top center", textfont=dict(size=text_size), opacity=opacity,
        marker=dict(size=size, symbol=symbol, line=dict(width=ring, color="#ffffff"),
                    color=["#999999" if grey else colors.get(d, "#888888") for d in sub["driver"]]),
        hovertext=[f"P{r.pos} {r.driver}" for r in sub.itertuples()], hoverinfo="text"))


followed = snap["driver"].isin(follow)
add_cars(snap[(snap["status"] != "OUT") & ~followed], "circle", 12, 0.65 if follow else 1.0, 1, 10)
add_cars(snap[(snap["status"] == "OUT") & ~followed], "x", 12, 0.65 if follow else 1.0, 1, 10, True)
add_cars(snap[followed], "circle", 20, 1.0, 3, 14)
fig.update_layout(height=640, margin=dict(l=0, r=0, t=10, b=0), uirevision="map")
fig.update_xaxes(visible=False)
fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)

tbl = snap.copy()
if code in ("R", "S"):
    tbl["grid change"] = ["" if (pd.isna(g) or g <= 0) else ("=" if g == q else f"{int(g - q):+d}")
                          for g, q in zip(tbl["grid"], tbl["pos"])]
tbl = tbl.rename(columns={"tyre_age": "age", "last_lap": "last lap", "best_lap": "best lap"})
tbl["gap"] = [g + " ~" if (a and g) else g for g, a in zip(tbl["gap"], tbl["approx"])]
cols = (["pos", "driver"] + (["grid change"] if "grid change" in tbl else [])
        + ["gap", "interval", "tyre", "age", "last lap", "best lap", "pits", "status"])
show = tbl[cols]
int_s = snap["int_s"].to_numpy()
fl = snap["fl"].to_numpy()


def paint(col):
    if col.name == "interval":
        return ["background-color: #ffd166; color: #111111" if (pd.notna(x) and x < 1.0) else ""
                for x in int_s]
    if col.name == "best lap":
        return ["color: #b048ff; font-weight: 700" if f else "" for f in fl]
    if col.name == "driver":
        return ["font-weight: 700; text-decoration: underline" if d in follow else ""
                for d in show["driver"]]
    return [""] * len(col)


c_map, c_tab = st.columns([3, 2])
c_map.plotly_chart(fig)
c_tab.dataframe(show.style.apply(paint, axis=0), hide_index=True, height=640)


@st.cache_data(show_spinner=False)
def car_arrays(year: int, rnd: int, code: str, num: int):
    df = pw.read("telemetry_car", year, rnd, code, f"driver_number = {num}")
    if df.empty:
        return None
    df = df.sort_values("session_time_s")
    out = {k: pd.to_numeric(df[k], errors="coerce").to_numpy(float)
           for k in ("session_time_s", "speed", "throttle", "ngear", "drs")}
    out["brake"] = df["brake"].fillna(False).to_numpy(bool)
    return out


def car_at(arr, t_now):
    t = arr["session_time_s"]
    i = int(np.clip(np.searchsorted(t, t_now), 1, len(t) - 1))
    if abs(t[i - 1] - t_now) < abs(t[i] - t_now):
        i -= 1
    if abs(t[i] - t_now) > 2.0:
        return None
    return {k: arr[k][i] for k in ("speed", "throttle", "ngear", "drs", "brake")}


if follow:
    st.subheader("Followed drivers")
    for col, name in zip(st.columns(len(follow)), follow):
        row = snap[snap["driver"] == name].iloc[0]
        lap_now = int(min(np.floor(row["P"]) + 1, state["drivers"][name]["max_lap"]))
        arr = car_arrays(year, rnd, code, int(numbers[name]))
        v = car_at(arr, T) if arr is not None else None
        with col:
            st.markdown(f"**{name}** | P{int(row['pos'])} | lap {lap_now} | {row['status'] or 'on track'}")
            if v is None:
                st.caption("No telemetry for this moment.")
                continue
            c1, c2, c3 = st.columns(3)
            c1.metric("Speed", f"{pw.spd(v['speed'], imp):.0f} {pw.spd_unit(imp)}")
            c2.metric("Gear", "-" if np.isnan(v["ngear"]) else f"{int(v['ngear'])}")
            c3.metric("Throttle", f"{min(100.0, max(0.0, v['throttle'])):.0f}%")
            c4, c5 = st.columns(2)
            c4.metric("Brake", "ON" if v["brake"] else "off")
            drs = "n/a" if year >= 2026 else ("OPEN" if v["drs"] in (10, 12, 14) else "closed")
            c5.metric("DRS", drs)

with st.expander("Legend"):
    st.markdown(
        "- **Dots:** team colour, with the driver code. A grey x is a retired car.\n"
        "- **Followed drivers** get a large ringed dot and a live telemetry panel.\n"
        "- **~ after a gap:** GPS matching looked unreliable on that car's current lap, so its "
        "progress is estimated from the lap timing.\n"
        "- **PIT / OUT / FIN:** in the pit lane / retired / finished.\n"
        "- **Yellow interval:** under one second to the car ahead.\n"
        "- **Purple best lap:** the fastest lap so far in the session.\n"
        "- **Grid change (races and sprints):** places gained (+) or lost (-) since the grid.\n"
        "- **DRS:** open when the code is 10, 12 or 14 (my reading of FastF1's documentation; "
        "not verified against these files). DRS no longer exists in 2026.")
st.caption(
    "Positions come from GPS; the order and gaps come from each car's progress around the lap, "
    "anchored to the official timing at the line. Tested against the official order at the two "
    "sector timing lines on four races: exact 89-99.8% of the time, within one place 98-100%. "
    "Not tested: lap 1 and the start, and races with broken position data. Gaps are computed from "
    "when the car ahead was at the same point on track.")

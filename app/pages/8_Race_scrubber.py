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
imp = pw.imperial()

duration = int(state["end"] - state["start"])
last_lap = max(1, int(np.ceil(state["lead"][-1])))
key = f"scrub_{year}_{rnd}_{code}"
st.session_state.setdefault(key, min(60, duration))
L_m = state["L"] / 10.0


def bump(delta: int) -> None:
    st.session_state[key] = int(min(duration, max(0, st.session_state[key] + delta)))


def to_lap() -> None:
    n = int(st.session_state[f"{key}_lap"])
    idx = int(np.searchsorted(state["lead"], n - 1))
    t = state["grid"][min(idx, len(state["grid"]) - 1)] - state["start"]
    st.session_state[key] = int(min(duration, max(0, t)))


timeline_box = st.container()

b1, b2, b3, b4, b5, b6 = st.columns([1, 1, 1, 1, 1, 2])
b1.button("-60 s", on_click=bump, args=(-60,))
b2.button("-10 s", on_click=bump, args=(-10,))
b3.button("+10 s", on_click=bump, args=(10,))
b4.button("+60 s", on_click=bump, args=(60,))
b5.number_input("Lap", 1, last_lap, 1, key=f"{key}_lap", label_visibility="collapsed")
b6.button("Go to lap", on_click=to_lap)

t_rel = st.slider("Seconds since the start", 0, duration, key=key)
follow = st.multiselect("Follow drivers (highlighted on the map, live panel below)",
                        names, max_selections=3, key=f"{key}_follow")
T = state["start"] + t_rel
snap = eg.snapshot(state, T)
m, s = divmod(int(t_rel), 60)
lead_lap = int(min(np.floor(snap["P"].iloc[0]) + 1, last_lap))
st.caption(f"Race time {m}:{s:02d} | leader on lap {lead_lap} of {last_lap}")

# ---- flag timeline (lap resolution), filled in above the controls ------------------------
FLAG_STYLE = {"YEL": ("Yellow", "#ffd60a"), "VSC": ("Virtual safety car", "#ff9f1c"),
              "SC": ("Safety car", "#e76f51"), "RED": ("Red flag", "#d00000")}
flags = rl.flag_laps(laps)
with timeline_box:
    tl = go.Figure()
    clear = [n for n in range(1, last_lap + 1) if n not in flags]
    if clear:
        tl.add_trace(go.Bar(x=[n - 0.5 for n in clear], y=[1] * len(clear), width=1, name="Green",
                            marker=dict(color="#2e7d4f", line=dict(width=0)), opacity=0.55,
                            hoverinfo="skip"))
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

# ---- weather strip at this moment -------------------------------------------------------
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
        + ["gap", "interval", "tyres", "age", "last lap", "S1", "S2", "S3", "best lap", "pits",
           "status"])
show = tbl[cols]
int_s = snap["int_s"].to_numpy()
fl = snap["fl"].to_numpy()
SEC_STYLE = {"purple": "background-color: #7b2cbf; color: #ffffff",
             "green": "background-color: #2d6a4f; color: #ffffff",
             "yellow": "background-color: #ffd166; color: #111111"}


def paint(col):
    if col.name == "interval":
        return ["background-color: #ffd166; color: #111111" if (pd.notna(x) and x < 1.0) else ""
                for x in int_s]
    if col.name == "best lap":
        return ["color: #b048ff; font-weight: 700" if f else "" for f in fl]
    if col.name == "driver":
        return ["font-weight: 700; text-decoration: underline" if d in follow else ""
                for d in show["driver"]]
    if col.name in ("S1", "S2", "S3"):
        return [SEC_STYLE.get(c, "") for c in snap[f"c{col.name[1]}"]]
    return [""] * len(col)


c_map, c_tab = st.columns([5, 6])
c_map.plotly_chart(fig)
c_tab.dataframe(show.style.apply(paint, axis=0), hide_index=True, height=640)


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
            st.markdown(f"**{name}** | P{int(row['pos'])} | lap {lap_now} | {row['status'] or 'on track'}")
            st.caption(neighbour_text("Ahead", None if ahead is None else ahead["driver"],
                                      row["int_s"], 99.0 if ahead is None else ahead["P"] - row["P"]))
            st.caption(neighbour_text("Behind", None if behind is None else behind["driver"],
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
            st.progress(1.0 if v["brake"] else 0.0, text="Brake " + ("ON" if v["brake"] else "off"))
            rpm = 0.0 if np.isnan(v["rpm"]) else float(v["rpm"])
            st.progress(min(1.0, rpm / arr["rpm_max"]), text=f"RPM {rpm:,.0f}")

# ---- race control feed up to the current lap ---------------------------------------------
rc = pw.read("race_control", year, rnd, code)
st.subheader(f"Race control: latest messages up to lap {lead_lap}")
if rc.empty or "Lap" not in rc.columns:
    st.caption("No race control messages with lap numbers for this session.")
else:
    sub = rc[pd.to_numeric(rc["Lap"], errors="coerce") <= lead_lap].tail(8).iloc[::-1]
    rcols = [c for c in ("Lap", "Category", "Flag", "Message") if c in sub.columns]
    if sub.empty:
        st.caption("No messages yet.")
    else:
        st.dataframe(sub[rcols], hide_index=True, height=300)

with st.expander("Legend"):
    st.markdown(
        "- **Timeline above the slider:** green = normal running; yellow, virtual safety car, "
        "safety car and red flag stretches at lap resolution; the purple line is the leader now.\n"
        "- **Dots:** team colour, with the driver code. A grey x is a retired car.\n"
        "- **Followed drivers** get a large ringed dot and a panel with gaps ahead and behind "
        "(seconds, and metres along the track), speed, gear, DRS, throttle, brake and RPM.\n"
        "- **~ after a gap:** GPS matching looked unreliable on that car's current lap, so its "
        "progress is estimated from the lap timing.\n"
        "- **PIT / OUT / FIN:** in the pit lane / retired / finished.\n"
        "- **Tyres:** compounds used so far, oldest first (S soft, M medium, H hard, I intermediate, "
        "W wet); age is laps on the current set.\n"
        "- **S1 / S2 / S3:** the freshest completed sector time. Purple = fastest of anyone so far, "
        "green = the driver's own best, yellow = slower.\n"
        "- **Yellow interval:** under one second to the car ahead. **Purple best lap:** fastest lap "
        "so far. **Grid change (races and sprints):** places gained (+) or lost (-).\n"
        "- **DRS:** open when the code is 10, 12 or 14 (my reading of FastF1's documentation, "
        "not verified against these files). DRS no longer exists in 2026.\n"
        "- **Wind** is shown in km/h or mph, converted from the feed's m/s (my reading of the "
        "documentation).")
st.caption(
    "Positions come from GPS; the order and gaps come from each car's progress around the lap, "
    "anchored to the official timing at the line. Tested against the official order at the two "
    "sector timing lines on four races: exact 89-99.8% of the time, within one place 98-100%. "
    "Not tested: lap 1 and the start, and races with broken position data. Flags are at lap "
    "resolution; exact timing needs the track-status data that newer ingests include.")

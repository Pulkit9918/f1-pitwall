import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import pitwall as pw
import racelib as rl

st.set_page_config(page_title="Race explorer", layout="wide")
st.title("Race explorer")

p = pw.pick_session(key="race")
year, rnd, code = int(p["year"]), int(p["round"]), p["session"]
parts = [p["event"], p["location"], pw.SESSION_NAMES.get(code, code), str(year)]
st.caption(" · ".join(x for x in parts if x))

laps = pw.laps(year, rnd, code)
drv = pw.drivers(year, rnd, code)
if laps.empty:
    st.error("No lap data for this session.")
    st.stop()
colors = dict(zip(drv["Driver"], drv["color"]))

tab_res, tab_laps, tab_tyres, tab_weather, tab_rc = st.tabs(
    ["Results", "Lap times", "Tyre strategy", "Weather", "Race control"])

with tab_res:
    res = pw.read("results", year, rnd, code)
    cols = [c for c in ("Position", "Abbreviation", "FullName", "TeamName", "GridPosition",
                        "Status", "Points") if c in res.columns]
    st.dataframe(res[cols] if cols else res, hide_index=True)

with tab_laps:
    chosen = st.multiselect("Drivers", list(drv["Driver"]), default=list(drv["Driver"][:5]))
    clean = st.checkbox("Hide in/out laps and laps slower than 112% of the fastest", value=True)
    d = laps[laps["Driver"].isin(chosen) & laps["LapTime_s"].notna()].copy()
    if clean and not d.empty:
        d = d[d["PitInTime_s"].isna() & d["PitOutTime_s"].isna()]
        d = d[d["LapTime_s"] <= d["LapTime_s"].min() * 1.12]
    if d.empty:
        st.info("No laps to show.")
    else:
        d["lap_time"] = d["LapTime_s"].map(pw.fmt_lap)
        fig = px.line(d, x="LapNumber", y="LapTime_s", color="Driver", markers=True,
                      color_discrete_map=colors,
                      hover_data={"lap_time": True, "LapTime_s": False},
                      labels={"LapTime_s": "Lap time (s)", "LapNumber": "Lap"})
        for a_, b_, c_ in rl.status_ranges(laps):
            fig.add_vrect(x0=a_ - 0.5, x1=b_ + 0.5, fillcolor=rl.STATUS_STYLE[c_][1],
                          opacity=0.18, line_width=0, annotation_text=c_,
                          annotation_position="top left")
        st.plotly_chart(fig)
        best = d.loc[d.groupby("Driver")["LapTime_s"].idxmin(),
                     ["Driver", "LapNumber", "lap_time", "Compound"]]
        st.dataframe(best.sort_values("lap_time"), hide_index=True)

with tab_tyres:
    stints = (laps.dropna(subset=["Stint"])
              .groupby(["Driver", "Stint", "Compound"], as_index=False, dropna=False)
              .agg(start=("LapNumber", "min"), end=("LapNumber", "max")))
    stints["laps"] = stints["end"] - stints["start"] + 1
    stints = stints.sort_values(["Driver", "start"])
    order = list(drv["Driver"])
    comp = stints["Compound"].fillna("UNKNOWN")
    fig = go.Figure()
    for name in comp.unique():
        sub = stints[comp == name]
        fig.add_trace(go.Bar(
            y=sub["Driver"], x=sub["laps"], base=sub["start"] - 1, orientation="h", name=name,
            marker_color=pw.COMPOUND_COLORS.get(name, "#888888"),
            marker_line_color="#555555", marker_line_width=1,
            customdata=sub[["Stint", "start", "end"]],
            hovertemplate=("%{y}: stint %{customdata[0]:.0f}, laps "
                           "%{customdata[1]:.0f}-%{customdata[2]:.0f}<extra>" + name + "</extra>")))
    fig.update_layout(barmode="overlay", height=max(300, 28 * len(order) + 120),
                      xaxis_title="Lap",
                      yaxis=dict(categoryorder="array", categoryarray=order, autorange="reversed"))
    st.plotly_chart(fig)

    stints["next"] = stints.groupby("Driver")["Compound"].shift(-1)
    stops = stints.dropna(subset=["next"])[["Driver", "end", "Compound", "next"]]
    stops = stops.rename(columns={"end": "pit lap", "Compound": "from", "next": "to"})
    st.subheader("Tyre changes")
    st.dataframe(stops, hide_index=True)

with tab_weather:
    w = pw.read("weather", year, rnd, code)
    if w.empty:
        st.info("No weather data.")
    else:
        w = w.assign(minutes=w["Time_s"] / 60)
        a, b, c = st.columns(3)
        imp = pw.imperial()
        u = pw.tmp_unit(imp)
        a.metric("Air temp (avg)", f"{pw.tmp(w['AirTemp'].mean(), imp):.1f} {u}")
        b.metric("Track temp (avg)", f"{pw.tmp(w['TrackTemp'].mean(), imp):.1f} {u}")
        c.metric("Rain samples", f"{100 * w['Rainfall'].mean():.0f}%")
        wt = w.set_index("minutes")[["AirTemp", "TrackTemp"]].apply(lambda s: pw.tmp(s, imp))
        st.line_chart(wt)

with tab_rc:
    rc = pw.read("race_control", year, rnd, code)
    cols = [c for c in ("Time", "Lap", "Category", "Flag", "Message") if c in rc.columns]
    st.dataframe(rc[cols] if cols else rc, hide_index=True, height=450)

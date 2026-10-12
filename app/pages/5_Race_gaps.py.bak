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


tab_pos, tab_gap, tab_tower = st.tabs(["Positions", "Gap to leader", "Lap snapshot"])

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
    last_lap = int(laps["LapNumber"].max())
    lap = st.slider("Lap", 1, last_lap, min(last_lap, 10))
    snap = rl.snapshot(laps, lap)
    if snap.empty:
        st.info("No timing for this lap.")
    else:
        st.dataframe(snap, hide_index=True, height=min(750, 40 + 36 * len(snap)))
        st.caption("Order in which cars finished this lap. Resolution is one lap, not live.")

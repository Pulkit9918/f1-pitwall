from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Season history", layout="wide")
st.title("Season history")

LAKE = Path(__file__).resolve().parents[2] / "data" / "lake"
HIST = LAKE / "history"
if not (HIST / "results.parquet").exists() and (LAKE / "history_test" / "results.parquet").exists():
    HIST = LAKE / "history_test"
    st.info("Showing the test pull (only the seasons you pulled). "
            "Run the full `python history.py` for everything.")


@st.cache_data(show_spinner=False)
def load(name: str, base: str) -> pd.DataFrame:
    path = Path(base) / f"{name}.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


res = load("results", str(HIST))
if res.empty:
    st.warning("No history data yet. Run `python history.py` first.")
    st.stop()
dstand = load("driver_standings", str(HIST))
cstand = load("constructor_standings", str(HIST))
drivers, circuits = load("drivers", str(HIST)), load("circuits", str(HIST))
latest = int(res["season"].max())
st.caption(f"{int(res['season'].min())}-{latest} · {len(res):,} results. Points systems changed "
           f"over the years, so totals are not comparable across eras. Titles exclude {latest} "
           "until that season is complete.")

tab_season, tab_driver, tab_team, tab_circuit = st.tabs(["Season", "Driver", "Team", "Circuit"])

with tab_season:
    season = st.selectbox("Season", sorted(res["season"].unique(), reverse=True))
    ds = dstand[dstand["season"] == season].sort_values("position")
    cs = cstand[cstand["season"] == season].sort_values("position") if not cstand.empty else cstand
    a, b = st.columns(2)
    a.subheader("Drivers' standings")
    a.dataframe(ds[["position", "driver", "constructor", "points", "wins"]], hide_index=True)
    b.subheader("Constructors' standings")
    if cs.empty:
        b.info("No constructors' championship before 1958.")
    else:
        b.dataframe(cs[["position", "constructor", "points", "wins"]], hide_index=True)

    st.subheader("Race winners")
    w = res[(res["season"] == season) & (res["position"] == 1)].sort_values("round")
    st.dataframe(w[["round", "race_name", "date", "driver", "constructor", "grid"]],
                 hide_index=True)

    st.subheader("Championship progression (top 6)")
    prog = res[res["season"] == season].sort_values("round").copy()
    prog["cumulative points"] = prog.groupby("driver")["points"].cumsum()
    prog = prog[prog["driver"].isin(list(ds["driver"].head(6)))]
    st.plotly_chart(px.line(prog, x="round", y="cumulative points", color="driver",
                            markers=True, hover_data=["race_name"]))
    st.caption("Race points only: sprint points are not included.")

with tab_driver:
    wins = res[res["position"] == 1].groupby("driver_id").size()
    drv = drivers.assign(name=drivers["given_name"] + " " + drivers["family_name"])
    drv = drv[drv["driver_id"].isin(res["driver_id"].unique())].copy()
    drv["wins"] = drv["driver_id"].map(wins).fillna(0)
    drv = drv.sort_values("wins", ascending=False)
    labels = dict(zip(drv["driver_id"], drv["name"]))
    pick = st.selectbox("Driver (most wins first)", list(labels), format_func=labels.get)
    r = res[res["driver_id"] == pick]
    ds_all = dstand[dstand["driver_id"] == pick]
    titles = int(((ds_all["position"] == 1) & (ds_all["season"] < latest)).sum())
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Seasons", r["season"].nunique())
    m2.metric("Starts", len(r))
    m3.metric("Wins", int((r["position"] == 1).sum()))
    m4.metric("Podiums", int((r["position"] <= 3).sum()))
    m5.metric("Titles", titles)
    per = r.groupby("season").agg(
        team=("constructor", lambda s: " / ".join(sorted(set(s)))),
        races=("round", "count"),
        wins=("position", lambda s: int((s == 1).sum())),
        podiums=("position", lambda s: int((s <= 3).sum())),
        points=("points", "sum")).reset_index()
    per = per.merge(ds_all[["season", "position"]].rename(columns={"position": "final pos"}),
                    on="season", how="left")
    st.dataframe(per.sort_values("season", ascending=False), hide_index=True)

with tab_team:
    team_wins = res[res["position"] == 1].groupby("constructor_id").size()
    teams = res.drop_duplicates("constructor_id")[["constructor_id", "constructor"]].copy()
    teams["wins"] = teams["constructor_id"].map(team_wins).fillna(0)
    teams = teams.sort_values("wins", ascending=False)
    tl = dict(zip(teams["constructor_id"], teams["constructor"]))
    tpick = st.selectbox("Team (most wins first)", list(tl), format_func=tl.get)
    tr = res[res["constructor_id"] == tpick]
    cs_all = cstand[cstand["constructor_id"] == tpick] if not cstand.empty else cstand
    ttitles = 0 if cs_all.empty else int(
        ((cs_all["position"] == 1) & (cs_all["season"] < latest)).sum())
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Seasons", tr["season"].nunique())
    t2.metric("Race wins", int((tr["position"] == 1).sum()))
    t3.metric("Podium finishes", int((tr["position"] <= 3).sum()))
    t4.metric("Constructors' titles", ttitles)
    tper = tr.groupby("season").agg(
        wins=("position", lambda s: int((s == 1).sum())),
        podiums=("position", lambda s: int((s <= 3).sum())),
        drivers=("driver", lambda s: ", ".join(sorted(set(s))))).reset_index()
    if not cs_all.empty:
        tper = tper.merge(cs_all[["season", "position", "points"]]
                          .rename(columns={"position": "final pos"}), on="season", how="left")
    st.dataframe(tper.sort_values("season", ascending=False), hide_index=True)

with tab_circuit:
    held = res.drop_duplicates(["season", "round"]).groupby("circuit_id").size()
    circ = circuits.assign(races=circuits["circuit_id"].map(held)).dropna(subset=["races"])
    circ = circ.sort_values("races", ascending=False)
    cl = {x.circuit_id: f"{x.circuit_name} ({x.country}) · {int(x.races)} races"
          for x in circ.itertuples()}
    cpick = st.selectbox("Circuit (most races first)", list(cl), format_func=cl.get)
    cw = res[(res["circuit_id"] == cpick) & (res["position"] == 1)]
    st.subheader("Most wins here")
    st.dataframe(cw.groupby("driver").size().sort_values(ascending=False).head(10)
                 .rename("wins").reset_index(), hide_index=True)
    st.subheader("Every winner")
    st.dataframe(cw.sort_values(["season", "round"], ascending=False)
                 [["season", "race_name", "driver", "constructor", "grid"]], hide_index=True)

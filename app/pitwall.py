"""Shared data access for the F1 Pitwall app: reads the local Parquet lake with DuckDB."""

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import streamlit as st

LAKE = Path(__file__).resolve().parents[1] / "data" / "lake"
MANIFEST = LAKE / "_manifest" / "sessions.jsonl"

SESSION_NAMES = {
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
    "SQ": "Sprint Qualifying", "SS": "Sprint Shootout", "S": "Sprint",
    "Q": "Qualifying", "R": "Race",
}
ORDER = {"FP1": 1, "FP2": 2, "FP3": 3, "SQ": 4, "SS": 4, "S": 5, "Q": 6, "R": 7}
COMPOUND_COLORS = {
    "SOFT": "#e8002d", "MEDIUM": "#ffd12e", "HARD": "#f0f0f0",
    "INTERMEDIATE": "#39b54a", "WET": "#0067ff", "UNKNOWN": "#888888",
}
FALLBACK = ["#636efa", "#ef553b", "#00cc96", "#ab63fa", "#ffa15a", "#19d3f3", "#ff6692",
            "#b6e880", "#ff97ff", "#fecb52"]


def fmt_lap(seconds) -> str:
    if seconds is None or pd.isna(seconds):
        return ""
    m, s = divmod(float(seconds), 60)
    return f"{int(m)}:{s:06.3f}"


@st.cache_data(ttl=60)
def sessions() -> pd.DataFrame:
    """One row per ingested session (the latest attempt wins)."""
    if not MANIFEST.exists():
        return pd.DataFrame()
    latest = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("round") is None:
            continue
        latest[(r["year"], int(r["round"]), r["session"])] = r
    rows = []
    for (year, rnd, code), r in latest.items():
        if r["status"] not in ("ok", "partial"):
            continue
        rows.append({
            "year": year, "round": rnd, "session": code, "event": r.get("event", ""),
            "location": r.get("location", ""), "country": r.get("country", ""),
            "telemetry": bool(r.get("with_telemetry")), "rotation": r.get("circuit_rotation"),
            "mb": sum(t.get("bytes", 0) for t in r.get("tables", {}).values()) / 1e6,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["order"] = df["session"].map(ORDER).fillna(9)
    return df.sort_values(["year", "round", "order"]).reset_index(drop=True)


def part(table: str, year: int, rnd: int, code: str) -> Path:
    return LAKE / table / f"year={year}" / f"round={int(rnd):02d}" / f"session={code}" / "part.parquet"


@st.cache_data(show_spinner=False)
def read(table: str, year: int, rnd: int, code: str, where: str = "") -> pd.DataFrame:
    path = part(table, year, rnd, code)
    if not path.exists():
        return pd.DataFrame()
    sql = f"SELECT * FROM read_parquet('{path}')" + (f" WHERE {where}" if where else "")
    con = duckdb.connect()
    try:
        return con.sql(sql).df()
    finally:
        con.close()


@st.cache_data(show_spinner=False)
def laps(year: int, rnd: int, code: str) -> pd.DataFrame:
    df = read("laps", year, rnd, code)
    if not df.empty:
        df["DriverNumber"] = df["DriverNumber"].astype(str)
        for col in ("PitInTime_s", "PitOutTime_s"):
            if col not in df.columns:
                df[col] = np.nan
    return df


@st.cache_data(show_spinner=False)
def drivers(year: int, rnd: int, code: str) -> pd.DataFrame:
    """One row per driver, best finisher first, with team colour when known."""
    lp = laps(year, rnd, code)
    if lp.empty:
        return pd.DataFrame()
    d = lp.groupby("Driver", as_index=False).agg(
        number=("DriverNumber", "first"), team=("Team", "first"))
    res = read("results", year, rnd, code)
    if not res.empty and {"Abbreviation", "Position"} <= set(res.columns):
        keep = {"Abbreviation": "Driver", "Position": "finish",
                "TeamColor": "color", "GridPosition": "grid"}
        res = res[[c for c in keep if c in res.columns]].rename(columns=keep)
        d = d.merge(res, on="Driver", how="left")
    for col in ("finish", "color", "grid"):
        if col not in d.columns:
            d[col] = np.nan
    d["finish"] = pd.to_numeric(d["finish"], errors="coerce").fillna(99)
    d["color"] = [f"#{c}" if isinstance(c, str) and c else FALLBACK[i % len(FALLBACK)]
                  for i, c in enumerate(d["color"])]
    return d.sort_values(["finish", "Driver"]).reset_index(drop=True)


def pick_session(need_telemetry: bool = False, key: str = "s") -> dict:
    """Season / event / session selectors. Returns the chosen session as a dict."""
    df = sessions()
    if df.empty:
        st.warning("No sessions found in data/lake yet. Run batch.py first.")
        st.stop()
    if need_telemetry:
        df = df[df["telemetry"]]
        if df.empty:
            st.warning("No sessions with telemetry yet.")
            st.stop()
    c1, c2, c3 = st.columns(3)
    years = sorted(df["year"].unique(), reverse=True)
    year = c1.selectbox("Season", years, key=f"{key}_year")
    events = df[df["year"] == year].drop_duplicates("round").sort_values("round")
    labels = {int(r["round"]): f"R{int(r['round']):02d} {r['event']}" for _, r in events.iterrows()}
    rnd = c2.selectbox("Event", list(labels), index=len(labels) - 1,
                       format_func=labels.get, key=f"{key}_event")
    ss = df[(df["year"] == year) & (df["round"] == rnd)].sort_values("order")
    codes = list(ss["session"])
    code = c3.selectbox("Session", codes, index=codes.index("R") if "R" in codes else 0,
                        format_func=lambda c: SESSION_NAMES.get(c, c), key=f"{key}_session")
    return ss[ss["session"] == code].iloc[0].to_dict()

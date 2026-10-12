"""Helpers for race-level views: track-status ranges, gap tables and lap traces."""

import numpy as np
import pandas as pd

import pitwall as pw

STATUS_STYLE = {
    "SC": ("Safety car", "#ff9f1c"),
    "VSC": ("Virtual safety car", "#ffd166"),
    "RED": ("Red flag", "#e63946"),
}


def _runs(laps: list[int]) -> list[tuple[int, int]]:
    runs, start, prev = [], None, None
    for n in laps:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            runs.append((start, prev))
            start = prev = n
    if start is not None:
        runs.append((start, prev))
    return runs


def status_ranges(laps: pd.DataFrame) -> list[tuple[int, int, str]]:
    """Lap ranges where at least half the field ran under SC / VSC / red flag.

    Based on each lap's TrackStatus codes: 4 = safety car, 5 = red flag, 6 or 7 = VSC."""
    if laps.empty or "TrackStatus" not in laps.columns:
        return []
    d = laps.dropna(subset=["TrackStatus", "LapNumber"]).copy()
    d["lap"] = d["LapNumber"].astype(int)
    d["ts"] = d["TrackStatus"].astype(str)
    out = []
    for code, chars in (("RED", "5"), ("SC", "4"), ("VSC", "67")):
        hit = d["ts"].map(lambda x, ch=chars: any(c in x for c in ch))
        share = hit.groupby(d["lap"]).mean()
        flagged = sorted(int(n) for n in share[share >= 0.5].index)
        out += [(a, b, code) for a, b in _runs(flagged)]
    return sorted(out)


def gap_table(laps: pd.DataFrame) -> pd.DataFrame:
    """Gap to the first car across the line, at the end of each lap."""
    d = laps.dropna(subset=["Time_s", "LapNumber"]).copy()
    d["lap"] = d["LapNumber"].astype(int)
    d["gap_s"] = d["Time_s"] - d.groupby("lap")["Time_s"].transform("min")
    return d[["Driver", "lap", "gap_s", "Position"]]


def snapshot(laps: pd.DataFrame, lap: int) -> pd.DataFrame:
    """Lap-resolution timing tower: order of crossing the line at the end of `lap`."""
    d = laps[laps["LapNumber"] == lap].dropna(subset=["Time_s"]).sort_values("Time_s").copy()
    if d.empty:
        return d
    d["order"] = range(1, len(d) + 1)
    d["gap to leader"] = (d["Time_s"] - d["Time_s"].iloc[0]).round(3)
    d["interval"] = d["Time_s"].diff().round(3)
    d["last lap"] = d["LapTime_s"].map(pw.fmt_lap)
    out = d[["order", "Driver", "gap to leader", "interval", "last lap", "Compound", "TyreLife"]]
    return out.rename(columns={"TyreLife": "tyre age"})


def lap_trace(year: int, rnd: int, code: str, row) -> dict | None:
    """Speed, throttle, brake and gear for one lap, against time and integrated distance."""
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
    gear = pd.to_numeric(car["ngear"], errors="coerce").fillna(0).astype(float).to_numpy()
    drs = np.isin(pd.to_numeric(car["drs"], errors="coerce").fillna(0).astype(float)
                  .to_numpy(), (10, 12, 14)).astype(float)
    dist = np.cumsum(speed / 3.6 * np.diff(t, prepend=t[0]))
    dist = np.maximum.accumulate(dist) + np.arange(len(dist)) * 1e-6
    return {"t": t, "dist": dist, "speed": speed, "throttle": throttle,
            "brake": brake, "gear": gear, "drs": drs}


def on_grid(trace: dict, length: float, grid: np.ndarray) -> dict:
    """Resample a lap trace onto a common distance grid (laps scaled to the same length)."""
    d = trace["dist"] * (length / trace["dist"][-1])
    return {k: np.interp(grid, d, trace[k]) for k in ("t", "speed", "throttle", "brake", "gear", "drs")}

def driver_frames(laps: pd.DataFrame) -> dict:
    """One frame per driver, indexed by lap number, with 'clean' and 'green' flags."""
    d = laps.dropna(subset=["LapNumber"]).copy()
    d["LapNumber"] = d["LapNumber"].astype(int)
    d["clean"] = d["PitInTime_s"].isna() & d["PitOutTime_s"].isna() & d["LapTime_s"].notna()
    d["green"] = d["TrackStatus"].astype(str) == "1"
    return {name: g.sort_values("LapNumber").drop_duplicates("LapNumber").set_index("LapNumber")
            for name, g in d.groupby("Driver")}


def pace(g: pd.DataFrame, before: int) -> float:
    """Median of the last 3 clean green laps before lap `before` (NaN if fewer than 2)."""
    ks = [k for k in range(before - 1, before - 9, -1) if k in g.index]
    c = g.loc[ks]
    c = c[c["clean"] & c["green"]]
    return float(c["LapTime_s"].head(3).median()) if len(c) >= 2 else float("nan")


def actual_stops(g: pd.DataFrame) -> list[int]:
    out = []
    for n in g.index[g["PitInTime_s"].notna()]:
        if (n + 1) in g.index and pd.notna(g.at[n + 1, "PitOutTime_s"]):
            out.append(int(n))
    return out


def predict_rejoin(frames: dict, driver: str, n: int, loss: float) -> dict | None:
    """Predict the position at the end of the out-lap if `driver` pits on in-lap `n`.

    Uses only information known at the end of lap n-1. Assumes nobody else pits."""
    g = frames[driver]
    m = n - 1
    if m not in g.index:
        return None
    t_d, p_d = g.at[m, "Time_s"], pace(g, n)
    if pd.isna(t_d) or pd.isna(p_d):
        return None
    mine = float(t_d) + 2 * p_d + loss
    others = []
    for name, go in frames.items():
        if name == driver or m not in go.index:
            continue
        t_o, p_o = go.at[m, "Time_s"], pace(go, n)
        if not (pd.isna(t_o) or pd.isna(p_o)):
            others.append((name, float(t_o) + 2 * p_o))
    return {"position": 1 + sum(1 for _, t in others if t < mine), "driver_time": mine,
            "others": others, "now": g.at[m, "Position"]}


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


# ---- flag timeline ---------------------------------------------------------------------

def flag_laps(laps: pd.DataFrame) -> dict[int, str]:
    """Lap number -> YEL / VSC / SC / RED when at least half the field ran under that status.

    Codes from each lap's TrackStatus: 2 yellow, 4 safety car, 5 red, 6 or 7 VSC. Red beats
    safety car beats VSC beats yellow when several apply to one lap."""
    d = laps.dropna(subset=["TrackStatus", "LapNumber"]).copy()
    d["lap"] = d["LapNumber"].astype(int)
    d["ts"] = d["TrackStatus"].astype(str)
    out = {}
    for code, chars in (("YEL", "2"), ("VSC", "67"), ("SC", "4"), ("RED", "5")):
        hit = d["ts"].map(lambda x, ch=chars: any(c in x for c in ch))
        share = hit.groupby(d["lap"]).mean()
        for n in share[share >= 0.5].index:
            out[int(n)] = code
    return out

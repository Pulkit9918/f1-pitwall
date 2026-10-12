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
    dist = np.cumsum(speed / 3.6 * np.diff(t, prepend=t[0]))
    dist = np.maximum.accumulate(dist) + np.arange(len(dist)) * 1e-6
    return {"t": t, "dist": dist, "speed": speed, "throttle": throttle,
            "brake": brake, "gear": gear}


def on_grid(trace: dict, length: float, grid: np.ndarray) -> dict:
    """Resample a lap trace onto a common distance grid (laps scaled to the same length)."""
    d = trace["dist"] * (length / trace["dist"][-1])
    return {k: np.interp(grid, d, trace[k]) for k in ("t", "speed", "throttle", "brake", "gear")}

"""Prototype race-state engine: turn GPS positions into per-driver race progress, then test it.

usage: python engine_probe.py [YEAR ROUND SESSION]      (default: 2026 17 R)

Progress P(t) = laps completed + fraction of the lap, for every driver at every moment.
Laps are anchored to the official timing at the start/finish line, so the order AT the line is
right by construction. The real test is the two sector lines in the middle of the lap, which the
engine never sees: at the moment each driver crosses a sector line, is the engine's running
order the same as the order derived from the official sector times?
"""

import sys
import time

import duckdb
import numpy as np
import pandas as pd

YEAR, RND, CODE = ((int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
                   if len(sys.argv) >= 4 else (2026, 17, "R"))
LAKE = "data/lake"
T_START = time.monotonic()


def path(table: str) -> str:
    return f"{LAKE}/{table}/year={YEAR}/round={RND:02d}/session={CODE}/part.parquet"


con = duckdb.connect()
laps = con.sql(f"SELECT * FROM read_parquet('{path('laps')}')").df()
pos = con.sql(f"""SELECT driver_number, session_time_s, x, y
                  FROM read_parquet('{path('telemetry_pos')}')
                  WHERE x IS NOT NULL AND y IS NOT NULL""").df()
res = con.sql(f"SELECT Abbreviation, Position FROM read_parquet('{path('results')}')").df()

laps = laps.dropna(subset=["LapNumber"]).copy()
laps["LapNumber"] = laps["LapNumber"].astype(int)
laps["DriverNumber"] = laps["DriverNumber"].astype(int)
for c in ("x", "y", "session_time_s"):
    pos[c] = pos[c].astype(float)
print(f"{YEAR} round {RND} {CODE}: {len(laps)} laps, {len(pos):,} position samples, "
      f"{laps['Driver'].nunique()} drivers")

# ---- reference track: the winner's fastest clean lap, as a polyline from line to line --------
winner = res.loc[res["Position"] == 1, "Abbreviation"].iloc[0]
wl = laps[(laps["Driver"] == winner) & laps["LapTime_s"].notna()
          & laps["PitInTime_s"].isna() & laps["PitOutTime_s"].isna()]
ref_row = wl.loc[wl["LapTime_s"].idxmin()]
num_w = int(ref_row["DriverNumber"])
pw_ = pos[(pos["driver_number"] == num_w)
          & (pos["session_time_s"] >= ref_row["LapStartTime_s"])
          & (pos["session_time_s"] <= ref_row["Time_s"])].sort_values("session_time_s")
ref_xy = pw_[["x", "y"]].to_numpy(float)
ref_t = pw_["session_time_s"].to_numpy(float)
seg = np.sqrt((np.diff(ref_xy, axis=0) ** 2).sum(1))
keep = np.concatenate([[True], seg > 1.0])
ref_xy, ref_t = ref_xy[keep], ref_t[keep]
seg = np.sqrt((np.diff(ref_xy, axis=0) ** 2).sum(1))
s_ref = np.concatenate([[0.0], np.cumsum(seg)])
L = float(s_ref[-1])
frac_s = {}
for k, col in ((1, "Sector1SessionTime_s"), (2, "Sector2SessionTime_s")):
    v = ref_row.get(col)
    frac_s[k] = float(np.interp(v, ref_t, s_ref) / L) if pd.notna(v) else None
print(f"reference: {winner} lap {int(ref_row['LapNumber'])}, {len(ref_xy)} points, "
      f"length {L / 10:.0f} m; sector lines at {frac_s[1]:.3f} and {frac_s[2]:.3f} of the lap"
      if all(v is not None for v in frac_s.values()) else
      f"reference: {winner} lap {int(ref_row['LapNumber'])}, length {L / 10:.0f} m; no sector times")


def project(xy, ref, s):
    """Distance along the reference line of the nearest point, and how far off it the car is."""
    a, b = ref[:-1], ref[1:]
    ab = b - a
    seg_len = np.sqrt((ab ** 2).sum(1))
    n_seg = len(a)
    s_out, d_out = np.empty(len(xy)), np.empty(len(xy))
    for lo in range(0, len(xy), 20000):
        p = xy[lo:lo + 20000]
        d2 = ((p[:, None, :] - ref[None, :, :]) ** 2).sum(2)
        k = d2.argmin(1)
        best_d2 = np.full(len(p), np.inf)
        best_s = np.zeros(len(p))
        for j in (k - 1, k):
            j = np.clip(j, 0, n_seg - 1)
            t = np.clip(((p - a[j]) * ab[j]).sum(1) / (seg_len[j] ** 2), 0.0, 1.0)
            proj = a[j] + t[:, None] * ab[j]
            dd = ((p - proj) ** 2).sum(1)
            better = dd < best_d2
            best_d2 = np.where(better, dd, best_d2)
            best_s = np.where(better, s[j] + t * seg_len[j], best_s)
        s_out[lo:lo + 20000] = best_s
        d_out[lo:lo + 20000] = np.sqrt(best_d2)
    return s_out, d_out


# ---- progress per driver ------------------------------------------------------------------
prog, diag = {}, []
for drv, dl in laps.groupby("Driver"):
    num = int(dl["DriverNumber"].iloc[0])
    p = (pos[pos["driver_number"] == num].sort_values("session_time_s")
         .drop_duplicates("session_time_s"))
    if len(p) < 100:
        diag.append((drv, len(p), None, None, None))
        continue
    t = p["session_time_s"].to_numpy(float)
    s_raw, dist = project(p[["x", "y"]].to_numpy(float), ref_xy, s_ref)
    S = np.unwrap(s_raw, period=L)
    jumps = int((np.abs(np.diff(S)) > 1000).sum())          # more than 100 m in one sample
    P = np.full(len(t), np.nan)
    prev_end = None
    for r in dl.sort_values("LapNumber").drop_duplicates("LapNumber").itertuples():
        t1 = r.Time_s
        if pd.isna(t1):
            break
        if prev_end is not None:
            t0 = prev_end
        else:
            t0 = r.LapStartTime_s if pd.notna(r.LapStartTime_s) else t[0]
        prev_end = t1
        if t1 <= t0:
            continue
        m = (t > t0) & (t <= t1)
        if m.sum() < 5:
            continue
        s0, s1 = np.interp(t0, t, S), np.interp(t1, t, S)
        span = s1 - s0
        if 0.6 * L <= span <= 1.4 * L:
            frac = (S[m] - s0) / span
        else:
            frac = (t[m] - t0) / (t1 - t0)                    # fall back to linear in time
        P[m] = (int(r.LapNumber) - 1) + np.clip(frac, 0, 1)
    ok = ~np.isnan(P)
    if ok.sum() < 100:
        diag.append((drv, len(p), None, None, None))
        continue
    prog[drv] = (t[ok], np.maximum.accumulate(P[ok]))
    diag.append((drv, len(p), float(np.median(dist)) / 10, float((dist > 200).mean() * 100), jumps))

d = pd.DataFrame(diag, columns=["driver", "samples", "median off-line (m)", "% over 20 m", "jumps"])
print(f"\nMAP-MATCHING QUALITY: {len(prog)} of {laps['Driver'].nunique()} drivers usable")
print(f"  median distance from the reference line: {d['median off-line (m)'].median():.1f} m")
print(f"  share of samples more than 20 m off it: {d['% over 20 m'].mean():.1f}% "
      "(pit lane and run-offs count here)")
print(f"  impossible jumps (over 100 m between samples): {int(d['jumps'].fillna(0).sum())} "
      f"in {int((d['jumps'].fillna(0) > 0).sum())} drivers")
unusable = d[d["median off-line (m)"].isna()]["driver"].tolist()
if unusable:
    print(f"  no usable position data for: {unusable}")


def p_at(drv, T):
    tv, pv = prog[drv]
    return float(np.interp(T, tv, pv, left=0.0, right=pv[-1]))


# lap-resolution baseline: the official position at the end of the previous lap
official_pos = {(r.Driver, r.LapNumber): r.Position for r in laps.itertuples()
                if pd.notna(r.Position)}


def test_line(col, frac):
    cross = {}
    for drv, dl in laps.groupby("Driver"):
        x = dl.dropna(subset=[col]).sort_values(col)
        cross[drv] = (np.maximum.accumulate(x["LapNumber"].to_numpy(int)), x[col].to_numpy(float))
    rows, terr = [], []
    for drv, (lapn, times) in cross.items():
        if drv not in prog:
            continue
        tv, pv = prog[drv]
        for n, T in zip(lapn, times):
            if n < 2:
                continue
            ahead_off = 0
            for j, (cl, tj) in cross.items():
                if j == drv:
                    continue
                k = np.searchsorted(tj, T, side="right")
                if k > 0 and cl[k - 1] >= n:
                    ahead_off += 1
            pi = p_at(drv, T)
            ahead_eng = sum(1 for j in prog if j != drv and p_at(j, T) > pi)
            base = official_pos.get((drv, n - 1))
            rows.append((drv, int(n), 1 + ahead_off, 1 + ahead_eng, base))
            if frac is not None:
                target = (n - 1) + frac
                if pv[0] <= target <= pv[-1]:
                    terr.append(float(np.interp(target, pv, tv)) - T)
    df = pd.DataFrame(rows, columns=["driver", "lap", "official", "engine", "lap_baseline"])
    return df, np.array(terr)


def summarize(label, df, col):
    sub = df.dropna(subset=[col])
    e = (sub[col] - sub["official"]).abs()
    print(f"  {label:34} n={len(sub):5d}  exact {100 * (e == 0).mean():5.1f}%   "
          f"within 1 {100 * (e <= 1).mean():5.1f}%   mean error {e.mean():.2f} places")


print("\nRUNNING-ORDER TEST AT THE TWO SECTOR LINES (laps 2 onwards)")
worst = []
for k, col in ((1, "Sector1SessionTime_s"), (2, "Sector2SessionTime_s")):
    ev, terr = test_line(col, frac_s[k])
    print(f" sector {k} line, official order from timing:")
    summarize("engine (GPS progress)", ev, "engine")
    summarize("baseline: last lap-end position", ev, "lap_baseline")
    if len(terr):
        a = np.abs(terr)
        print(f"  predicted vs official crossing time: median {np.median(a):.2f} s, "
              f"90th percentile {np.percentile(a, 90):.2f} s, 99th {np.percentile(a, 99):.2f} s "
              f"(n={len(a)})")
    ev["error"] = (ev["engine"] - ev["official"]).abs()
    ev["line"] = k
    worst.append(ev)
w = pd.concat(worst).sort_values("error", ascending=False).head(8)
print("\nLARGEST DISAGREEMENTS")
print(w[["line", "driver", "lap", "official", "engine"]].to_string(index=False))
print(f"\nfinished in {time.monotonic() - T_START:.0f}s")

import os

dbg = os.environ.get("DEBUG_DRIVER")
if dbg:
    name, rng_ = dbg.split(":")
    lo, hi = (int(v) for v in rng_.split("-"))
    dl = (laps[(laps["Driver"] == name) & laps["LapNumber"].between(lo - 1, hi)]
          .sort_values("LapNumber").drop_duplicates("LapNumber"))
    p = (pos[pos["driver_number"] == int(dl["DriverNumber"].iloc[0])]
         .sort_values("session_time_s").drop_duplicates("session_time_s"))
    t = p["session_time_s"].to_numpy(float)
    s_raw, dist = project(p[["x", "y"]].to_numpy(float), ref_xy, s_ref)
    S = np.unwrap(s_raw, period=L)
    print(f"\nDEBUG {name}, laps {lo}-{hi}: the engine should read about "
          f"{frac_s[1]:.2f} at sector line 1 and {frac_s[2]:.2f} at line 2")
    print("  lap  laptime  pit-in pit-out  track  official-pos  engine@S1  engine@S2  off-line>20m  jumps")
    prev_end = None
    for r in dl.itertuples():
        t0 = prev_end if prev_end is not None else (
            r.LapStartTime_s if pd.notna(r.LapStartTime_s) else t[0])
        prev_end = r.Time_s
        if r.LapNumber < lo or pd.isna(r.Time_s):
            continue
        m = (t > t0) & (t <= r.Time_s)
        e1 = (p_at(name, r.Sector1SessionTime_s) - (r.LapNumber - 1)
              if pd.notna(r.Sector1SessionTime_s) else float("nan"))
        e2 = (p_at(name, r.Sector2SessionTime_s) - (r.LapNumber - 1)
              if pd.notna(r.Sector2SessionTime_s) else float("nan"))
        off = 100 * float((dist[m] > 200).mean()) if m.any() else float("nan")
        jumps_ = int((np.abs(np.diff(S[m])) > 1000).sum()) if m.sum() > 1 else 0
        print(f"  {int(r.LapNumber):3d}  {r.LapTime_s:7.1f}  {'Y' if pd.notna(r.PitInTime_s) else '-':>6} "
              f"{'Y' if pd.notna(r.PitOutTime_s) else '-':>7}  {str(r.TrackStatus):>5}  "
              f"{r.Position:12.0f}  {e1:9.2f}  {e2:9.2f}  {off:11.0f}%  {jumps_:5d}")

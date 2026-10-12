"""Race-state engine: GPS positions -> per-driver race progress, running order and gaps.

Progress P(t) = laps completed + fraction of the current lap. Each lap is anchored to the official
timing at the start/finish line; inside the lap, the fraction comes from where the car is on a
reference line (the fastest clean lap of the session). Tested against the official order at the
sector timing lines on four races: exact 89-99.8%, within one place 98-100%.
"""

import duckdb
import numpy as np
import pandas as pd
import streamlit as st

import pitwall as pw

FINISHED = ("Finished", "+", "Lapped")


def rotate(a, deg):
    t = np.deg2rad(deg)
    return a @ np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])


def project(xy, ref, s):
    """Distance along the reference line of the nearest point, and how far off the line it is."""
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


@st.cache_resource(show_spinner="Building race state from GPS data...")
def build(year: int, rnd: int, code: str):
    lp = pw.laps(year, rnd, code)
    path = pw.part("telemetry_pos", year, rnd, code)
    if lp.empty or not path.exists():
        return None
    con = duckdb.connect()
    try:
        pos = con.sql("SELECT driver_number, session_time_s, x, y "
                      f"FROM read_parquet('{path}') WHERE x IS NOT NULL AND y IS NOT NULL").df()
    finally:
        con.close()
    for c in ("x", "y", "session_time_s"):
        pos[c] = pos[c].astype(float)
    laps = lp.dropna(subset=["LapNumber"]).copy()
    laps["LapNumber"] = laps["LapNumber"].astype(int)
    laps["num"] = laps["DriverNumber"].astype(int)

    # reference line: the fastest clean lap of the session, from line to line
    clean = laps[laps["LapTime_s"].notna() & laps["PitInTime_s"].isna()
                 & laps["PitOutTime_s"].isna() & laps["LapStartTime_s"].notna()
                 & laps["Time_s"].notna()]
    if clean.empty:
        return None
    ref_row = clean.loc[clean["LapTime_s"].idxmin()]
    ref = pos[(pos["driver_number"] == int(ref_row["num"]))
              & (pos["session_time_s"] >= ref_row["LapStartTime_s"])
              & (pos["session_time_s"] <= ref_row["Time_s"])].sort_values("session_time_s")
    if len(ref) < 50:
        return None
    ref_xy = ref[["x", "y"]].to_numpy(float)
    seg = np.sqrt((np.diff(ref_xy, axis=0) ** 2).sum(1))
    ref_xy = ref_xy[np.concatenate([[True], seg > 1.0])]
    seg = np.sqrt((np.diff(ref_xy, axis=0) ** 2).sum(1))
    s_ref = np.concatenate([[0.0], np.cumsum(seg)])
    L = float(s_ref[-1])

    res = pw.read("results", year, rnd, code)
    status = {}
    if not res.empty and {"Abbreviation", "Status"} <= set(res.columns):
        status = dict(zip(res["Abbreviation"], res["Status"].astype(str)))

    drivers = {}
    for name, dl in laps.groupby("Driver"):
        num = int(dl["num"].iloc[0])
        p = (pos[pos["driver_number"] == num].sort_values("session_time_s")
             .drop_duplicates("session_time_s"))
        if len(p) < 100:
            continue
        t = p["session_time_s"].to_numpy(float)
        xy = p[["x", "y"]].to_numpy(float)
        s_raw, _ = project(xy, ref_xy, s_ref)
        S = np.unwrap(s_raw, period=L)
        P = np.full(len(t), np.nan)
        approx = set()
        prev_end = None
        dls = dl.sort_values("LapNumber").drop_duplicates("LapNumber")
        for r in dls.itertuples():
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
            if 0.92 * L <= span <= 1.08 * L:
                frac = (S[m] - s0) / span
            else:
                frac = (t[m] - t0) / (t1 - t0)
                approx.add(int(r.LapNumber))
            P[m] = (int(r.LapNumber) - 1) + np.clip(frac, 0, 1)
        ok = ~np.isnan(P)
        if ok.sum() < 100:
            continue
        pv = np.maximum.accumulate(P[ok])
        ins = sorted(dls["PitInTime_s"].dropna().tolist())
        outs = sorted(dls["PitOutTime_s"].dropna().tolist())
        pit_iv = []
        for a in ins:
            later = [o for o in outs if o > a]
            pit_iv.append((a, later[0] if later else a + 30.0))
        drivers[name] = {
            "tv": t[ok], "pv": pv, "pv_inc": pv + np.arange(len(pv)) * 1e-9,
            "tp": t, "x": xy[:, 0], "y": xy[:, 1],
            "lapinfo": dls.set_index("LapNumber")[["LapTime_s", "Compound", "TyreLife"]],
            "pit_iv": pit_iv, "last_end": float(dls["Time_s"].max()),
            "finisher": status.get(name, "Finished").startswith(FINISHED),
            "max_lap": int(dls["LapNumber"].max()),
            "approx": approx,
        }
    if not drivers:
        return None

    l1 = laps[laps["LapNumber"] == 1]
    starts = (l1["Time_s"] - l1["LapTime_s"]).dropna()
    if len(starts):
        start = float(starts.median())
    elif laps["LapStartTime_s"].notna().any():
        start = float(laps["LapStartTime_s"].min())
    else:
        start = float(pos["session_time_s"].min())
    end = float(laps["Time_s"].max())
    grid = np.arange(start, end + 1.0, 1.0)
    lead = np.max([np.interp(grid, d["tv"], d["pv"], left=0.0, right=d["pv"][-1])
                   for d in drivers.values()], axis=0)
    return {"ref_xy": ref_xy, "L": L, "start": start, "end": end, "grid": grid, "lead": lead,
            "drivers": drivers}


def snapshot(state, T):
    """Running order, gaps, tyres and positions of every car at session time T (seconds)."""
    D = state["drivers"]
    rows = []
    for name, d in D.items():
        rows.append({"driver": name,
                     "P": float(np.interp(T, d["tv"], d["pv"], left=0.0, right=d["pv"][-1])),
                     "x": float(np.interp(T, d["tp"], d["x"])),
                     "y": float(np.interp(T, d["tp"], d["y"]))})
    df = pd.DataFrame(rows).sort_values("P", ascending=False).reset_index(drop=True)
    leader, lead_p = df.at[0, "driver"], df.at[0, "P"]

    def t_at(name, P):
        pv = D[name]["pv_inc"]
        if P < pv[0] or P > pv[-1]:
            return np.nan
        return float(np.interp(P, pv, D[name]["tv"]))

    def gap_text(ahead, P, P_ahead):
        down = int(np.floor(P_ahead - P + 1e-9))
        if down >= 1:
            return f"+{down} lap" + ("s" if down > 1 else "")
        ta = t_at(ahead, P)
        return "" if np.isnan(ta) else f"+{T - ta:.1f}"

    out = []
    for i, r in df.iterrows():
        d = D[r["driver"]]
        n_done = int(np.floor(r["P"] + 1e-9))
        li = d["lapinfo"]
        cur = min(n_done + 1, d["max_lap"])
        done = li.loc[li.index <= n_done, "LapTime_s"]
        if i == 0:
            gap, interval = "leader", ""
        else:
            gap = gap_text(leader, r["P"], lead_p)
            interval = gap_text(df.at[i - 1, "driver"], r["P"], df.at[i - 1, "P"])
        in_pit = any(a <= T <= b for a, b in d["pit_iv"])
        status = "PIT" if in_pit else ""
        if T > d["last_end"] + 1:
            status = "FIN" if d["finisher"] else "OUT"
        out.append({
            "pos": i + 1, "driver": r["driver"], "gap": gap, "interval": interval,
            "tyre": li.at[cur, "Compound"] if cur in li.index else "",
            "tyre_age": li.at[cur, "TyreLife"] if cur in li.index else np.nan,
            "last_lap": pw.fmt_lap(li.at[n_done, "LapTime_s"]) if n_done in li.index else "",
            "best_lap": pw.fmt_lap(done.min()) if len(done) else "",
            "pits": sum(1 for a, _ in d["pit_iv"] if a <= T),
            "status": status, "approx": (n_done + 1) in d["approx"],
            "P": r["P"], "x": r["x"], "y": r["y"],
        })
    res = pd.DataFrame(out)
    res["tyre_age"] = pd.to_numeric(res["tyre_age"], errors="coerce").round().astype("Int64")
    return res

"""Backtest of a live-gap rejoin prediction against the lap-resolution model.

usage:  ~/.venvs/f1-app/bin/python rejoin_live_probe.py      (run from the project folder)

For every clean green-flag pit stop in the 2025-2026 races and sprints, predict the driver's position
at the end of the out-lap using only what was known when the car entered the pit lane.
A car ends up ahead after the stop if it is within the pit loss (seconds) of the driver, ahead or behind.
Not modelled: other cars pitting in the same window, and traffic after the stop.
"""

import logging
import sys
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, "app")
import engine as eg  # noqa: E402
import pitwall as pw  # noqa: E402
import racelib as rl  # noqa: E402

LOSS = 22.4   # global green-flag pit loss from the earlier measurement (a single number)

sel = pw.sessions()
sel = sel[sel["session"].isin(["R", "S"]) & sel["telemetry"] & (sel["year"] >= 2025)]
rows, skipped, n_sessions = [], {"not green": 0, "estimated lap": 0}, 0
for srow in sel.itertuples():
    y, r, c = int(srow.year), int(srow.round), srow.session
    state = eg.build(y, r, c)
    if state is None:
        continue
    n_sessions += 1
    laps = pw.laps(y, r, c)
    frames = rl.driver_frames(laps)
    D = state["drivers"]
    for name, g in frames.items():
        if name not in D:
            continue
        for n in rl.actual_stops(g):
            if (n + 1) not in g.index:
                continue
            if not (str(g.at[n, "TrackStatus"]) == "1" and str(g.at[n + 1, "TrackStatus"]) == "1"):
                skipped["not green"] += 1
                continue
            if any(k in D[name]["approx"] for k in (n - 1, n, n + 1)):
                skipped["estimated lap"] += 1
                continue
            actual, t_in = g.at[n + 1, "Position"], g.at[n, "PitInTime_s"]
            if pd.isna(actual) or pd.isna(t_in):
                continue
            d_i = D[name]
            p_i = float(np.interp(t_in, d_i["tv"], d_i["pv"], left=0.0, right=d_i["pv"][-1]))
            fallback = rl.pace(g, n)
            stay = live = oracle = 1
            for j, d_j in D.items():
                if j == name or t_in > d_j["last_end"] + 1:
                    continue
                p_j = float(np.interp(t_in, d_j["tv"], d_j["pv"], left=0.0, right=d_j["pv"][-1]))
                pv, tv = d_j["pv_inc"], d_j["tv"]
                if p_j > p_i:
                    stay += 1
                # oracle: when j actually was (or will be) at the driver's spot on track
                if p_i <= pv[-1]:
                    g_or = t_in - float(np.interp(p_i, pv, tv))
                else:
                    g_or = -1e9
                oracle += int(g_or + LOSS > 0)
                # live: only what was known at the moment of entering the pit lane
                if p_j > p_i:
                    g_live = g_or                       # already ahead: the gap is in the past
                else:
                    pace_j = rl.pace(frames[j], int(np.floor(p_j)) + 1) if j in frames else np.nan
                    if np.isnan(pace_j):
                        pace_j = fallback if not np.isnan(fallback) else 95.0
                    g_live = -(p_i - p_j) * pace_j      # behind: extrapolate at its recent pace
                live += int(g_live + LOSS > 0)
            old = rl.predict_rejoin(frames, name, n, LOSS)
            rows.append({"session": f"{y} R{r:02d} {c}", "driver": name, "lap": n,
                         "actual": actual, "stay": stay, "live": live, "oracle": oracle,
                         "old": np.nan if old is None else old["position"]})

res = pd.DataFrame(rows)
print(f"{n_sessions} sessions, {len(res)} green-flag stops with data "
      f"(skipped: {skipped['not green']} not fully green, {skipped['estimated lap']} on laps the "
      "engine flagged as estimated)")
res = res.dropna(subset=["old"])
print(f"{len(res)} stops where every predictor could run\n")

res["lost"] = res["actual"] - res["stay"]
shift = float(res["lost"].median())
res["typical"] = (res["stay"] + shift).clip(lower=1).round()


def summarize(label, col):
    e = (res[col] - res["actual"]).abs()
    print(f"  {label:46} exact {100 * (e == 0).mean():5.1f}%   within 1 {100 * (e <= 1).mean():5.1f}%"
          f"   mean error {e.mean():.2f} places")


print("REJOIN POSITION AT THE END OF THE OUT-LAP")
print(f"  places actually lost on average: {res['lost'].mean():.1f}")
summarize("baseline: stay in the same position", "stay")
summarize(f"baseline: lose the typical {shift:.0f} places", "typical")
summarize("old model (lap-end times)", "old")
summarize("new model, live gaps", "live")
summarize("new model, oracle gaps (peeks at the future)", "oracle")

res["live err"] = (res["live"] - res["actual"]).abs()
res["old err"] = (res["old"] - res["actual"]).abs()
print("\nMEAN ERROR BY PLACES ACTUALLY LOST")
by = res.groupby(pd.cut(res["lost"], [-30, 0, 2, 5, 9, 30]), observed=True)[["old err", "live err"]]
print(pd.concat([by.size().rename("stops"), by.mean().round(2)], axis=1).to_string())

better = int((res["live err"] < res["old err"]).sum())
worse = int((res["live err"] > res["old err"]).sum())
print(f"\nlive model closer than the old one on {better} stops, further on {worse}, "
      f"equal on {len(res) - better - worse}")
print("\nLARGEST LIVE-MODEL MISSES")
print(res.sort_values("live err", ascending=False).head(6)
      [["session", "driver", "lap", "actual", "stay", "live", "old"]].to_string(index=False))

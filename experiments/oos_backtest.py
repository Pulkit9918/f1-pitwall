"""Out-of-sample check of the pit-loss figure and the rejoin model, season by season.

usage:  ~/.venvs/f1-app/bin/python oos_backtest.py        (run from the project folder)

The 22.4 s pit loss and the lap-end rejoin model were built and tuned on 2025-2026 data. This applies
them, unchanged, to every season from 2022 that is in the lake, and reports each year separately.
Only green-flag stops are used. Not modelled: safety cars, other cars pitting in the same window.
"""

import logging
import sys
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, "app")
import pitwall as pw  # noqa: E402
import racelib as rl  # noqa: E402

LOSS = 22.4

sel = pw.sessions()
sel = sel[sel["session"].isin(["R", "S"]) & (sel["year"] >= 2022)]
rows, per_year = [], {}
for srow in sel.itertuples():
    y, r, c = int(srow.year), int(srow.round), srow.session
    laps = pw.laps(y, r, c)
    if laps.empty:
        continue
    per_year[y] = per_year.get(y, 0) + 1
    d = laps.dropna(subset=["LapNumber"]).copy()
    d["LapNumber"] = d["LapNumber"].astype(int)
    d["clean"] = d["PitInTime_s"].isna() & d["PitOutTime_s"].isna() & d["LapTime_s"].notna()
    field = d[d["clean"]].groupby("LapNumber")["LapTime_s"].median().rename("field")
    d = d.join(field, on="LapNumber")
    frames = rl.driver_frames(laps)
    for name, g in d.groupby("Driver"):
        g = g.sort_values("LapNumber").drop_duplicates("LapNumber").set_index("LapNumber")
        for n in g.index[g["PitInTime_s"].notna()]:
            n = int(n)
            if (n + 1) not in g.index or (n - 1) not in g.index:
                continue
            if pd.isna(g.at[n + 1, "PitOutTime_s"]):
                continue
            if not (str(g.at[n, "TrackStatus"]) == "1" and str(g.at[n + 1, "TrackStatus"]) == "1"):
                continue
            t_in, t_out = g.at[n, "LapTime_s"], g.at[n + 1, "LapTime_s"]
            f_in, f_out = g.at[n, "field"], g.at[n + 1, "field"]
            if any(pd.isna(x) for x in (t_in, t_out, f_in, f_out)):
                continue
            around = [k for k in [*range(n - 4, n), *range(n + 2, n + 6)] if k in g.index]
            cc = g.loc[around]
            cc = cc[cc["clean"] & (cc["TrackStatus"] == "1") & cc["field"].notna()]
            if len(cc) < 3:
                continue
            offset = (cc["LapTime_s"] - cc["field"]).median()
            loss = (t_in - f_in - offset) + (t_out - f_out - offset)
            actual, before = g.at[n + 1, "Position"], g.at[n - 1, "Position"]
            if pd.isna(actual) or pd.isna(before):
                continue
            old = rl.predict_rejoin(frames, name, n, LOSS)
            if old is None:
                continue
            rows.append({"year": y, "loss": loss, "actual": actual, "stay": before,
                         "old": old["position"]})

res = pd.DataFrame(rows)
print("sessions per year:", dict(sorted(per_year.items())))
print(f"{len(res)} green-flag stops measured\n")


def agg(x):
    e = (x["old"] - x["actual"]).abs()
    e0 = (x["stay"] - x["actual"]).abs()
    return pd.Series({
        "stops": len(x),
        "loss median": round(x["loss"].median(), 1),
        "p25": round(x["loss"].quantile(0.25), 1),
        "p75": round(x["loss"].quantile(0.75), 1),
        "exact %": round(100 * (e == 0).mean(), 1),
        "within 1 %": round(100 * (e <= 1).mean(), 1),
        "mean error": round(e.mean(), 2),
        "stay-put error": round(e0.mean(), 2)})


print(f"PIT LOSS (seconds) AND REJOIN-MODEL ACCURACY BY SEASON (model uses {LOSS} s everywhere)")
print(res.groupby("year").apply(agg).to_string())
print()
for label, sub in (("2022-2024", res[res["year"] <= 2024]), ("2025-2026", res[res["year"] >= 2025])):
    if len(sub):
        print(f"{label:10}", agg(sub).to_dict())
print("ALL        ", agg(res).to_dict())

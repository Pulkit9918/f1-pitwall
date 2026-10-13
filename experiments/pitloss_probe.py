import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

LAPS = """
    SELECT year, round, event, session, Driver, LapNumber, LapTime_s,
           PitInTime_s, PitOutTime_s, TrackStatus
    FROM read_parquet('data/lake/laps/*/*/*/part.parquet',
                      hive_partitioning = true, union_by_name = true)
    WHERE session IN ('R', 'S') AND year >= 2025
"""
laps = duckdb.connect().sql(LAPS).df()

loc = {}
for line in Path("data/lake/_manifest/sessions.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    if r.get("round") is not None:
        loc[(r["year"], int(r["round"]), r["session"])] = r.get("location") or r.get("event")
laps["circuit"] = [loc.get((y, int(rd), s), e) for y, rd, s, e in
                   zip(laps["year"], laps["round"], laps["session"], laps["event"])]

laps["clean"] = (laps["PitInTime_s"].isna() & laps["PitOutTime_s"].isna()
                 & laps["LapTime_s"].notna())
key = ["year", "round", "session", "LapNumber"]
field = laps[laps["clean"]].groupby(key)["LapTime_s"].median().rename("field").reset_index()
laps = laps.merge(field, on=key, how="left")


def classify(a, b) -> str:
    s = (a if isinstance(a, str) else "") + (b if isinstance(b, str) else "")
    if "5" in s:
        return "red"
    if "4" in s:
        return "safety car"
    if "6" in s or "7" in s:
        return "vsc"
    if "2" in s:
        return "yellow"
    return "green"


rows = []
for (year, rnd, sess, drv), g in laps.groupby(["year", "round", "session", "Driver"]):
    g = g.sort_values("LapNumber")
    g = g[~g["LapNumber"].duplicated()].set_index("LapNumber")
    for n in g.index[g["PitInTime_s"].notna()]:
        if (n + 1) not in g.index or pd.isna(g.at[n + 1, "PitOutTime_s"]):
            continue
        t_in, t_out = g.at[n, "LapTime_s"], g.at[n + 1, "LapTime_s"]
        f_in, f_out = g.at[n, "field"], g.at[n + 1, "field"]
        if any(pd.isna(x) for x in (t_in, t_out, f_in, f_out)):
            continue
        around = [k for k in [*range(int(n) - 4, int(n)), *range(int(n) + 2, int(n) + 6)]
                  if k in g.index]
        c = g.loc[around]
        c = c[c["clean"] & (c["TrackStatus"] == "1") & c["field"].notna()]
        if len(c) < 3:
            continue
        offset = (c["LapTime_s"] - c["field"]).median()  
        loss = (t_in - f_in - offset) + (t_out - f_out - offset)
        rows.append({"year": year, "round": rnd, "session": sess, "circuit": g["circuit"].iloc[0],
                     "driver": drv, "lap": int(n), "loss": loss,
                     "kind": classify(g.at[n, "TrackStatus"], g.at[n + 1, "TrackStatus"])})
res = pd.DataFrame(rows)
print(f"{laps.groupby(['year','round','session']).ngroups} sessions, {len(res)} stops measured")

print("\nPIT LOSS BY TRACK CONDITION, seconds [min, p5, p25, median, p75, p95, max]")
for kind, sub in res.groupby("kind"):
    q = sub["loss"].quantile([0, .05, .25, .5, .75, .95, 1]).round(1).tolist()
    print(f"  {kind:11} n={len(sub):4d}  {q}")

g = res[res["kind"] == "green"].copy()
tab = g.groupby("circuit")["loss"].agg(stops="count", median="median",
                                       p25=lambda s: s.quantile(.25),
                                       p75=lambda s: s.quantile(.75)).round(1)
print("\nGREEN PIT LOSS BY CIRCUIT (10+ stops)")
print(tab[tab["stops"] >= 10].sort_values("median", ascending=False).to_string())

g["sess"] = list(zip(g["year"], g["round"], g["session"]))
errs = []
for _, r in g.iterrows():
    others = g[g["sess"] != r["sess"]]
    same = others[others["circuit"] == r["circuit"]]["loss"]
    if len(same) >= 10:
        errs.append((abs(r["loss"] - same.median()), abs(r["loss"] - others["loss"].median())))
if errs:
    e = np.array(errs)
    print(f"\nHELD-OUT TEST on {len(e)} green stops (predict each from OTHER sessions)")
    print(f"  circuit median   : mean error {e[:, 0].mean():.2f} s, median error {np.median(e[:, 0]):.2f} s")
    print(f"  global median    : mean error {e[:, 1].mean():.2f} s, median error {np.median(e[:, 1]):.2f} s")
else:
    print("\nNot enough stops per circuit for the held-out test yet.")

print("\nMOST EXTREME GREEN STOPS")
ext = g.reindex(g["loss"].sub(g["loss"].median()).abs().sort_values(ascending=False).index).head(6)
print(ext[["year", "circuit", "session", "driver", "lap", "loss"]].round(1).to_string(index=False))

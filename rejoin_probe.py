import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ALIAS = {"Monte Carlo": "Monaco"}
SQL = """
    SELECT year, round, event, session, Driver, LapNumber, LapTime_s, Time_s, Position,
           PitInTime_s, PitOutTime_s, TrackStatus
    FROM read_parquet('data/lake/laps/*/*/*/part.parquet',
                      hive_partitioning = true, union_by_name = true)
    WHERE session IN ('R', 'S') AND year >= 2025
"""
laps = duckdb.connect().sql(SQL).df()

loc = {}
for line in Path("data/lake/_manifest/sessions.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    if r.get("round") is not None:
        loc[(r["year"], int(r["round"]), r["session"])] = r.get("location") or r.get("event")
names = [loc.get((y, int(rd), s), e) for y, rd, s, e in
         zip(laps["year"], laps["round"], laps["session"], laps["event"])]
laps["circuit"] = [ALIAS.get(c, c) for c in names]
laps["clean"] = laps["PitInTime_s"].isna() & laps["PitOutTime_s"].isna() & laps["LapTime_s"].notna()
laps["green"] = laps["TrackStatus"] == "1"

key = ["year", "round", "session", "LapNumber"]
field = laps[laps["clean"]].groupby(key)["LapTime_s"].median().rename("field").reset_index()
laps = laps.merge(field, on=key, how="left")

sessions = {}
for sk, df in laps.groupby(["year", "round", "session"]):
    sessions[sk] = {d: g.sort_values("LapNumber").drop_duplicates("LapNumber").set_index("LapNumber")
                    for d, g in df.groupby("Driver")}


def pace(g, before):
    """Median of the last 3 clean green laps before lap `before` (None if fewer than 2)."""
    ks = [k for k in range(before - 1, before - 9, -1) if k in g.index]
    c = g.loc[ks]
    c = c[c["clean"] & c["green"]]
    return c["LapTime_s"].head(3).median() if len(c) >= 2 else np.nan


stops = []
for sk, drivers in sessions.items():
    circuit = next(iter(drivers.values()))["circuit"].iloc[0]
    for d, g in drivers.items():
        for n in g.index[g["PitInTime_s"].notna()]:
            n = int(n)
            if (n + 1) not in g.index or pd.isna(g.at[n + 1, "PitOutTime_s"]):
                continue
            a, b = g.loc[n], g.loc[n + 1]
            if not (a["green"] and b["green"]):
                continue
            v = [a["LapTime_s"], b["LapTime_s"], a["field"], b["field"]]
            if any(pd.isna(x) for x in v):
                continue
            around = [k for k in [*range(n - 4, n), *range(n + 2, n + 6)] if k in g.index]
            c = g.loc[around]
            c = c[c["clean"] & c["green"] & c["field"].notna()]
            if len(c) < 3:
                continue
            offset = (c["LapTime_s"] - c["field"]).median()
            stops.append({"sk": sk, "circuit": circuit, "driver": d, "lap": n,
                          "loss": (v[0] - v[2] - offset) + (v[1] - v[3] - offset)})
stops = pd.DataFrame(stops)
print(f"{len(sessions)} sessions, {len(stops)} green-flag stops measured")
by_circuit = stops.groupby("circuit")["loss"].agg(["count", "median"]).round(1)
print(by_circuit[by_circuit["count"] >= 10].sort_values("median", ascending=False).to_string())


def loss_for(stop, per_circuit):
    others = stops[stops["sk"] != stop["sk"]]
    if per_circuit:
        same = others[others["circuit"] == stop["circuit"]]["loss"]
        if len(same) >= 10:
            return same.median()
    return others["loss"].median()


rows = []
for _, s in stops.iterrows():
    drivers = sessions[s["sk"]]
    gd, n = drivers[s["driver"]], int(s["lap"])
    m = n - 1
    if m not in gd.index or (n + 1) not in gd.index:
        continue
    t_d, p_d = gd.at[m, "Time_s"], pace(gd, n)
    actual, before = gd.at[n + 1, "Position"], gd.at[m, "Position"]
    if any(pd.isna(x) for x in (t_d, p_d, actual, before)):
        continue
    others = []
    for o, go in drivers.items():
        if o == s["driver"] or m not in go.index:
            continue
        t_o, p_o = go.at[m, "Time_s"], pace(go, n)
        if not (pd.isna(t_o) or pd.isna(p_o)):
            others.append(t_o + 2 * p_o)
    others = np.array(others)
    out = {"circuit": s["circuit"], "actual": actual, "before": before}
    for name, per in (("global", False), ("circuit_loss", True)):
        t_pred = t_d + 2 * p_d + loss_for(s, per)
        out[name] = 1 + int((others < t_pred).sum())
    rows.append(out)
res = pd.DataFrame(rows)


def summarize(name, pred):
    err = (pred - res["actual"]).abs()
    print(f"  {name:34} exact {100 * (err == 0).mean():4.0f}%   within 1 place "
          f"{100 * (err <= 1).mean():4.0f}%   mean error {err.mean():.2f} places")


print(f"\nREJOIN-POSITION BACKTEST on {len(res)} green-flag stops")
print(f"  places actually lost on average: {(res['actual'] - res['before']).mean():.1f}")
summarize("baseline: stay in the same position", res["before"])
summarize("model, global pit loss", res["global"])
summarize("model, circuit pit loss", res["circuit_loss"])

res["places lost"] = res["actual"] - res["before"]
res["model error"] = (res["global"] - res["actual"]).abs()
print("\nMODEL ERROR (global) BY PLACES ACTUALLY LOST")
print(res.groupby(pd.cut(res["places lost"], [-30, 0, 2, 5, 9, 30]), observed=True)["model error"]
      .agg(["count", "mean"]).round(2).to_string())

shift = float((res["actual"] - res["before"]).median())
const = (res["before"] + shift).clip(lower=1).round()
err = (const - res["actual"]).abs()
print(f"\nFAIRER BASELINE: lose the typical {shift:.0f} places "
      f"-> exact {100 * (err == 0).mean():.0f}%, within 1 place {100 * (err <= 1).mean():.0f}%, "
      f"mean error {err.mean():.2f} places")

shift = float((res["actual"] - res["before"]).median())
const = (res["before"] + shift).clip(lower=1).round()
err = (const - res["actual"]).abs()
print(f"\nFAIRER BASELINE: lose the typical {shift:.0f} places "
      f"-> exact {100 * (err == 0).mean():.0f}%, within 1 place {100 * (err <= 1).mean():.0f}%, "
      f"mean error {err.mean():.2f} places")

"""Estimate tyre degradation for every dry race in the gold layer, under three trend models.

For each race: clean laps on slick tyres, then a least-squares fit of
    lap_time = driver offset + compound offset + trend(lap_number) + b_compound * tyre_life
b  = seconds lost per lap of tyre age, per compound (expected positive).
trend is the part of the pace that changes with the race itself: fuel burn plus track evolution.
  linear : a * lap
  quad   : a * lap + c * lap^2   (lets the track evolve quickly early and flatten later)
  spline : piecewise-linear in lap, slope may change at laps 8, 16 and 30 (the most flexible)
Stints that start on different laps are what separate trend from tyre age. After a red flag
everyone changes tyres together, so the two are collinear there; such races are flagged.
Standard errors are clustered by driver (laps of one driver are not independent).

Filters (all printed): dry races only, clean laps only (green, accurate, not deleted, not an in-lap
or out-lap), SOFT/MEDIUM/HARD only, laps slower than 107% of the session's fastest clean lap dropped.

usage (repository root):  python experiments/tyre_probe.py [--db data/f1_dbt.duckdb] [--years 2018-2026]
                                                            [--show linear|quad|spline]
Reads the dbt database read-only; writes logs/tyre_probe_<time>.csv.
"""

import argparse
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

SLICKS = ("SOFT", "MEDIUM", "HARD")
MODELS = ("linear", "quad", "spline")
KNOTS = (8, 16, 30)  # laps where the spline trend may change slope
CUTOFF = 1.07  # drop laps slower than this multiple of the session's fastest clean lap
MIN_LAPS = 400  # usable laps needed to fit a session
MIN_COMPOUND_LAPS = 120  # laps a compound needs to get its own slope
MIN_AGE_RANGE = 8  # a compound's tyre ages must span at least this many laps

QUERY = """
select l.session_key, l.year, l.round, s.event, l.driver_code, l.lap_number,
       l.compound, l.tyre_life, l.lap_time_s
from gold.fct_lap l
join gold.dim_session s using (session_key)
left join gold.fct_session_weather w using (session_key)
where l.session_code = 'R'
  and l.is_clean_lap
  and l.compound in ('SOFT', 'MEDIUM', 'HARD')
  and l.tyre_life is not null
  and coalesce(w.share_of_samples_raining, 0) = 0
  and l.year between {lo} and {hi}
"""
RED_QUERY = """
select distinct session_key from gold.fct_track_status_period
where session_code = 'R' and cast(status as varchar) = '5'
"""


def design(d: pd.DataFrame, comps: list[str], model: str):
    lap = d["lap_number"].to_numpy(float)
    names, cols = ["lap_number"], [lap]
    if model == "quad":
        names.append("lap_sq")
        cols.append((lap - lap.mean()) ** 2)
    if model == "spline":
        for k in KNOTS:
            if lap.min() < k < lap.max():
                names.append(f"hinge_{k}")
                cols.append(np.maximum(0.0, lap - k))
    for c in comps[1:]:
        names.append(f"offset_{c}")
        cols.append((d["compound"] == c).to_numpy(float))
    for c in comps:
        names.append(f"age_{c}")
        cols.append(np.where(d["compound"] == c, d["tyre_life"], 0).astype(float))
    for drv in sorted(d["driver_code"].unique()):
        names.append(f"driver_{drv}")
        cols.append((d["driver_code"] == drv).to_numpy(float))
    return names, np.column_stack(cols)


def fit_session(d: pd.DataFrame, model: str):
    """Return (rows, reason): rows is a list of dicts (coef, clustered se), or None with a reason."""
    d = d[d["lap_time_s"] <= CUTOFF * d["lap_time_s"].min()]
    counts = d["compound"].value_counts()
    comps = [
        c
        for c in SLICKS
        if counts.get(c, 0) >= MIN_COMPOUND_LAPS
        and np.ptp(d.loc[d["compound"] == c, "tyre_life"]) >= MIN_AGE_RANGE
    ]
    d = d[d["compound"].isin(comps)]
    if not comps or len(d) < MIN_LAPS:
        return None, "too few usable laps"
    names, x = design(d, comps, model)
    y = d["lap_time_s"].to_numpy(float)
    if np.linalg.matrix_rank(x) < x.shape[1]:
        return None, "rank deficient"
    n, p = x.shape
    bread = np.linalg.inv(x.T @ x)
    beta = bread @ x.T @ y
    u = y - x @ beta
    meat = np.zeros((p, p))
    groups = d["driver_code"].to_numpy()
    for g in np.unique(groups):
        idx = groups == g
        s = x[idx].T @ u[idx]
        meat += np.outer(s, s)
    k = len(np.unique(groups))
    cov = bread @ meat @ bread * (k / (k - 1)) * ((n - 1) / (n - p))
    se = np.sqrt(np.diag(cov))
    rows = [
        {"term": nm, "coef": beta[i], "se": se[i], "n_laps": n}
        for i, nm in enumerate(names)
        if nm in ("lap_number", "lap_sq") or nm.startswith("age_")
    ]
    return rows, "ok"


def parse_years(text: str) -> tuple[int, int]:
    lo, _, hi = text.partition("-")
    return int(lo), int(hi or lo)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--db", default="data/f1_dbt.duckdb")
    ap.add_argument("--years", default="2018-2026")
    ap.add_argument("--show", choices=MODELS, default="spline", help="model for the by-year table")
    a = ap.parse_args()
    lo, hi = parse_years(a.years)
    con = duckdb.connect(a.db, read_only=True)
    laps = con.sql(QUERY.format(lo=lo, hi=hi)).df()
    red = set(con.sql(RED_QUERY).df()["session_key"])
    print(f"{len(laps):,} clean slick laps in {laps['session_key'].nunique()} dry races, {lo}-{hi}; "
          f"{len(red & set(laps['session_key']))} of them had a red flag")

    out, skipped = [], {}
    for key, d in laps.groupby("session_key"):
        meta = d.iloc[0]
        for model in MODELS:
            rows, reason = fit_session(d, model)
            if rows is None:
                skipped[(model, reason)] = skipped.get((model, reason), 0) + 1
                continue
            for r in rows:
                out.append({"session_key": key, "year": int(meta["year"]), "round": int(meta["round"]),
                            "event": meta["event"], "model": model, "red_flag": key in red, **r})
    print("skipped:", {f"{m}/{r}": n for (m, r), n in skipped.items()} or "none")
    if not out:
        raise SystemExit("nothing fitted")
    res = pd.DataFrame(out)
    age = res[res["term"].str.startswith("age_")].assign(compound=lambda t: t["term"].str[4:])
    age = age.assign(neg=age["coef"] < 0, sig_neg=age["coef"] + 2 * age["se"] < 0)

    print("\nslopes that are negative (physically impossible, so a sign of a wrong model)")
    print("sig_neg = more than two clustered standard errors below zero")
    g = age.groupby(["model", "red_flag"])
    print(g.agg(slopes=("coef", "size"), negative=("neg", "sum"), sig_neg=("sig_neg", "sum"),
                median_se=("se", "median")).round(4).to_string())

    print("\ntyre degradation by compound, s per lap of tyre age (all dry races)")
    print(age.groupby(["model", "compound"])["coef"].describe().round(4).to_string())

    shown = age[(age["model"] == a.show) & (~age["red_flag"])]
    gy = shown.groupby(["compound", "year"])["coef"]
    print(f"\nby year, model={a.show}, red-flag races excluded: median [p25, p75], races")
    tbl = pd.DataFrame({"races": gy.size(), "median": gy.median(),
                        "p25": gy.quantile(0.25), "p75": gy.quantile(0.75)})
    print(tbl.round(4).to_string())

    Path("logs").mkdir(exist_ok=True)
    path = Path("logs") / f"tyre_probe_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    res.to_csv(path, index=False)
    print(f"\nper-race coefficients: {path}")


if __name__ == "__main__":
    main()

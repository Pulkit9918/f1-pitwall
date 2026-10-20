"""Does a circuit-specific pit loss beat one global figure? Run from the repo root.
Reads data/f1_dbt.duckdb read-only; changes nothing.

Measurement is the one in rejoin_probe.py: for a green-flag stop, loss = (in-lap - field - offset) +
(out-lap - field - offset), where field is the median clean lap of all cars on that lap and offset is the
driver's median gap to the field over the 4 laps before and 4 after (needs 3 clean green laps).
Each stop is predicted from the other sessions: the circuit median if at least MIN_N other stops, else global."""
import duckdb
import numpy as np
import pandas as pd

MIN_N, SHRINK_K = 10, 10
PERIODS = [("2018-2021", 2018, 2021), ("2022-2024", 2022, 2024), ("2025-2026", 2025, 2026)]


def measure(con):
    laps = con.sql("""
        select l.session_key, l.year, l.round, l.driver_code, l.lap_number, l.lap_time_s,
               l.pit_in_time_s, l.pit_out_time_s, l.track_status,
               c.circuit_id, c.circuit_layout_key
        from gold.fct_lap l join gold.dim_session_circuit c using (session_key)
        where l.session_code in ('R', 'S')""").df()
    laps["clean"] = laps.pit_in_time_s.isna() & laps.pit_out_time_s.isna() & laps.lap_time_s.notna()
    laps["green"] = laps.track_status == "1"
    field = (laps[laps.clean].groupby(["session_key", "lap_number"]).lap_time_s.median().rename("field").reset_index())
    laps = laps.merge(field, on=["session_key", "lap_number"], how="left")
    rows = []
    for (sk, drv), g in laps.groupby(["session_key", "driver_code"]):
        g = g.sort_values("lap_number").drop_duplicates("lap_number").set_index("lap_number")
        for n in g.index[g.pit_in_time_s.notna()]:
            n = int(n)
            if (n + 1) not in g.index or pd.isna(g.at[n + 1, "pit_out_time_s"]):
                continue
            a, b = g.loc[n], g.loc[n + 1]
            if not (a.green and b.green):
                continue
            v = [a.lap_time_s, b.lap_time_s, a.field, b.field]
            if any(pd.isna(x) for x in v):
                continue
            around = [k for k in [*range(n - 4, n), *range(n + 2, n + 6)] if k in g.index]
            c = g.loc[around]
            c = c[c.clean & c.green & c.field.notna()]
            if len(c) < 3:
                continue
            offset = (c.lap_time_s - c.field).median()
            rows.append({"session_key": sk, "year": int(a.year), "driver": drv, "lap": n,
                         "circuit_id": a.circuit_id, "layout": a.circuit_layout_key,
                         "loss": (v[0] - v[2] - offset) + (v[1] - v[3] - offset)})
    return laps, pd.DataFrame(rows)


def predict(s, keycol, shrink=False):
    """Leave-one-session-out prediction of each stop's loss."""
    out = np.empty(len(s))
    used = np.zeros(len(s), dtype=bool)
    sess = s.session_key.to_numpy()
    loss = s.loss.to_numpy()
    key = s[keycol].to_numpy()
    glob = {sk: np.median(loss[sess != sk]) for sk in np.unique(sess)}
    cache = {}
    for i in range(len(s)):
        sk, k = sess[i], key[i]
        if (sk, k) not in cache:
            same = loss[(sess != sk) & (key == k)]
            g = glob[sk]
            if shrink:
                cache[(sk, k)] = (g + len(same) / (len(same) + SHRINK_K) * (np.median(same) - g)) if len(same) else g, len(same) > 0
            else:
                cache[(sk, k)] = (np.median(same), True) if len(same) >= MIN_N else (g, False)
        out[i], used[i] = cache[(sk, k)]
    return out, used, np.array([glob[x] for x in sess])


def paired(base_err, new_err, grp, n_boot=2000):
    df = pd.DataFrame({"g": grp, "d": base_err - new_err}).groupby("g")["d"].agg(["sum", "count"])
    s, c = df["sum"].to_numpy(), df["count"].to_numpy()
    rng = np.random.default_rng(2)
    bs = [s[i].sum() / c[i].sum() for i in (rng.integers(0, len(s), len(s)) for _ in range(n_boot))]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return s.sum() / c.sum(), lo, hi


def report(s, n_boot=2000):
    sess = s.session_key.to_numpy()
    print(f"\n{len(s)} green-flag stops in {s.session_key.nunique()} sessions, {s.circuit_id.nunique()} circuits "
          f"({s.layout.nunique()} circuit-layout keys). Loss quantiles (s) 5/25/50/75/95: "
          + ", ".join(f"{q:.1f}" for q in s.loss.quantile([.05, .25, .5, .75, .95])))
    y = s.loss.to_numpy()
    preds = {}
    p, u, g = predict(s, "circuit_id"); preds["circuit (layouts merged)"] = (p, u)
    p, u, _ = predict(s, "layout"); preds["circuit layout (split)"] = (p, u)
    p, u, _ = predict(s, "circuit_id", shrink=True); preds[f"circuit shrunk to global (k={SHRINK_K})"] = (p, u)
    err = {"global": np.abs(y - g)}
    for name, (p, u) in preds.items():
        err[name] = np.abs(y - p)
    print("\nHeld-out error of the predicted pit loss, seconds (each session predicted from the others):")
    for name, e in err.items():
        extra = "" if name == "global" else f", circuit figure used for {preds[name][1].mean():.0%} of stops"
        print(f"  {name:36s} mean {e.mean():.2f}, median {np.median(e):.2f}{extra}")
    print("\nBy period (mean error, global vs circuit with layouts merged):")
    for label, lo_y, hi_y in PERIODS:
        m = ((s.year >= lo_y) & (s.year <= hi_y)).to_numpy()
        if m.any():
            print(f"  {label}: {m.sum():5d} stops  global {err['global'][m].mean():.2f}  circuit {err['circuit (layouts merged)'][m].mean():.2f}")
    print("\nImprovement in mean error over the comparison, seconds, positive = better, 95% interval by session:")
    for a_, b_ in (("global", "circuit (layouts merged)"), ("global", "circuit layout (split)"),
                   ("circuit (layouts merged)", "circuit layout (split)"),
                   ("global", f"circuit shrunk to global (k={SHRINK_K})")):
        m, lo, hi = paired(err[a_], err[b_], sess, n_boot)
        print(f"  {b_:36s} over {a_:26s} {m:+.3f} ({lo:+.3f} to {hi:+.3f})")


def tables(s):
    t = s.groupby("circuit_id").agg(stops=("loss", "size"), seasons=("year", "nunique"), median=("loss", "median"),
                                     p25=("loss", lambda x: x.quantile(.25)), p75=("loss", lambda x: x.quantile(.75))).round(1)
    t = t[t.stops >= MIN_N].sort_values("median", ascending=False)
    print(f"\nGreen-flag pit loss by circuit ({MIN_N}+ stops, layouts merged):")
    print(t.to_string())
    multi = s.groupby("circuit_id").layout.nunique()
    split = s[s.circuit_id.isin(multi[multi > 1].index)]
    if len(split):
        print("\nCircuits with more than one layout in the seed (does the pit-loss median differ by layout?):")
        print(split.groupby("layout").loss.agg(stops="size", median="median").round(1).to_string())


if __name__ == "__main__":
    con = duckdb.connect("data/f1_dbt.duckdb", read_only=True)
    laps, stops = measure(con)
    print("track_status values (top):", laps.track_status.value_counts().head(5).to_dict())
    if len(stops) < 200:
        raise SystemExit(f"Only {len(stops)} stops measured.")
    report(stops)
    tables(stops)

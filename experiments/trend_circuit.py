"""Does a per-circuit offset, shrunk toward the global lap-length line, predict a held-out race better?

Each race is held out in turn. The global line is refit without it. The circuit offset comes from that
circuit's OTHER races only (their residuals against that same line), shrunk by n / (n + k), where
k = noise variance / between-circuit variance, estimated inside the fold. Nothing from the held-out
race is used. Compared: the global line, the unshrunk offset, and the shrunk offset."""
import glob

import numpy as np
import pandas as pd

FOCUS = "jeddah|vegas|marina"


def load():
    import duckdb
    d = pd.read_csv(sorted(glob.glob("logs/tyre_probe_*.csv"))[-1])
    t = d[(d.model == "linear") & (d.term == "lap_number")]
    con = duckdb.connect("data/f1_dbt.duckdb", read_only=True)
    p = con.sql("""
    select l.session_key, c.circuit_id, median(l.lap_time_s) as median_lap_s
    from gold.fct_lap l join gold.dim_session_circuit c using (session_key)
    where l.session_code = 'R' and l.is_clean_lap group by 1, 2
    """).df()
    x = t.merge(p, on="session_key")
    return x[(~x.red_flag.astype(bool)) & (x.se < 0.01)].reset_index(drop=True)


def theil_sen(a, b):
    i, j = np.triu_indices(len(a), 1)
    dx = a[j] - a[i]
    ok = dx != 0
    s = np.median((b[j] - b[i])[ok] / dx[ok])
    return s, np.median(b - s * a)


def mad(r):
    r = np.asarray(r)
    return 1.4826 * np.median(np.abs(r - np.median(r)))


def components(res, circ):
    """Within-circuit noise variance and between-circuit variance (method of moments)."""
    df = pd.DataFrame({"r": res, "c": circ})
    g = df.groupby("c")["r"]
    n, m = g.size(), g.mean()
    multi = n[n >= 2].index
    ss = sum(((df.r[df.c == c] - m[c]) ** 2).sum() for c in multi)
    dof = sum(n[c] - 1 for c in multi)
    s2e = ss / dof
    s2u = max(m.var(ddof=1) - s2e * (1 / n).mean(), 1e-8)
    return s2e, s2u


def evaluate(x):
    cs = x.circuit_id.to_numpy()
    a = x.median_lap_s.to_numpy()
    y = x.coef.to_numpy()
    rows = []
    for i in range(len(x)):
        keep = np.arange(len(x)) != i
        s, ic = theil_sen(a[keep], y[keep])
        res = y[keep] - (s * a[keep] + ic)
        same = cs[keep] == cs[i]
        n = int(same.sum())
        s2e, s2u = components(res, cs[keep])
        k = s2e / s2u
        base = s * a[i] + ic
        mean_res = res[same].mean() if n else 0.0
        w = n / (n + k) if n else 0.0
        rows.append(dict(circuit_id=cs[i], year=x.year.iloc[i], n_other=n, k=k, weight=w, actual=y[i],
                         e_line=y[i] - base, e_raw=y[i] - (base + mean_res),
                         e_shrunk=y[i] - (base + w * mean_res)))
    return pd.DataFrame(rows)


def block(o, title):
    print(f"\n{title} ({len(o)} races)")
    for name, col in [("global line", "e_line"), ("unshrunk offset", "e_raw"), ("shrunk offset", "e_shrunk")]:
        e = o[col]
        print(f"  {name:<16} mean abs {e.abs().mean():.4f}  RMSE {np.sqrt((e ** 2).mean()):.4f}  robust spread {mad(e):.4f}")
    if len(o):
        print(f"  shrunk offset is closer than the line for {(o.e_shrunk.abs() < o.e_line.abs()).mean():.0%} of these races")


def cluster_bootstrap(o, reps=2000, seed=0):
    """Mean of (|line error| - |shrunk error|) with a 95% interval, resampling whole circuits."""
    d = (o.e_line.abs() - o.e_shrunk.abs()).groupby(o.circuit_id).agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(reps, len(d)))
    s, c = d["sum"].to_numpy(), d["count"].to_numpy()
    m = s[idx].sum(1) / c[idx].sum(1)
    return d["sum"].sum() / d["count"].sum(), np.percentile(m, [2.5, 97.5])


def report(x):
    o = evaluate(x)
    s2e, s2u = components(_resid_all(x), x.circuit_id.to_numpy())
    print(f"{len(x)} races from {x.circuit_id.nunique()} circuits")
    print(f"variance components on all races: noise sd {np.sqrt(s2e):.4f}, between-circuit sd {np.sqrt(s2u):.4f}, k = {s2e / s2u:.1f}")
    print(f"typical shrinkage weight for a circuit with 3 other races: {3 / (3 + s2e / s2u):.2f}")
    block(o, "All races")
    for m in (1, 2, 3):
        block(o[o.n_other >= m], f"Races with at least {m} other race(s) at the same circuit")
    sub = o[o.n_other >= 1]
    mean, (lo, hi) = cluster_bootstrap(sub)
    print(f"\nGain in mean abs error, line minus shrunk offset, races with a same-circuit history: "
          f"{mean:+.4f} s per lap (95% interval {lo:+.4f} to {hi:+.4f}, resampling circuits)")
    print("  positive = the offset helps; an interval that includes zero means no demonstrated gain")
    f = o[o.circuit_id.str.contains(FOCUS)]
    print("\nFocus circuits, mean signed error when held out (actual minus predicted):")
    print(f.groupby("circuit_id").agg(races=("actual", "size"), line=("e_line", "mean"),
          unshrunk=("e_raw", "mean"), shrunk=("e_shrunk", "mean"), weight=("weight", "mean")).round(4).to_string())
    return o


def _resid_all(x):
    s, ic = theil_sen(x.median_lap_s.to_numpy(), x.coef.to_numpy())
    return x.coef.to_numpy() - (s * x.median_lap_s.to_numpy() + ic)


if __name__ == "__main__":
    report(load())

import glob, duckdb, numpy as np, pandas as pd

d = pd.read_csv(sorted(glob.glob("logs/tyre_probe_*.csv"))[-1])
t = d[(d.model == "linear") & (d.term == "lap_number")]
con = duckdb.connect("data/f1_dbt.duckdb", read_only=True)
p = con.sql("""
select l.session_key, c.circuit_id, median(l.lap_time_s) as median_lap_s
from gold.fct_lap l join gold.dim_session_circuit c using (session_key)
where l.session_code = 'R' and l.is_clean_lap group by 1, 2
""").df()
x = t.merge(p, on="session_key")
x = x[(~x.red_flag.astype(bool)) & (x.se < 0.01)].reset_index(drop=True)

def theil_sen(a, b):
    i, j = np.triu_indices(len(a), 1)
    dx = a[j] - a[i]
    ok = dx != 0
    s = np.median((b[j] - b[i])[ok] / dx[ok])
    return s, np.median(b - s * a)

mad = lambda r: 1.4826 * np.median(np.abs(r - np.median(r)))
rows = []
for cid, g in x.groupby("circuit_id"):
    rest = x[x.circuit_id != cid]
    s, ic = theil_sen(rest.median_lap_s.to_numpy(), rest.coef.to_numpy())
    const = rest.coef.median()
    for r in g.itertuples():
        rows.append(dict(circuit_id=cid, year=r.year, lap_s=r.median_lap_s, actual=r.coef,
                         err_line=r.coef - (s * r.median_lap_s + ic), err_const=r.coef - const))
o = pd.DataFrame(rows)
print(f"{len(x)} races from {x.circuit_id.nunique()} circuits (no red flag, trend standard error under 0.01)")
print("\nOut-of-sample error of the predicted trend, s per lap (each circuit predicted without itself):")
print(f"  one constant: robust spread {mad(o.err_const):.4f}, RMSE {np.sqrt((o.err_const**2).mean()):.4f}, mean abs {o.err_const.abs().mean():.4f}")
print(f"  lap-time line: robust spread {mad(o.err_line):.4f}, RMSE {np.sqrt((o.err_line**2).mean()):.4f}, mean abs {o.err_line.abs().mean():.4f}")
better = (o.err_line.abs() < o.err_const.abs()).mean()
print(f"  the line is closer than the constant for {better:.0%} of races")
print("\nBy lap length (races, mean abs error constant vs line):")
o["band"] = pd.cut(o.lap_s, [0, 75, 85, 95, 105, 200], labels=["<75 s", "75-85", "85-95", "95-105", ">105 s"])
print(o.groupby("band", observed=True).agg(races=("actual", "size"),
      const=("err_const", lambda e: e.abs().mean()), line=("err_line", lambda e: e.abs().mean())).round(4).to_string())
c = o.groupby("circuit_id").agg(races=("actual", "size"), lap_s=("lap_s", "mean"),
      bias_const=("err_const", "mean"), bias_line=("err_line", "mean")).round(4)
c = c[c.races >= 3]
print("\nCircuits with the largest average error of the line when held out (3+ races):")
print(c.reindex(c.bias_line.abs().sort_values(ascending=False).index).head(10).to_string())
print("\nFocus circuits:")
print(c[c.index.str.contains("spa|red_bull|baku|monaco|silverstone|losail|interlagos|marina|zandvoort")].to_string())

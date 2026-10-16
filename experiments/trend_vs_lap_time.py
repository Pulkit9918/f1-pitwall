import glob, duckdb, numpy as np, pandas as pd
d = pd.read_csv(sorted(glob.glob("logs/tyre_probe_*.csv"))[-1])
t = d[(d.model == "linear") & (d.term == "lap_number")]
con = duckdb.connect("data/f1_dbt.duckdb", read_only=True)
p = con.sql("select session_key, median(lap_time_s) as median_lap_s from gold.fct_lap where session_code = 'R' and is_clean_lap group by 1").df()
x = t.merge(p, on="session_key")
keep = x[(~x.red_flag.astype(bool)) & (x.se < 0.01)]
print(f"all races {len(x)}; kept {len(keep)} (no red flag, trend standard error under 0.01); dropped {len(x) - len(keep)}")
a, b = keep.median_lap_s.to_numpy(), keep.coef.to_numpy()
i, j = np.triu_indices(len(a), 1)
s = (b[j] - b[i]) / (a[j] - a[i]); s = s[np.isfinite(s)]
slope = np.median(s); icpt = np.median(b - slope * a)
kappa = np.median(b / a)
mad = lambda r: 1.4826 * np.median(np.abs(r - np.median(r)))
print(f"Pearson {np.corrcoef(a, b)[0, 1]:.2f}, Spearman {keep.median_lap_s.corr(keep.coef, method='spearman'):.2f}")
print(f"robust line (Theil-Sen): trend = {slope:.5f} * lap_s + {icpt:.4f}")
print(f"proportional: trend = {kappa:.5f} * lap_s;  one constant: {np.median(b):.4f}")
print("robust spread of the trend left unexplained (1.48 * MAD, s/lap):")
print(f"  one constant {mad(b):.4f} | proportional {mad(b - kappa * a):.4f} | robust line {mad(b - (slope * a + icpt)):.4f}")
print("predicted trend by lap time:   lap_s   line   proportional")
for sec in (70, 80, 90, 100, 110):
    print(f"                              {sec:5d} {slope * sec + icpt:7.3f} {kappa * sec:8.3f}")

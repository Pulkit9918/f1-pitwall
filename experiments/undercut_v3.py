"""Undercut probe v3: adds the recent pace difference between B and A, and paired bootstrap tests.
Run from the repo root after patch_v2_36.py. Reads data/f1_dbt.duckdb read-only; changes nothing.

pace_diff = median over B's and A's last N_PACE clean laps before B's in-lap of (B lap time - A lap time),
seconds per lap, positive = B slower. Known when B pits. Needs at least MIN_PACE clean paired laps.
car_term  = -pace_diff x (k + 2): what the car pace difference alone would give B over laps L..M."""
import duckdb, numpy as np, pandas as pd
import undercut_v2 as v2
from undercut_v2 import huber, loro, logit, auc

N_PACE, MIN_PACE = 5, 3


def add_pace(con, d):
    laps = con.sql("""select session_key, driver_code, lap_number, lap_time_s,
                      coalesce(is_clean_lap, false) as clean from gold.fct_lap where session_code = 'R'""").df()
    idx = {k: g.set_index("lap_number").sort_index() for k, g in laps.groupby(["session_key", "driver_code"])}
    out = []
    for r in d.itertuples():
        x = idx[(r.session_key, r.a)].reindex(range(r.L - N_PACE, r.L))
        y = idx[(r.session_key, r.b)].reindex(range(r.L - N_PACE, r.L))
        m = (x.clean.eq(True) & y.clean.eq(True)
             & x.lap_time_s.notna() & y.lap_time_s.notna())
        out.append(float((y.lap_time_s[m] - x.lap_time_s[m]).median()) if m.sum() >= MIN_PACE else np.nan)
    return d.assign(pace_diff=out)


def paired(base, new, grp, n_boot=2000):
    """Improvement = mean(base loss - new loss); 95% interval by resampling races."""
    df = pd.DataFrame({"g": grp, "diff": base - new}).groupby("g")["diff"].agg(["sum", "count"])
    s, c = df["sum"].to_numpy(), df["count"].to_numpy()
    rng = np.random.default_rng(1)
    bs = []
    for _ in range(n_boot):
        i = rng.integers(0, len(s), len(s))
        bs.append(s[i].sum() / c[i].sum())
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return s.sum() / c.sum(), lo, hi


def logit_loro(F, yy, grp):
    p = np.empty(len(yy))
    for gid in np.unique(grp):
        te = grp == gid
        mu, sd = (F[~te].mean(0), F[~te].std(0) + 1e-9) if F.shape[1] else (0, 1)
        Xtr = np.c_[np.ones((~te).sum()), (F[~te] - mu) / sd]
        Xte = np.c_[np.ones(te.sum()), (F[te] - mu) / sd]
        p[te] = 1 / (1 + np.exp(-np.clip(Xte @ logit(Xtr, yy[~te]), -30, 30)))
    return p


def analyse3(d, n_boot=2000):
    grp = d.session_key.to_numpy()
    ids = np.unique(grp)
    one = np.ones(len(d))
    car = (-d.pace_diff * (d.k + 2)).to_numpy()
    print(f"\n{len(d)} attempts from {len(ids)} races; pace difference B minus A before the stop: "
          f"median {d.pace_diff.median():.2f} s per lap, middle half {d.pace_diff.quantile(.25):.2f} to {d.pace_diff.quantile(.75):.2f}")

    print("\n== PART 1: pace gain (pace-only delta, robust fits, each race predicted without itself) ==")
    y = d.pace.to_numpy()
    designs = {"M0 constant": np.c_[one], "M1 laps stayed out (k)": np.c_[one, d.k],
               "M2 degradation model": np.c_[one, d.p_deg], "M3 k + degradation": np.c_[one, d.k, d.p_deg],
               "M4 k + car pace": np.c_[one, d.k, car], "M5 k + degradation + car pace": np.c_[one, d.k, d.p_deg, car]}
    err = {}
    for name, X in designs.items():
        err[name] = np.abs(y - loro(huber, X, y, grp))
        print(f"  {name:30s} MAE {err[name].mean():.2f}, median abs error {np.median(err[name]):.2f}, within 1 s {np.mean(err[name] <= 1):.1%}")
    b4 = huber(designs["M4 k + car pace"], y)
    print(f"  M4 fit: pace gain = {b4[0]:.2f} + {b4[1]:.2f} per lap stayed out + {b4[2]:.2f} x car pace term (1.00 would mean the pace difference carries over fully)")
    print("  MAE improvement in seconds, positive = better, 95% interval by race:")
    for a_, b_ in (("M1 laps stayed out (k)", "M3 k + degradation"), ("M1 laps stayed out (k)", "M4 k + car pace"),
                   ("M4 k + car pace", "M5 k + degradation + car pace")):
        m, lo, hi = paired(err[a_], err[b_], grp, n_boot)
        print(f"    {b_[:30]:30s} over {a_[:24]:24s} {m:+.3f} ({lo:+.3f} to {hi:+.3f})")

    print("\n== PART 2: will B be ahead once A has stopped? (what B knows when it pits; A stops within the window) ==")
    yy = (d.margin > 0).astype(float).to_numpy()
    print(f"B ahead in {yy.mean():.1%} of attempts")
    feats = {"L0 base rate": np.zeros((len(d), 0)), "L1 gap": d[["gap"]].to_numpy(),
             "L2 gap + tyre advantage": d[["gap", "adv"]].to_numpy(),
             "L5 gap + pace difference": d[["gap", "pace_diff"]].to_numpy(),
             "L6 gap + advantage + pace": d[["gap", "adv", "pace_diff"]].to_numpy()}
    probs, ll, br = {}, {}, {}
    for name, F in feats.items():
        p = logit_loro(F, yy, grp)
        pc = np.clip(p, 1e-6, 1 - 1e-6)
        probs[name] = p
        ll[name] = -(yy * np.log(pc) + (1 - yy) * np.log(1 - pc))
        br[name] = (p - yy) ** 2
        print(f"  {name:28s} Brier {br[name].mean():.3f}, log loss {ll[name].mean():.3f}, "
              f"correct {np.mean((p > .5) == (yy == 1)):.1%}, AUC {'n/a' if F.shape[1] == 0 else format(auc(p, yy), '.3f')}")
    print("  Improvement over the comparison model, positive = better, 95% interval by race:")
    for a_, b_ in (("L1 gap", "L2 gap + tyre advantage"), ("L1 gap", "L5 gap + pace difference"),
                   ("L5 gap + pace difference", "L6 gap + advantage + pace"), ("L1 gap", "L6 gap + advantage + pace")):
        for label, arr in (("log loss", ll), ("Brier", br)):
            m, lo, hi = paired(arr[a_], arr[b_], grp, n_boot)
            print(f"    {label:8s} {b_[:28]:28s} over {a_[:24]:24s} {m:+.4f} ({lo:+.4f} to {hi:+.4f})")
    best = min(("L1 gap", "L2 gap + tyre advantage", "L5 gap + pace difference", "L6 gap + advantage + pace"), key=lambda n: ll[n].mean())
    F = feats["L6 gap + advantage + pace"]
    Z = np.c_[np.ones(len(d)), (F - F.mean(0)) / F.std(0)]
    cf = logit(Z, yy)
    print(f"\n  Full-sample L6 coefficients per standard deviation: gap {cf[1]:+.2f}, tyre advantage {cf[2]:+.2f}, pace difference {cf[3]:+.2f}")
    print(f"  Calibration of the lowest-log-loss model ({best}), out of sample:")
    cal = pd.DataFrame({"p": probs[best], "y": yy})
    cal["bin"] = pd.cut(cal.p, [0, .2, .4, .6, .8, 1.0])
    print(cal.groupby("bin", observed=True).agg(attempts=("y", "size"), predicted=("p", "mean"), observed=("y", "mean")).round(3).to_string())


if __name__ == "__main__":
    con = duckdb.connect("data/f1_dbt.duckdb", read_only=True)
    d, drops, notund, src = v2.prepare(con)
    d = add_pace(con, d)
    n0 = len(d)
    d = d[d.pace_diff.notna()].reset_index(drop=True)
    print(f"{n0 - len(d)} of {n0} attempts dropped: fewer than {MIN_PACE} clean paired laps in the {N_PACE} before the stop")
    if len(d) < 60:
        raise SystemExit(f"Only {len(d)} attempts kept.")
    analyse3(d)

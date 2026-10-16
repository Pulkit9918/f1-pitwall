"""Undercut probe v2. Run from the repo root. Reads data/f1_dbt.duckdb read-only; changes nothing.

Attempt: B is directly behind A (gap 0-GAP_MAX s at the end of lap L-1, green running) and pits on lap L;
A does not pit that lap but stops k laps later (k <= K_MAX), and no lap from L-1 to A's out-lap M is
not green. Pairs where A never stops, or stops later than K_MAX laps, are not undercuts and are only counted.

margin   = seconds B is ahead of A at the end of lap M (positive = B ahead).
delta    = time A spends on laps L..M minus time B spends = margin + gap.
pace     = delta minus (A's pit-lane time - B's pit-lane time): what the tyres and pace gave B,
           without the luck of how long each stop took.
"""
from collections import Counter
import duckdb, numpy as np, pandas as pd

GAP_MAX, K_MAX, MIN_STINTS = 3.0, 10, 10
PIT_MIN, PIT_MAX = 10.0, 60.0
DRY = {"SOFT", "MEDIUM", "HARD"}


def prepare(con):
    laps = con.sql("""select session_key, year, driver_code, lap_number, position, time_s, tyre_life, compound,
                      coalesce(is_green, false) as is_green from gold.fct_lap where session_code = 'R'""").df()
    stops = con.sql("""select session_key, driver_code, in_lap, compound_after, pit_lane_time_s,
                       coalesce(is_green_stop, false) as is_green_stop
                       from gold.fct_pit_stop where session_code = 'R' and in_lap is not null""").df()
    deg = con.sql("""select s.session_key, s.compound, s.degradation_s_per_lap as dg, c.circuit_layout_key as clk
                     from gold.fct_stint_degradation s join gold.dim_session_circuit c using (session_key)
                     where s.degradation_s_per_lap is not null""").df()
    clk_of = dict(con.sql("select session_key, circuit_layout_key from gold.dim_session_circuit").fetchall())
    by_circ = {k: g[["session_key", "dg"]] for k, g in deg.groupby(["clk", "compound"])}
    by_comp = {k: g[["session_key", "dg"]] for k, g in deg.groupby("compound")}
    src = Counter()

    def dg_for(s, comp):
        sub = by_circ.get((clk_of.get(s), comp))
        if sub is not None:
            x = sub.dg[sub.session_key != s]
            if len(x) >= MIN_STINTS:
                src["circuit median (other races)"] += 1
                return float(x.median())
        src["compound median (other races)"] += 1
        sub = by_comp[comp]
        return float(sub.dg[sub.session_key != s].median())

    b = stops[stops.is_green_stop & (stops.in_lap >= 2)].copy()
    bl = laps.rename(columns={"driver_code": "b", "position": "pos_b", "time_s": "t_b", "tyre_life": "age_b",
                              "compound": "comp_b"})[["session_key", "year", "lap_number", "b", "pos_b", "t_b", "age_b", "comp_b"]]
    c = (b.rename(columns={"driver_code": "b", "in_lap": "L", "compound_after": "comp_b_new"})
           .assign(lap_number=lambda d: d.L - 1).merge(bl, on=["session_key", "lap_number", "b"], how="inner"))
    c = c[c.pos_b.notna() & c.t_b.notna() & (c.pos_b >= 2)]
    al = laps.rename(columns={"driver_code": "a", "position": "pos_a", "time_s": "t_a", "tyre_life": "age_a",
                              "compound": "comp_a"})
    al = al.assign(pos_b=al.pos_a + 1)[["session_key", "lap_number", "pos_b", "a", "t_a", "age_a", "comp_a"]]
    c = c.merge(al, on=["session_key", "lap_number", "pos_b"], how="inner").drop_duplicates(["session_key", "L", "b"])
    c["gap"] = c.t_b - c.t_a
    c = c[(c.gap > 0) & (c.gap <= GAP_MAX)]

    sb = {k: sorted(g.in_lap.tolist()) for k, g in stops.groupby(["session_key", "driver_code"])}
    after = {(r.session_key, r.driver_code, r.in_lap): r.compound_after for r in stops.itertuples()}
    plane = {(r.session_key, r.driver_code, r.in_lap): r.pit_lane_time_s for r in stops.itertuples()}
    lapidx = {k: g.set_index("lap_number").sort_index() for k, g in laps.groupby(["session_key", "driver_code"])}
    keep, drops, notund = [], Counter(), Counter()
    for row in c.itertuples():
        s, a, bb, L = row.session_key, row.a, row.b, row.L
        a_stops = sb.get((s, a), [])
        if L in a_stops:
            drops["A pits the same lap (a double stop, not an undercut)"] += 1; continue
        nxt = [x for x in a_stops if x > L]
        la, lb = lapidx.get((s, a)), lapidx.get((s, bb))
        if not nxt or nxt[0] - L > K_MAX:
            kind = "A stops later than the window" if nxt else "A never stops again"
            E = L + K_MAX + 1
            if (la is not None and lb is not None and E in la.index and E in lb.index
                    and not any(L < x <= E for x in sb.get((s, bb), []))
                    and pd.notna(la.time_s[E]) and pd.notna(lb.time_s[E])):
                notund[(kind, "B ahead" if lb.time_s[E] < la.time_s[E] else "B behind")] += 1
            else:
                notund[(kind, "unresolved")] += 1
            continue
        M = nxt[0] + 1
        if any(L < x <= M for x in sb.get((s, bb), [])):
            drops["B stops again before the outcome"] += 1; continue
        ok = la is not None and lb is not None
        if ok:
            want = range(L - 1, M + 1)
            sa, sbb = la.reindex(want), lb.reindex(want)
            ok = bool(sa.time_s.notna().all() and sbb.time_s.notna().all()
                      and sa.is_green.fillna(False).all() and sbb.is_green.fillna(False).all())
        if not ok:
            drops["a lap in the window missing or not green"] += 1; continue
        k = nxt[0] - L
        comp_a_new = after.get((s, a, nxt[0]))
        if not {row.comp_a, comp_a_new, row.comp_b, row.comp_b_new} <= DRY or pd.isna(row.age_a) or pd.isna(row.age_b):
            drops["non-dry compound or unknown tyre age"] += 1; continue
        plb, pla = plane.get((s, bb, L)), plane.get((s, a, nxt[0]))
        if pd.isna(plb) or pd.isna(pla) or not (PIT_MIN <= plb <= PIT_MAX and PIT_MIN <= pla <= PIT_MAX):
            drops[f"pit-lane time missing or outside {PIT_MIN:g}-{PIT_MAX:g} s"] += 1; continue
        d = {c_: dg_for(s, c_) for c_ in {row.comp_a, comp_a_new, row.comp_b, row.comp_b_new}}
        pdeg = 0.0
        for n in range(L, M + 1):
            age_A, dA = (row.age_a + (n - (L - 1)), d[row.comp_a]) if n <= L + k else (1, d[comp_a_new])
            age_B, dB = (row.age_b + 1, d[row.comp_b]) if n == L else (n - L, d[row.comp_b_new])
            pdeg += dA * age_A - dB * age_B
        adv = d[row.comp_a] * (row.age_a + 1) - d[row.comp_b_new] * 1.0   # known when B pits
        margin = float(la.time_s[M] - lb.time_s[M])
        delta = margin + row.gap
        keep.append(dict(session_key=s, year=row.year, a=a, b=bb, L=int(L), gap=row.gap, k=k, age_a=row.age_a, age_b=row.age_b,
                         p_deg=pdeg, adv=adv, margin=margin, delta=delta, pl_diff=float(pla - plb),
                         pace=delta - float(pla - plb)))
    return pd.DataFrame(keep), drops, notund, src


def lstsq(X, y):
    return np.linalg.lstsq(X, y, rcond=None)[0]


def huber(X, y, c=1.345, iters=60):
    beta = lstsq(X, y)
    for _ in range(iters):
        r = y - X @ beta
        s = max(1.4826 * np.median(np.abs(r - np.median(r))), 1e-6)
        u = np.abs(r) / (c * s)
        w = np.where(u <= 1, 1.0, 1.0 / np.maximum(u, 1e-12))
        XtW = (X * w[:, None]).T
        new = np.linalg.solve(XtW @ X + 1e-9 * np.eye(X.shape[1]), XtW @ y)
        if np.abs(new - beta).max() < 1e-9:
            beta = new; break
        beta = new
    return beta


def loro(fit, X, y, groups):
    pred = np.empty_like(y)
    for g in np.unique(groups):
        te = groups == g
        pred[te] = X[te] @ fit(X[~te], y[~te])
    return pred


def logit(X, y, lam=1e-2):
    b = np.zeros(X.shape[1])
    for _ in range(100):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        H = X.T @ (X * (p * (1 - p))[:, None]) + lam * np.eye(len(b))
        step = np.linalg.solve(H, X.T @ (y - p) - lam * b)
        b += step
        if np.abs(step).max() < 1e-9:
            break
    return b


def auc(score, y):
    r = pd.Series(score).rank().to_numpy()
    n1, n0 = y.sum(), len(y) - y.sum()
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else float("nan")


def analyse(d, n_boot=500):
    grp = d.session_key.to_numpy()
    ids = np.unique(grp)
    one = np.ones(len(d))
    print(f"\n{len(d)} attempts from {len(ids)} races")
    print(f"Raw delta: mean {d.delta.mean():.2f} s, spread (std) {d.delta.std():.2f}; pit-lane time difference A minus B: "
          f"mean {d.pl_diff.mean():.2f}, std {d.pl_diff.std():.2f}; pace-only delta: mean {d.pace.mean():.2f}, std {d.pace.std():.2f}")

    print("\n== PART 1: does the degradation model explain the pace gain? (pace-only delta, robust fits) ==")
    y = d.pace.to_numpy()
    g = d.assign(band=pd.cut(d.k, [0, 1, 2, 3, 5, 10])).groupby("band", observed=True).agg(
        attempts=("pace", "size"), median_pace=("pace", "median"), mean_pace=("pace", "mean"), mean_p_deg=("p_deg", "mean"))
    print(g.round(2).to_string())
    designs = {"M0 constant": np.c_[one], "M1 laps stayed out (k)": np.c_[one, d.k],
               "M2 degradation model": np.c_[one, d.p_deg], "M3 k and degradation": np.c_[one, d.k, d.p_deg]}
    b1 = huber(designs["M1 laps stayed out (k)"], y)
    b2 = huber(designs["M2 degradation model"], y)
    idx = {i: np.where(grp == i)[0] for i in ids}
    rng, bs = np.random.default_rng(0), []
    for _ in range(n_boot):
        pick = np.concatenate([idx[i] for i in rng.choice(ids, len(ids))])
        bs.append(huber(designs["M2 degradation model"][pick], y[pick])[1])
    lo, hi = np.percentile(bs, [2.5, 97.5])
    r2 = y - designs["M2 degradation model"] @ b2
    s2 = 1.4826 * np.median(np.abs(r2 - np.median(r2)))
    print(f"\nM1 (robust): pace gain = {b1[0]:.2f} + {b1[1]:.2f} s per lap stayed out")
    print(f"M2 (robust): pace gain = {b2[0]:.2f} + {b2[1]:.2f} x (degradation-model gain); slope 95% interval by race "
          f"{lo:.2f} to {hi:.2f} (1.00 = calibrated). Robust residual spread {s2:.2f} s; "
          f"{np.mean(np.abs(r2 - np.median(r2)) > 3 * s2):.1%} of attempts are outliers beyond 3 spreads")
    print("\nOut of sample (each race predicted without itself), pace gain error in seconds:")
    for name, X in designs.items():
        p = loro(huber, X, y, grp)
        e = np.abs(y - p)
        print(f"  {name:26s} MAE {e.mean():.2f}, median abs error {np.median(e):.2f}, within 1 s {np.mean(e <= 1):.1%}")

    print("\n== PART 2: what B knows when it pits: will B be ahead once A has stopped? ==")
    print("(only attempts where A does stop within the window; features exclude k)")
    yy = (d.margin > 0).astype(float).to_numpy()
    print(f"B ahead in {yy.mean():.1%} of attempts. Gap bands:")
    gb = d.assign(band=pd.cut(d.gap, [0, 1, 2, 3])).groupby("band", observed=True).margin.agg(
        attempts="size", b_ahead=lambda m: (m > 0).mean())
    print(gb.round(3).to_string())
    feats = {"L0 base rate": np.zeros((len(d), 0)), "L1 gap": d[["gap"]].to_numpy(),
             "L2 gap + tyre advantage now": d[["gap", "adv"]].to_numpy(),
             "L3 gap + A's tyre age": d[["gap", "age_a"]].to_numpy(),
             "L4 gap + advantage + age": d[["gap", "adv", "age_a"]].to_numpy()}
    print(f"\nOut of sample (each race predicted without itself):")
    for name, F in feats.items():
        p = np.empty(len(d))
        for gid in ids:
            te = grp == gid
            mu, sd = (F[~te].mean(0), F[~te].std(0) + 1e-9) if F.shape[1] else (0, 1)
            Xtr = np.c_[np.ones((~te).sum()), (F[~te] - mu) / sd]
            Xte = np.c_[np.ones(te.sum()), (F[te] - mu) / sd]
            p[te] = 1 / (1 + np.exp(-np.clip(Xte @ logit(Xtr, yy[~te]), -30, 30)))
        pc = np.clip(p, 1e-6, 1 - 1e-6)
        print(f"  {name:28s} Brier {np.mean((p - yy) ** 2):.3f}, log loss {-np.mean(yy * np.log(pc) + (1 - yy) * np.log(1 - pc)):.3f}, "
              f"correct {np.mean((p > .5) == (yy == 1)):.1%}, AUC {'n/a' if F.shape[1] == 0 else format(auc(p, yy), '.3f')}")
    grid = np.arange(0.25, 3.01, 0.25)
    pred = np.empty(len(d), dtype=bool)
    for gid in ids:
        te = grp == gid
        accs = [np.mean((d.gap.to_numpy()[~te] <= t) == (yy[~te] == 1)) for t in grid]
        pred[te] = d.gap.to_numpy()[te] <= grid[int(np.argmax(accs))]
    print(f"  gap threshold rule (cut chosen without the race) correct {np.mean(pred == (yy == 1)):.1%}")
    print("  Lower Brier and log loss, higher AUC, are better. A tyre feature only helps if it beats L1.")


if __name__ == "__main__":
    con = duckdb.connect("data/f1_dbt.duckdb", read_only=True)
    d, drops, notund, src = prepare(con)
    for k_, v in drops.most_common():
        print(f"dropped {v:5,}: {k_}")
    print("degradation figures used:", dict(src))
    if notund:
        print(f"\nNot undercuts (A does not stop within {K_MAX} laps); where B stood by lap L+{K_MAX + 1}:")
        for (kind, res), v in sorted(notund.items()):
            print(f"  {kind:32s} {res:10s} {v:5,}")
    if len(d) < 60:
        raise SystemExit(f"Only {len(d)} attempts kept.")
    analyse(d)

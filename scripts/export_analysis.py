"""Export per-race analysis (gaps, undercut and overcut events, pit-now predictions) as static JSON for the web app.

    python scripts/export_analysis.py [--db data/f1_dbt.duckdb] [--out web/public/analysis-data] [--from-year 2022]

Reads fct_lap_gap, fct_pit_now, fct_stop_battle and fct_pit_stop from the gold layer and writes one
<session_key>.json for every race and sprint, plus index.json. Per-driver series are arrays with one slot per
lap (lap 1 is slot 0), null where there is no value. Like the other exporters it only writes into an empty
folder or one it wrote itself.
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "f1_dbt.duckdb"
DEFAULT_OUT = ROOT / "web" / "public" / "analysis-data"
GENERATOR = "export_analysis"
SCHEMA = 1
REGIME_LETTER = {"green": "g", "sc": "s", "vsc": "v", "red": "r"}


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def r(v, nd):
    return None if v is None else round(float(v), nd)


def build_session(key, laps, battles, stops, ratios):
    """laps: rows (driver, lap, position, gap_leader, interval, regime, loss, pred, fast, slow, margin)."""
    n = max((row[1] for row in laps), default=0)
    drivers = {}
    for drv, lap, pos, gl, itv, regime, loss, pred, fast, slow, margin in laps:
        d = drivers.setdefault(drv, {k: [None] * n for k in ("pos", "leader", "interval", "loss", "pred", "fast", "slow", "margin")} | {"regime": ["."] * n})
        i = lap - 1
        d["pos"][i] = pos
        d["leader"][i] = r(gl, 1)
        d["interval"][i] = r(itv, 1)
        d["loss"][i] = r(loss, 1)
        d["pred"][i] = pred
        d["fast"][i] = fast
        d["slow"][i] = slow
        d["margin"][i] = r(margin, 1)
        d["regime"][i] = REGIME_LETTER.get(regime, ".")
    for d in drivers.values():
        d["regime"] = "".join(d["regime"])
    return dict(
        schema=SCHEMA, session_key=key, laps=n, drivers=sorted(drivers),
        series={k: drivers[k] for k in sorted(drivers)},
        stops=[dict(driver=d, lap=int(l)) for d, l in stops],
        battles=[dict(kind=k, attacker=a, defender=df, first_by=fb, first_lap=int(fl), second_lap=int(sl),
                      gap_before_s=r(g, 2), attacker_ahead=bool(ah), margin_after_s=r(m, 2), neutralised=bool(ne))
                 for k, a, df, fb, fl, sl, g, ah, m, ne in battles],
        loss_ratio=ratios,
    )


def export(db, out, from_year=2022, log=print):
    db, out = Path(db), Path(out)
    if not db.exists():
        sys.exit(f"REFUSING: database not found: {db}")
    marker = out / "index.json"
    if out.exists() and any(out.iterdir()):
        try:
            ok = json.loads(marker.read_text()).get("generator") == GENERATOR
        except (OSError, ValueError):
            ok = False
        if not ok:
            sys.exit(f"REFUSING: {out} is not empty and was not written by this script; nothing changed")
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"attach '{str(db).replace(chr(39), chr(39) * 2)}' as f1 (read_only)")

    ratios = {row[0]: dict(stops=row[1], median_loss_s=r(row[2], 1), p25_loss_s=r(row[3], 1), p75_loss_s=r(row[4], 1),
                           ratio=r(row[5], 3), reliable=bool(row[6]))
              for row in con.execute("select regime, stops, median_loss_s, p25_loss_s, p75_loss_s, ratio_to_green, is_reliable "
                                     "from f1.gold.fct_pit_loss_ratio").fetchall()}

    by_laps, by_battles, by_stops = {}, {}, {}
    for row in con.execute(
        "select g.session_key, g.driver_code, g.lap_number, g.position, g.gap_to_leader_s, g.interval_s, "
        "p.regime, p.pit_loss_s, p.predicted_position, p.predicted_position_fast, p.predicted_position_slow, p.margin_s "
        "from f1.gold.fct_lap_gap g left join f1.gold.fct_pit_now p on p.pit_now_key = g.lap_key "
        "where g.year >= ? order by g.session_key, g.driver_code, g.lap_number", [from_year]).fetchall():
        by_laps.setdefault(row[0], []).append(row[1:])
    for row in con.execute(
        "select session_key, kind, attacker_code, defender_code, first_stopper_code, first_stop_lap, second_stop_lap, "
        "gap_before_s, attacker_ahead_after, margin_after_s, is_neutralised "
        "from f1.gold.fct_stop_battle where year >= ? order by session_key, first_stop_lap, attacker_code", [from_year]).fetchall():
        by_battles.setdefault(row[0], []).append(row[1:])
    for row in con.execute(
        "select session_key, driver_code, in_lap from f1.gold.fct_pit_stop "
        "where session_code in ('R','S') and in_lap is not null and session_key in "
        "(select distinct session_key from f1.gold.fct_lap_gap where year >= ?) group by all order by 1, 3, 2", [from_year]).fetchall():
        by_stops.setdefault(row[0], []).append(row[1:])

    keys = sorted(by_laps)
    for key in keys:
        doc = build_session(key, by_laps[key], by_battles.get(key, []), by_stops.get(key, []), ratios)
        (out / f"{key}.json").write_text(dumps(doc), encoding="utf-8")
    marker.write_text(dumps(dict(generator=GENERATOR, schema=SCHEMA, sessions=keys)), encoding="utf-8")
    log(f"wrote {len(keys)} sessions to {out}")
    return keys


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--from-year", type=int, default=2022)
    a = ap.parse_args()
    export(a.db, a.out, a.from_year)


if __name__ == "__main__":
    main()

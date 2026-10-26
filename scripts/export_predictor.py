"""Export how well the pit-now prediction matched real stops as static JSON for the web app.

    python scripts/export_predictor.py [--db data/f1_dbt.duckdb] [--out web/public/predictor-data] [--from-year 2000]

Reads fct_pit_prediction_score and fct_pit_prediction_check from the gold layer and writes
  score.json   one row per scope, regime and margin bucket: hit rates and errors for the model and for two naive guesses,
               and heldout: the same green-flag stops scored with the pit loss estimated without the race itself
  stops.json   every checked stop from --from-year on (by default all of them, matching score.json) as columns of equal
               length, with the sessions they belong to
and index.json, which marks the folder as written by this script. Like the other exporters it only writes into an empty
folder or one it wrote itself.
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "f1_dbt.duckdb"
DEFAULT_OUT = ROOT / "web" / "public" / "predictor-data"
GENERATOR = "export_predictor"
SCHEMA = 1


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def r(x, nd=4):
    return None if x is None else round(float(x), nd)


def export(db, out, from_year=2000, log=print):
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

    rows = [dict(scope=a, regime=b, margin=c, stops=int(d), hit=r(e), within_one=r(f), mae=r(g), bias=r(h), in_range=r(i),
                 no_loss_hit=r(j), no_loss_mae=r(k), global_hit=r(l), global_mae=r(m), reliable=bool(n))
            for a, b, c, d, e, f, g, h, i, j, k, l, m, n in con.execute(
                "select scope, regime, margin_bucket, stops, hit_rate, within_one_rate, mae, bias, in_range_rate, "
                "no_loss_hit_rate, no_loss_mae, global_hit_rate, global_mae, is_reliable "
                "from f1.gold.fct_pit_prediction_score order by scope, regime, margin_bucket").fetchall()]

    heldout = [dict(scope=a, stops=int(b), in_sample_hit=r(c), held_out_hit=r(d), in_sample_mae=r(e), held_out_mae=r(f), loss_shift_s=r(g), circuit_share=r(h))
               for a, b, c, d, e, f, g, h in con.execute(
                   "select scope, stops, in_sample_hit_rate, held_out_hit_rate, in_sample_mae, held_out_mae, loss_shift_s, held_out_circuit_share "
                   "from f1.gold.fct_pit_prediction_heldout_score order by scope").fetchall()]

    checked = con.execute(
        "select c.session_key, c.year, c.round, c.driver_code, c.in_lap, c.regime, c.position_now, c.predicted_position, "
        "c.predicted_position_fast, c.predicted_position_slow, c.actual_position, c.margin_s, c.other_stops_nearby "
        "from f1.gold.fct_pit_prediction_check c where c.year >= ? order by c.session_key, c.in_lap, c.driver_code", [from_year]).fetchall()
    events = {k: v for k, v in con.execute("select session_key, event from f1.gold.dim_session_circuit").fetchall()}
    keys, cols = [], {k: [] for k in ("s", "d", "l", "r", "n", "p", "f", "w", "a", "m", "o")}
    index = {}
    for key, year, rnd, drv, lap, regime, now, pred, fast, slow, actual, margin, other in checked:
        if key not in index:
            index[key] = len(keys)
            keys.append({"key": key, "year": int(year), "round": int(rnd), "event": events.get(key)})
        for k, v in zip(cols, (index[key], drv, int(lap), regime[0], int(now), int(pred), int(fast), int(slow), int(actual), r(margin, 2), int(other))):
            cols[k].append(v)
    (out / "score.json").write_text(dumps({"schema": SCHEMA, "rows": rows, "heldout": heldout}), encoding="utf-8")
    (out / "stops.json").write_text(dumps({"schema": SCHEMA, "sessions": keys, **cols}), encoding="utf-8")
    marker.write_text(dumps({"generator": GENERATOR, "schema": SCHEMA, "stops": len(checked), "sessions": len(keys)}), encoding="utf-8")
    log(f"wrote {len(checked)} stops in {len(keys)} sessions and {len(rows)} score rows to {out}")
    return {"stops": len(checked), "sessions": len(keys), "rows": len(rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--from-year", type=int, default=2000)
    a = ap.parse_args()
    export(a.db, a.out, a.from_year)


if __name__ == "__main__":
    main()

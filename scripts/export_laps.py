"""Export every lap with its sector times and sector colours as static JSON for the web app.

    python scripts/export_laps.py [--db data/f1_dbt.duckdb] [--out web/public/lap-data] [--from-year 2022]

Reads fct_lap and fct_lap_sector from the gold layer and writes one <session_key>.json for every session with timed
laps, plus index.json. Per driver the laps are columns of equal length, one slot per lap in lap order:
  n lap number, t lap time, s1 s2 s3 sector times (seconds, null if not timed), c sector colours as three letters
  (p purple, g green, y yellow, - none), k compound, a tyre age in laps, w track status, o 1 when the lap is clean,
  i 1 when the lap has a pit entry or exit, x 1 when the lap time was deleted.
best holds the quickest time of each sector of the session and who set it. Like the other exporters it only writes
into an empty folder or one it wrote itself.
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "f1_dbt.duckdb"
DEFAULT_OUT = ROOT / "web" / "public" / "lap-data"
GENERATOR = "export_laps"
SCHEMA = 1


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def num(x, digits=3):
    return None if x is None else round(float(x), digits)


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
    rows = con.execute(
        """
        select l.session_key, l.driver_code, coalesce(l.team, ''), l.lap_number, l.lap_time_s,
               l.sector1_s, l.sector2_s, l.sector3_s, l.compound, l.tyre_life, l.track_status, l.is_clean_lap,
               (l.pit_in_time_s is not null or l.pit_out_time_s is not null), coalesce(l.deleted, false),
               s.c1, s.c2, s.c3
        from f1.gold.fct_lap l
        left join (
            select lap_key,
                   max(case when sector = 1 then status end) c1,
                   max(case when sector = 2 then status end) c2,
                   max(case when sector = 3 then status end) c3
            from f1.gold.fct_lap_sector group by lap_key) s on s.lap_key = l.lap_key
        where l.year >= ?
        order by l.session_key, l.driver_code, l.lap_number
        """, [from_year]).fetchall()
    meta = {r[0]: r[1:] for r in con.execute(
        "select session_key, year, round, session_code, event, circuit_name from f1.gold.dim_session_circuit").fetchall()}
    best = {}
    for key, sector, t, driver in con.execute(
        "select session_key, sector, min(time_s), arg_min(driver_code, time_s) from f1.gold.fct_lap_sector group by 1, 2").fetchall():
        best.setdefault(key, {})[str(int(sector))] = {"t": num(t), "d": driver}

    sessions, cur, docs = [], None, {}
    for (key, driver, team, lap, lt, s1, s2, s3, comp, age, status, clean, pit, deleted, c1, c2, c3) in rows:
        doc = docs.get(key)
        if doc is None:
            y, rnd, code, event, circuit = meta.get(key, (None, None, None, None, None))
            doc = docs[key] = {"schema": SCHEMA, "generator": GENERATOR, "session_key": key, "year": y, "round": rnd,
                               "session_code": code, "event": event, "circuit_name": circuit, "best": best.get(key, {}),
                               "drivers": [], "_by": {}}
        d = doc["_by"].get(driver)
        if d is None:
            d = {"code": driver, "team": team, **{k: [] for k in ("n", "t", "s1", "s2", "s3", "c", "k", "a", "w", "o", "i", "x")}}
            doc["_by"][driver] = d
            doc["drivers"].append(d)
        d["n"].append(int(lap))
        d["t"].append(num(lt))
        d["s1"].append(num(s1)); d["s2"].append(num(s2)); d["s3"].append(num(s3))
        d["c"].append("".join((c or "-")[0] for c in (c1, c2, c3)))
        d["k"].append(comp)
        d["a"].append(None if age is None else int(age))
        d["w"].append(status)
        d["o"].append(1 if clean else 0)
        d["i"].append(1 if pit else 0)
        d["x"].append(1 if deleted else 0)
    for i, (key, doc) in enumerate(docs.items(), 1):
        del doc["_by"]
        (out / f"{key}.json").write_text(dumps(doc), encoding="utf-8")
        sessions.append({"key": key, "year": doc["year"], "round": doc["round"], "session_code": doc["session_code"],
                         "event": doc["event"], "drivers": len(doc["drivers"]), "laps": sum(len(d["n"]) for d in doc["drivers"])})
    marker.write_text(dumps({"generator": GENERATOR, "schema": SCHEMA, "sessions": sessions}), encoding="utf-8")
    log(f"wrote {len(sessions)} sessions to {out}: {sum(f.stat().st_size for f in out.iterdir()) / 1e6:.1f} MB")
    return {"written": len(sessions)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--from-year", type=int, default=2022)
    a = ap.parse_args()
    export(a.db, a.out, a.from_year)


if __name__ == "__main__":
    main()

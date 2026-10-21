"""Export season tables (standings, points progression, race results and podiums) as static JSON for the web app.

    python scripts/export_seasons.py [--db data/f1_dbt.duckdb] [--out web/public/season-data] [--from-year 2018]

Reads only the gold layer (fct_driver_standing, fct_constructor_standing, fct_points_progression,
fct_constructor_points_progression, fct_season_result, dim_historical_driver, dim_constructor) and writes
index.json plus one <year>.json per season. The standings are the final table of each season; the
progression series are rebuilt from race and sprint points and are reconciled with the final standings
by dbt tests from 2018 on (2021 excepted for sprints). Like export_replay.py it will only write into an
empty folder or one it wrote itself.
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "f1_dbt.duckdb"
DEFAULT_OUT = ROOT / "web" / "public" / "season-data"
GENERATOR = "export_seasons"
SCHEMA = 1


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def num(v):
    if v is None:
        return None
    f = float(v)
    return int(f) if f == int(f) else round(f, 2)


def season_doc(con, year):
    q = lambda sql: con.execute(sql, [year]).fetchall()
    names = dict(con.execute("select driver_id, full_name from f1.gold.dim_historical_driver").fetchall())
    cons = dict(con.execute("select constructor_id, name from f1.gold.dim_constructor").fetchall())

    drivers = [dict(position=int(p), driver_id=d, name=names.get(d, d), team=t, points=num(pts), wins=int(w or 0))
               for p, d, t, pts, w in q(
        "select position, driver_id, constructor_name, points, wins from f1.gold.fct_driver_standing "
        "where season = ? and position is not null order by position")]
    constructors = [dict(position=int(p), constructor_id=c, name=cons.get(c, c), points=num(pts), wins=int(w or 0))
                    for p, c, pts, w in q(
        "select position, constructor_id, points, wins from f1.gold.fct_constructor_standing "
        "where season = ? and position is not null order by position")]

    rows = q("select round, race_name, cast(race_date as varchar), circuit_id, driver_id, driver_code, constructor_id, "
             "grid, position, points, laps, status, is_classified_finish, fastest_rank "
             "from f1.gold.fct_season_result where season = ? order by round, position nulls last, driver_id")
    races = {}
    for rnd, name, date, circ, did, code, cid, grid, pos, pts, laps, status, fin, fr in rows:
        r = races.setdefault(int(rnd), dict(round=int(rnd), name=name, date=date, circuit_id=circ, results=[]))
        gained = None
        if grid and pos and grid > 0:
            gained = int(grid) - int(pos)
        r["results"].append(dict(
            position=None if pos is None else int(pos), driver_id=did, code=code, name=names.get(did, did),
            constructor_id=cid, team=cons.get(cid, cid), grid=None if grid is None else int(grid),
            points=num(pts), laps=None if laps is None else int(laps), status=status,
            classified=bool(fin), gained=gained, fastest=(fr == 1)))
    codes = {r["driver_id"]: r["code"] for rr in races.values() for r in rr["results"] if r["code"]}
    race_list = [races[k] for k in sorted(races)]
    for r in race_list:
        r["podium"] = [x["driver_id"] for x in r["results"] if x["position"] in (1, 2, 3)][:3]

    prog = q("select round, driver_id, constructor_id, points_in_round, sprint_points, sprint_points_imputed, "
             "cumulative_points, championship_position from f1.gold.fct_points_progression "
             "where season = ? order by round, championship_position")
    cprog = q("select round, constructor_id, cumulative_points, championship_position "
              "from f1.gold.fct_constructor_points_progression where season = ? order by round, championship_position")
    rounds = sorted({int(r[0]) for r in prog})
    series = {}
    for rnd, did, cid, pir, sp, imp, cum, cpos in prog:
        s = series.setdefault(did, dict(driver_id=did, code=codes.get(did, did[:3].upper()), name=names.get(did, did), cum=[], pos=[], imputed=False))
        s["cum"].append(num(cum)); s["pos"].append(int(cpos))
        s["imputed"] = s["imputed"] or bool(imp)
    cseries = {}
    for rnd, cid, cum, cpos in cprog:
        s = cseries.setdefault(cid, dict(constructor_id=cid, name=cons.get(cid, cid), cum=[], pos=[]))
        s["cum"].append(num(cum)); s["pos"].append(int(cpos))
    return dict(schema=SCHEMA, season=year, drivers=drivers, constructors=constructors, races=race_list,
                progression=dict(rounds=rounds, drivers=list(series.values()), constructors=list(cseries.values())))


def export(db, out, from_year=2018, log=print):
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
    years = [r[0] for r in con.execute(
        "select distinct season from f1.gold.fct_season_result where season >= ? order by season", [from_year]).fetchall()]
    index = []
    for y in years:
        doc = season_doc(con, int(y))
        (out / f"{y}.json").write_text(dumps(doc), encoding="utf-8")
        d, c = (doc["drivers"] or [None])[0], (doc["constructors"] or [None])[0]
        index.append(dict(season=int(y), rounds=len(doc["races"]),
                          champion=d and d["name"], champion_id=d and d["driver_id"], champion_points=d and d["points"],
                          constructor_champion=c and c["name"], constructor_points=c and c["points"]))
        log(f"{y}: {len(doc['races'])} races, {len(doc['drivers'])} drivers")
    marker.write_text(dumps(dict(generator=GENERATOR, schema=SCHEMA, seasons=index)), encoding="utf-8")
    log(f"wrote {len(years)} seasons to {out}")
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--from-year", type=int, default=2018)
    a = ap.parse_args()
    export(a.db, a.out, a.from_year)


if __name__ == "__main__":
    main()

"""Export the gold tables as small static JSON files for the web front end.

usage (repository root):  python scripts/export_static.py [--db data/f1_dbt.duckdb] [--out web/public/data] [--from-year 2022]

Writes   manifest.json, sessions.json, circuits.json and sessions/<session_key>.json  (one file per session with laps).
Tables are stored column by column ({"lap_number": [1, 2, ...], ...}) and floats are rounded to 3 decimals to keep the
files small. The database is opened read-only. The output folder is wiped and rewritten on every run, but only if it is
empty or was written by this script (it holds a manifest.json); any other folder is refused and left alone.
"""
import argparse
import gzip
import json
import math
import shutil
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "f1_dbt.duckdb"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "web" / "public" / "data"

LAP_COLS = ["driver_code", "lap_number", "stint", "compound", "tyre_life", "position", "track_status", "is_green",
            "deleted", "is_accurate", "lap_time_s", "lap_start_time_s", "time_s", "pit_in_time_s", "pit_out_time_s",
            "sector1_s", "sector2_s", "sector3_s", "is_clean_lap"]
STINT_COLS = ["driver_code", "stint", "compound", "start_lap", "end_lap", "laps", "clean_laps", "median_clean_lap_s",
              "degradation_s_per_lap"]
PIT_COLS = ["driver_code", "in_lap", "pit_in_time_s", "pit_out_time_s", "pit_lane_time_s", "compound_before",
            "compound_after", "is_green_stop", "position_before"]
PERIOD_COLS = ["period_no", "kind", "start_s", "end_s", "is_open", "has_session_clock"]


def clean(v):
    """JSON-safe value: NaN and infinity become null, floats are rounded, dates become ISO text."""
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else round(v, 3)
    if isinstance(v, Decimal):
        return round(float(v), 3)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def fetch(con, sql, params=None):
    cur = con.execute(sql, params or [])
    names = [d[0] for d in cur.description]
    return [dict(zip(names, (clean(v) for v in row))) for row in cur.fetchall()]


def columnar(rows, cols):
    return {c: [r[c] for r in rows] for c in cols}


def group(rows, key="session_key"):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8")), len(gzip.compress(text.encode("utf-8"), 6))


def export(db, out, from_year=2022):
    db, out = Path(db), Path(out)
    if not db.exists():
        raise SystemExit(f"no database at {db}; build the dbt project first")
    if out.exists() and any(out.iterdir()) and not (out / "manifest.json").exists():
        raise SystemExit(f"refusing: {out} is not empty and was not written by this script")
    con = duckdb.connect()
    con.execute("attach '" + str(db).replace("'", "''") + "' as f1 (read_only)")

    sessions = fetch(con, """
        select s.session_key, s.year, s.round, s.session_code, s.session_name, s.event,
               c.circuit_id, c.circuit_name, c.country, s.has_laps, s.has_results, s.has_race_control
        from f1.gold.dim_session s left join f1.gold.dim_session_circuit c on s.session_key = c.session_key
        where s.year >= ? order by s.year, s.round, s.session_code""", [from_year])
    laps = group(fetch(con, "select session_key, team, " + ", ".join(LAP_COLS) +
                       " from f1.gold.fct_lap where year >= ? order by session_key, driver_code, lap_number", [from_year]))
    stints = group(fetch(con, "select s.session_key, " + ", ".join("s." + c for c in STINT_COLS[:-1]) +
                         ", d.degradation_s_per_lap from f1.gold.fct_stint s left join f1.gold.fct_stint_degradation d "
                         "on s.stint_key = d.stint_key where s.year >= ? order by s.session_key, s.driver_code, s.stint",
                         [from_year]))
    pits = group(fetch(con, "select session_key, " + ", ".join(PIT_COLS) + " from f1.gold.fct_pit_stop "
                       "where session_key in (select session_key from f1.gold.dim_session where year >= ?) "
                       "order by session_key, in_lap, driver_code", [from_year]))
    periods = group(fetch(con, "select session_key, " + ", ".join(PERIOD_COLS) + " from f1.gold.fct_race_control_period "
                          "where year >= ? order by session_key, period_no", [from_year]))

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    total_raw = total_gz = 0
    biggest = ("", 0)
    files = 0
    for s in sessions:
        key = s["session_key"]
        if key not in laps:
            continue
        lr = laps[key]
        teams = {}
        for r in lr:
            teams.setdefault(r["driver_code"], r["team"])
        doc = {
            "session": s,
            "drivers": [{"code": c, "team": t} for c, t in sorted(teams.items())],
            "laps": columnar(lr, LAP_COLS),
            "stints": columnar(stints.get(key, []), STINT_COLS),
            "pit_stops": columnar(pits.get(key, []), PIT_COLS),
            "race_control_periods": [{c: p[c] for c in PERIOD_COLS} for p in periods.get(key, [])],
        }
        raw, gz = write_json(out / "sessions" / f"{key}.json", doc)
        total_raw += raw
        total_gz += gz
        files += 1
        if gz > biggest[1]:
            biggest = (key, gz)

    write_json(out / "sessions.json", {"sessions": sessions})

    circuit_ids = sorted({s["circuit_id"] for s in sessions if s["circuit_id"]})
    pit_loss = {r["circuit_id"]: r for r in fetch(con, "select * from f1.gold.fct_circuit_pit_loss")}
    deg = group(fetch(con, "select circuit_id, circuit_layout_key, layout_id, compound, stints, races, seasons, "
                           "median_degradation_s_per_lap, p25_degradation_s_per_lap, p75_degradation_s_per_lap, "
                           "approx_se_median_s_per_lap, is_reliable from f1.gold.fct_circuit_degradation "
                           "order by circuit_id, layout_id, compound"), key="circuit_id")
    circuits = []
    for c in fetch(con, "select * from f1.gold.dim_circuit order by circuit_id"):
        if c["circuit_id"] not in circuit_ids:
            continue
        pl = pit_loss.get(c["circuit_id"])
        circuits.append({**c,
                         "pit_loss": ({k: pl[k] for k in ("stops", "sessions", "seasons", "median_pit_loss_s",
                                                         "p25_pit_loss_s", "p75_pit_loss_s", "is_reliable")} if pl else None),
                         "degradation": [{k: v for k, v in d.items() if k != "circuit_id"} for d in deg.get(c["circuit_id"], [])]})
    write_json(out / "circuits.json", {"circuits": circuits})

    manifest = {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "from_year": from_year,
                "sessions": len(sessions), "session_files": files, "circuits": len(circuits),
                "seasons": sorted({s["year"] for s in sessions})}
    write_json(out / "manifest.json", manifest)
    con.close()
    return {"session_files": files, "raw_bytes": total_raw, "gzip_bytes": total_gz, "largest": biggest,
            "sessions": len(sessions), "circuits": len(circuits)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--from-year", type=int, default=2022)
    a = ap.parse_args(argv)
    r = export(a.db, a.out, a.from_year)
    print(f"{r['sessions']} sessions listed, {r['session_files']} session files, {r['circuits']} circuits -> {a.out}")
    print(f"session files: {r['raw_bytes'] / 1e6:.1f} MB raw, about {r['gzip_bytes'] / 1e6:.1f} MB gzipped "
          f"(largest: {r['largest'][0]} at {r['largest'][1] / 1e3:.0f} KB gzipped)")


if __name__ == "__main__":
    sys.exit(main())

"""Export lap telemetry against distance (fct_lap_trace) as static JSON for the web app.

    python scripts/export_traces.py [--db data/f1_dbt.duckdb] [--out web/public/trace-data] [--from-year 2024]

For every race or sprint with at least one traced lap it writes  <session_key>/index.json  (the laps of every driver,
with lap time, tyre, track status and whether the lap has a trace, or why not) and  <session_key>/<CODE>.json  (the
traces of that driver's traced laps), plus a top-level index.json that lists the sessions. The page loads the session
index, then one driver file for each driver being compared.

Per lap, with P points from the line to the line (the same distances for every lap of a session, in the session index):
  dt  time between successive points in hundredths of a second, so the running sum is the time at each point
  v   speed in km/h, th  throttle in percent
  g   gear, one digit per point;  d  DRS code, one hex digit per point;  b  brake, 0 or 1 per point
v, th, g, d and b are left out for a lap whose speed channel did not agree with the positions (speed_ok is false).
Like the other exporters it only writes into an empty folder or one it wrote itself.
"""
import argparse
import gzip
import json
import sys
from pathlib import Path

import duckdb

try:
    import numpy as np
except ImportError:  # pragma: no cover
    sys.exit("numpy is required: pip install numpy")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "f1_dbt.duckdb"
DEFAULT_OUT = ROOT / "web" / "public" / "trace-data"
GENERATOR = "export_traces"
SCHEMA = 1


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def digits(a, base):
    """A string with one character per value: the decimal digit (base 10) or hex digit (base 16) of each clipped value."""
    a = np.clip(np.asarray(a, dtype=np.int64), 0, base - 1)
    chars = np.where(a < 10, a + 48, a + 87).astype(np.uint8)
    return chars.tobytes().decode("ascii")


def encode_lap(time_s, speed, throttle, gear, drs, brake):
    """The traces of one lap as the compact dict described in the module docstring."""
    cum = np.round(np.asarray(time_s, dtype=np.float64) * 100).astype(np.int64)
    out = {"dt": np.diff(cum).tolist()}
    if speed is not None:
        out["v"] = np.asarray(speed, dtype=np.int64).tolist()
        out["th"] = np.asarray(throttle, dtype=np.int64).tolist()
        out["g"] = digits(gear, 10)
        out["d"] = digits(drs, 16)
        out["b"] = "".join("1" if x else "0" for x in brake)
    return out


def lap_meta(row):
    driver, team, lap, lap_time, compound, tyre_life, status, has_trace, speed_ok, reason = row
    m = {"n": int(lap), "t": None if lap_time is None else round(float(lap_time), 3)}
    if compound:
        m["c"] = compound
    if tyre_life is not None:
        m["a"] = int(tyre_life)
    if status:
        m["s"] = status
    if has_trace:
        m["k"] = 1 if speed_ok else 0
    else:
        m["r"] = reason
    return m


def export(db, out, from_year=2024, log=print):
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

    sessions = con.execute(
        "select l.session_key, any_value(d.year), any_value(d.round), any_value(d.session_code), any_value(d.event), "
        "any_value(d.circuit_name), any_value(d.country), any_value(l.circuit_layout_key), any_value(l.ref_length_m) "
        "from f1.gold.fct_lap_trace_lap l join f1.gold.dim_session_circuit d on d.session_key = l.session_key "
        "where l.has_trace and l.year >= ? group by l.session_key order by 2, 3, 4", [from_year]).fetchall()
    metas = {}
    for row in con.execute(
        "select l.session_key, l.driver_code, coalesce(f.team, ''), l.lap_number, l.lap_time_s, f.compound, f.tyre_life, "
        "f.track_status, l.has_trace, l.speed_ok, l.trace_reason "
        "from f1.gold.fct_lap_trace_lap l join f1.gold.fct_lap f on f.lap_key = l.lap_key where l.year >= ? "
        "order by l.session_key, l.driver_code, l.lap_number", [from_year]).fetchall():
        metas.setdefault(row[0], []).append(row[1:])

    index, raw, gz, largest, skipped = [], 0, 0, ("", 0), []
    for i, (key, year, rnd, code, event, circuit, country, layout, ref_m) in enumerate(sessions, 1):
        sdir = out / key
        sdir.mkdir(parents=True, exist_ok=True)
        p = con.execute(
            "select driver_code, lap_number, point_idx, dist_m, time_s, speed_kph, throttle_pct, gear, drs, brake "
            "from f1.gold.fct_lap_trace where session_key = ? order by driver_code, lap_number, point_idx", [key]).fetchnumpy()
        drv, lap, idx = (np.asarray(p[k]) for k in ("driver_code", "lap_number", "point_idx"))
        n_points = int(idx.max()) + 1
        starts = np.concatenate([[0], np.flatnonzero((drv[1:] != drv[:-1]) | (lap[1:] != lap[:-1])) + 1, [len(drv)]])
        per_driver, dist = {}, None
        for a, b in zip(starts[:-1], starts[1:]):
            if b - a != n_points or not (idx[a:b] == np.arange(n_points)).all():
                skipped.append((key, str(drv[a]), int(lap[a])))      # a lap that is not a full grid is not exported
                continue
            if dist is None:
                dist = [round(float(x), 1) for x in p["dist_m"][a:b]]
            has_speed = not np.ma.getmaskarray(p["speed_kph"][a:b]).any()      # a lap without a trusted speed channel has nulls
            sl = slice(a, b)
            enc = encode_lap(
                np.ma.filled(p["time_s"][sl], 0),
                np.ma.filled(p["speed_kph"][sl], 0) if has_speed else None,
                np.ma.filled(p["throttle_pct"][sl], 0), np.ma.filled(p["gear"][sl], 0),
                np.ma.filled(p["drs"][sl], 0), np.ma.filled(p["brake"][sl], 0))
            per_driver.setdefault(str(drv[a]), {})[str(int(lap[a]))] = enc
        drivers_meta = {}
        for driver, team, *rest in metas.get(key, []):
            d = drivers_meta.setdefault(driver, {"code": driver, "team": team, "laps": []})
            d["laps"].append(lap_meta((driver, team, *rest)))
        traced = sum(len(v) for v in per_driver.values())
        doc = {"schema": SCHEMA, "generator": GENERATOR, "session_key": key, "year": int(year), "round": int(rnd),
               "session_code": code, "event": event, "circuit_name": circuit, "country": country, "layout": layout,
               "ref_length_m": round(float(ref_m), 1), "points": n_points, "dist": dist,
               "drivers": [drivers_meta[c] for c in sorted(drivers_meta)]}
        text = dumps(doc)
        (sdir / "index.json").write_text(text, encoding="utf-8")
        raw += len(text.encode())
        gz += len(gzip.compress(text.encode(), 6))
        for code_, laps in per_driver.items():
            t = dumps({"schema": SCHEMA, "session_key": key, "driver": code_, "points": n_points, "laps": laps})
            (sdir / f"{code_}.json").write_text(t, encoding="utf-8")
            z = len(gzip.compress(t.encode(), 6))
            raw += len(t.encode())
            gz += z
            if z > largest[1]:
                largest = (f"{key}/{code_}", z)
        index.append({"key": key, "year": int(year), "round": int(rnd), "session_code": code, "event": event,
                      "circuit_name": circuit, "drivers": len(per_driver), "laps": traced})
        log(f"[{i}/{len(sessions)}] {key}: {len(per_driver)} drivers, {traced} traced laps")
    marker.write_text(dumps({"generator": GENERATOR, "schema": SCHEMA, "sessions": index}), encoding="utf-8")
    log(f"wrote {len(index)} sessions to {out}: {raw / 1e6:.1f} MB raw, {gz / 1e6:.1f} MB gzipped; "
        f"largest driver file {largest[0]} at {largest[1] / 1e3:.0f} kB gzipped")
    if skipped:
        log(f"{len(skipped)} laps were not a full grid of points and were left out, e.g. {skipped[:3]}")
    return {"written": len(index), "skipped": skipped, "raw": raw, "gz": gz}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--from-year", type=int, default=2024)
    a = ap.parse_args()
    export(a.db, a.out, a.from_year)


if __name__ == "__main__":
    main()

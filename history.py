"""Pull F1 history (1950 to now) from the Jolpica Ergast-compatible API into Parquet files.

usage: python history.py [--seasons 1950-2026] [--pause 1.5]
Raw responses are cached in data/history_raw/, so a rerun skips what it already has.
A partial run (--seasons) writes to data/lake/history_test/, never over the full tables.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "https://api.jolpi.ca/ergast/f1"
RAW = Path("data/history_raw")
LAKE = Path("data/lake")
HEADERS = {"User-Agent": "f1-pitwall/0.1 (personal portfolio project)"}
PAGE = 100
FIRST_CONSTRUCTOR_TITLE = 1958


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def retry_after(r: requests.Response, attempt: int) -> float:
    try:
        return float(r.headers["Retry-After"])
    except (KeyError, ValueError):
        return 30.0 * attempt


def get(path: str, pause: float) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / (hashlib.sha1(path.encode()).hexdigest()[:16] + ".json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    for attempt in range(1, 8):
        r = requests.get(f"{BASE}/{path}", headers=HEADERS, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            wait = retry_after(r, attempt)
            print(f"  HTTP {r.status_code} on {path}; waiting {wait:.0f}s", flush=True)
            time.sleep(wait)
            continue
        r.raise_for_status()
        data = r.json()
        cache.write_text(json.dumps(data), encoding="utf-8")
        time.sleep(pause)
        return data
    raise RuntimeError(f"gave up on {path}")


def pages(path: str, pause: float):
    """Yield each page's MRData, following limit/offset until the total is reached."""
    offset = 0
    while True:
        sep = "&" if "?" in path else "?"
        mr = get(f"{path}{sep}limit={PAGE}&offset={offset}", pause)["MRData"]
        yield mr
        offset += max(int(mr["limit"]), 1)
        if offset >= int(mr["total"]):
            return


def collect_results(season: str, pause: float) -> list[dict]:
    rows = []
    for mr in pages(f"{season}/results.json", pause):
        for race in mr["RaceTable"]["Races"]:
            for res in race.get("Results", []):
                d, c = res["Driver"], res["Constructor"]
                fl, t = res.get("FastestLap", {}), res.get("Time", {})
                rows.append({
                    "season": int(race["season"]), "round": int(race["round"]),
                    "race_name": race["raceName"], "date": race.get("date"),
                    "circuit_id": race["Circuit"]["circuitId"],
                    "driver_id": d["driverId"], "code": d.get("code"),
                    "driver": f"{d['givenName']} {d['familyName']}",
                    "number": num(res.get("number")),
                    "constructor_id": c["constructorId"], "constructor": c["name"],
                    "grid": num(res.get("grid")), "position": num(res.get("position")),
                    "position_text": res.get("positionText"), "points": num(res.get("points")),
                    "laps": num(res.get("laps")), "status": res.get("status"),
                    "time_ms": num(t.get("millis")),
                    "fastest_rank": num(fl.get("rank")), "fastest_lap": num(fl.get("lap")),
                    "fastest_time": fl.get("Time", {}).get("time"),
                })
    return rows


def collect_driver_standings(season: str, pause: float) -> list[dict]:
    rows = []
    for mr in pages(f"{season}/driverStandings.json", pause):
        for sl in mr["StandingsTable"]["StandingsLists"]:
            for s in sl["DriverStandings"]:
                d, cons = s["Driver"], s.get("Constructors", [])
                rows.append({
                    "season": int(sl["season"]), "round": int(sl["round"]),
                    "position": num(s.get("position")), "position_text": s.get("positionText"),
                    "points": num(s.get("points")), "wins": num(s.get("wins")),
                    "driver_id": d["driverId"], "driver": f"{d['givenName']} {d['familyName']}",
                    "constructor": " / ".join(c["name"] for c in cons),
                })
    return rows


def collect_constructor_standings(season: str, pause: float) -> list[dict]:
    rows = []
    for mr in pages(f"{season}/constructorStandings.json", pause):
        for sl in mr["StandingsTable"]["StandingsLists"]:
            for s in sl["ConstructorStandings"]:
                c = s["Constructor"]
                rows.append({
                    "season": int(sl["season"]), "round": int(sl["round"]),
                    "position": num(s.get("position")), "points": num(s.get("points")),
                    "wins": num(s.get("wins")), "constructor_id": c["constructorId"],
                    "constructor": c["name"], "nationality": c.get("nationality"),
                })
    return rows


def collect_entities(pause: float) -> dict[str, list[dict]]:
    drivers, constructors, circuits = [], [], []
    for mr in pages("drivers.json", pause):
        for d in mr["DriverTable"]["Drivers"]:
            drivers.append({
                "driver_id": d["driverId"], "given_name": d["givenName"],
                "family_name": d["familyName"], "date_of_birth": d.get("dateOfBirth"),
                "nationality": d.get("nationality"), "code": d.get("code"),
                "number": num(d.get("permanentNumber"))})
    for mr in pages("constructors.json", pause):
        for c in mr["ConstructorTable"]["Constructors"]:
            constructors.append({"constructor_id": c["constructorId"], "name": c["name"],
                                 "nationality": c.get("nationality")})
    for mr in pages("circuits.json", pause):
        for c in mr["CircuitTable"]["Circuits"]:
            loc = c.get("Location", {})
            circuits.append({
                "circuit_id": c["circuitId"], "circuit_name": c["circuitName"],
                "locality": loc.get("locality"), "country": loc.get("country"),
                "lat": num(loc.get("lat")), "long": num(loc.get("long"))})
    return {"drivers": drivers, "constructors": constructors, "circuits": circuits}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seasons", default="", help="e.g. 2025 or 2020-2026 (default: all)")
    ap.add_argument("--pause", type=float, default=1.5)
    args = ap.parse_args()

    seasons = [m["season"] for mr in pages("seasons.json", args.pause)
               for m in mr["SeasonTable"]["Seasons"]]
    partial = bool(args.seasons)
    if partial:
        lo, _, hi = args.seasons.partition("-")
        keep = set(range(int(lo), int(hi or lo) + 1))
        seasons = [s for s in seasons if int(s) in keep]

    tables: dict[str, list[dict]] = {"results": [], "driver_standings": [],
                                     "constructor_standings": []}
    for season in seasons:
        tables["results"] += collect_results(season, args.pause)
        tables["driver_standings"] += collect_driver_standings(season, args.pause)
        if int(season) >= FIRST_CONSTRUCTOR_TITLE:
            tables["constructor_standings"] += collect_constructor_standings(season, args.pause)
        print(f"{season}: {len(tables['results'])} results so far", flush=True)
    tables.update(collect_entities(args.pause))

    out = LAKE / ("history_test" if partial else "history")
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        df = pd.DataFrame(rows)
        if df.empty:
            print(f"  skipped {name}: no rows")
            continue
        df.to_parquet(out / f"{name}.parquet", index=False, compression="zstd")
        print(f"  wrote {name}: {len(df)} rows")
    print(f"done -> {out}")


if __name__ == "__main__":
    main()

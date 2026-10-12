import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

MANIFEST = Path("data/lake/_manifest/sessions.jsonl")
MAX_LINES = 10**6 if "--all" in sys.argv else 30

latest = {}
for line in MANIFEST.read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    rnd = r.get("round", r["requested_event"] if isinstance(r["requested_event"], int) else 0)
    latest[(r["year"], rnd, r["session"])] = r  

by_year, mb = defaultdict(Counter), defaultdict(float)
for (year, _, _), r in latest.items():
    by_year[year][r["status"]] += 1
    mb[year] += sum(t.get("bytes", 0) for t in r.get("tables", {}).values()) / 1e6

print("PER YEAR (latest attempt per session)")
for y in sorted(by_year):
    c = by_year[y]
    print(f"  {y}: ok {c['ok']:3d} | partial {c['partial']:2d} | failed {c['failed']:2d} "
          f"| {mb[y]:7.1f} MB")
print(f"  total {sum(mb.values()):.1f} MB")

con = duckdb.connect()


def lap_window(year, rnd, code):
    path = f"data/lake/laps/year={year}/round={rnd:02d}/session={code}/part.parquet"
    if not Path(path).exists():
        return None
    lo, hi = con.sql(
        f"SELECT min(LapStartTime_s), max(Time_s) FROM read_parquet('{path}')").fetchone()
    return (lo, hi) if lo is not None and hi is not None else None


problems = []
for (year, rnd, code), r in sorted(latest.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
    notes = []
    if r["status"] != "ok":
        notes.append(r["status"] + (f" ({str(r['error'])[:50]})" if r.get("error") else ""))
    if "circuit" in r:
        notes.append("no circuit info")
    window = lap_window(year, rnd, code) if r.get("with_telemetry") else None
    for kind in ("car_gaps", "pos_gaps"):
        over = r.get(kind, {}).get("over_limit", {})
        if not over:
            continue
        start = min(v["starts_at_s"] for v in over.values())
        end = max(v["starts_at_s"] + v["gap_s"] for v in over.values())
        where = ""
        if window:
            overlap = start <= window[1] and end >= window[0]
            where = "inside lap window" if overlap else "outside lap window"
        notes.append(f"{kind[:3]} gap {r[kind]['max_gap_s']:.0f}s ({len(over)} drivers) {where}")
    if notes:
        name = str(r.get("event", r["requested_event"]))[:24]
        problems.append(f"  {year} R{rnd:02d} {name:24} {code:3} " + "; ".join(notes))

print(f"\nPROBLEMS ({len(problems)})")
for line in problems[:MAX_LINES]:
    print(line)
if len(problems) > MAX_LINES:
    print(f"  ... and {len(problems) - MAX_LINES} more (python report.py --all)")

import json
from pathlib import Path

import duckdb

MANIFEST = Path("data/lake/_manifest/sessions.jsonl")
LAKE = Path("data/lake")
con = duckdb.connect()

latest, attempts = {}, {}
for line in MANIFEST.read_text(encoding="utf-8").splitlines():
    try:
        r = json.loads(line)
    except json.JSONDecodeError:
        print("UNREADABLE MANIFEST LINE:", line[:80])
        continue
    rnd = r.get("round", r["requested_event"] if isinstance(r["requested_event"], int) else 0)
    key = (r["year"], rnd, r["session"])
    latest[key] = r
    attempts[key] = attempts.get(key, 0) + 1

bad, checked = [], 0
for (year, rnd, code), r in sorted(latest.items()):
    if r["status"] != "ok":
        continue
    for table, info in r.get("tables", {}).items():
        if "bytes" not in info:
            continue
        path = LAKE / table / f"year={year}" / f"round={rnd:02d}" / f"session={code}" / "part.parquet"
        checked += 1
        try:
            n = con.sql(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]
            if n != info["rows"]:
                bad.append((year, rnd, code, table, f"rows {n} != manifest {info['rows']}"))
        except Exception as e:
            bad.append((year, rnd, code, table, type(e).__name__))

dups = [k for k, n in attempts.items() if n > 1]
print(f"checked {checked} files across {len(latest)} sessions")
print(f"sessions logged more than once: {len(dups)} (some, like Singapore, were re-run on purpose)")
for k in dups[:15]:
    print("  ", k, attempts[k], "attempts")
print(f"\nBAD FILES: {len(bad)}")
for b in bad[:30]:
    print("  ", *b)
sessions = sorted({b[:3] for b in bad})
if sessions:
    print("\nre-run these:")
    for year, rnd, code in sessions:
        flag = "" if latest[(year, rnd, code)].get("with_telemetry") else " --no-telemetry"
        print(f"  python ingest.py {year} {rnd} {code} --force{flag}")

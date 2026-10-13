"""Backfill the track_status and session_status tables for sessions ingested before they existed.

usage (from the repository root, after the main ingest has finished):
    python scripts/backfill_track_status.py --dry-run
    python scripts/backfill_track_status.py [--years 2025-2026] [--codes R,Q] [--limit N]

Which sessions: every session that has a laps file in the lake but no track_status file.
What it does: loads laps only (no telemetry, weather or messages: FastF1 loads track status together
with laps), writes track_status and session_status next to the existing tables, never touches other
tables. Sessions that already have a file are skipped, so it is safe to stop and run again.
Log: data/lake/_manifest/backfill.jsonl (sessions.jsonl is not modified).
Do not run it at the same time as batch.py: both share FastF1's rate limit, and the batch may be
half-way through a session.
"""

import argparse
import json
import shutil
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fastf1  # noqa: E402
import ingest  # noqa: E402

TABLES = ("track_status", "session_status")
LOG = ingest.LAKE / "_manifest" / "backfill.jsonl"


def parse_range(text: str) -> range:
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def table_file(table: str, year: int, rnd: int, code: str) -> Path:
    return ingest.LAKE / table / f"year={year}" / f"round={rnd:02d}" / f"session={code}" / "part.parquet"


def lake_sessions():
    for p in sorted((ingest.LAKE / "laps").glob("year=*/round=*/session=*/part.parquet")):
        sess, rnd, yr = p.parent.name, p.parent.parent.name, p.parent.parent.parent.name
        yield int(yr.split("=")[1]), int(rnd.split("=")[1]), sess.split("=")[1]


def backfill(year: int, rnd: int, code: str) -> dict:
    t0 = time.monotonic()
    row = {"year": year, "round": rnd, "session": code, "kind": "backfill",
           "fastf1_version": fastf1.__version__, "at": datetime.now(UTC).isoformat()}
    session = fastf1.get_session(year, rnd, code)
    session.load(laps=True, telemetry=False, weather=False, messages=False)
    name = str(session.event["EventName"])
    tables = {}
    for table in TABLES:
        if table_file(table, year, rnd, code).exists():
            continue
        try:
            df = ingest.seconds(getattr(session, table))
            df.insert(0, "event", name)
            tables[table] = {"rows": len(df),
                             "bytes": ingest.write(df, ingest.part_path(table, year, rnd, code))}
        except Exception as e:
            tables[table] = {"error": f"{type(e).__name__}: {e}"}
    row["tables"] = tables
    row["status"] = "ok" if "bytes" in tables.get("track_status", {}) else "failed"
    row["seconds"] = round(time.monotonic() - t0, 1)
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="", help="e.g. 2025 or 2025-2026 (default: all in the lake)")
    ap.add_argument("--codes", default="", help="only these sessions, e.g. R,Q")
    ap.add_argument("--limit", type=int, default=0, help="stop after N sessions attempted")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pause", type=float, default=3.0, help="seconds between sessions")
    ap.add_argument("--cooldown", type=float, default=15.0, help="minutes to wait after a rate limit")
    ap.add_argument("--max-waits", type=int, default=8, help="give up after this many waits in a row")
    ap.add_argument("--keep-cache", action="store_true")
    args = ap.parse_args()

    years = set(parse_range(args.years)) if args.years else None
    codes = {c.strip() for c in args.codes.split(",") if c.strip()}
    todo, counts = [], Counter()
    for year, rnd, code in lake_sessions():
        if (years and year not in years) or (codes and code not in codes):
            continue
        if table_file("track_status", year, rnd, code).exists():
            counts["has track_status"] += 1
            continue
        counts["todo"] += 1
        todo.append((year, rnd, code))
    by_year = Counter(y for y, _, _ in todo)
    print("plan:", dict(counts), "| todo by year:", dict(sorted(by_year.items())), flush=True)
    if args.dry_run:
        for y, r, c in todo[:10]:
            print(f"  e.g. {y} R{r:02d} {c}")
        return 0

    LOG.parent.mkdir(parents=True, exist_ok=True)
    tally, attempted = Counter(), 0
    for year, rnd, code in todo:
        if args.limit and attempted >= args.limit:
            break
        waits = 0
        while True:
            try:
                row = backfill(year, rnd, code)
                break
            except Exception as e:
                if "RateLimit" in f"{type(e).__name__} {e}":
                    waits += 1
                    if waits > args.max_waits:
                        print(f"rate limited {waits} times in a row: stopping. Run again later.")
                        print("done so far:", dict(tally))
                        return 1
                    print(f"{year} R{rnd:02d} {code}: rate limited, waiting {args.cooldown:g} min "
                          f"({waits}/{args.max_waits})", flush=True)
                    time.sleep(args.cooldown * 60)
                    continue
                row = {"year": year, "round": rnd, "session": code, "kind": "backfill",
                       "status": "failed", "error": f"{type(e).__name__}: {e}",
                       "at": datetime.now(UTC).isoformat()}
                break
        attempted += 1
        tally[row["status"]] += 1
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        rows = row.get("tables", {}).get("track_status", {}).get("rows", "-")
        print(f"[{attempted}/{len(todo)}] {year} R{rnd:02d} {code}: {row['status']} "
              f"track_status rows={rows} in {row.get('seconds', '-')}s", flush=True)
        if row["status"] == "failed" and "error" in row:
            print("   ", row["error"][:200])
        if not args.keep_cache:
            shutil.rmtree(ingest.CACHE, ignore_errors=True)
            ingest.CACHE.mkdir(parents=True, exist_ok=True)
        time.sleep(args.pause)
    print("done:", dict(tally))
    return 0


if __name__ == "__main__":
    sys.exit(main())

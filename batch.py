"""Work through F1 seasons session by session. Resumable; waits out rate limits.

usage: python batch.py --years 2026 [--rounds 5-9] [--codes R,Q,S] [--limit 10]
                       [--dry-run] [--retry-failed] [--pause 3] [--cooldown 15]
"""

import argparse
import json
import time
from collections import Counter

import fastf1
import pandas as pd

import ingest

NAMES = {
    "Practice 1": "FP1", "Practice 2": "FP2", "Practice 3": "FP3",
    "Qualifying": "Q", "Sprint Qualifying": "SQ", "Sprint Shootout": "SS",
    "Sprint": "S", "Race": "R",
}
TELEMETRY_CODES = {"R", "Q", "S", "SQ", "SS"}
FIRST_TELEMETRY_YEAR = 2022


def parse_range(text: str) -> range:
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def manifest_status() -> dict:
    status = {}
    if ingest.MANIFEST.exists():
        for line in ingest.MANIFEST.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            key = (r["year"], r.get("round", r["requested_event"]), r["session"])
            if status.get(key) != "ok":  
                status[key] = r["status"]
    return status


def plan(years, rounds, codes):
    now = pd.Timestamp.now("UTC").tz_localize(None)
    for year in years:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        for _, ev in schedule.iterrows():
            rnd = int(ev["RoundNumber"])
            if rounds and rnd not in rounds:
                continue
            for n in range(1, 6):
                code = NAMES.get(ev.get(f"Session{n}"))
                if code is None or (codes and code not in codes):
                    continue
                when = ev.get(f"Session{n}DateUtc")
                future = False
                if pd.notna(when):
                    when = pd.Timestamp(when)
                    if when.tzinfo is not None:
                        when = when.tz_convert("UTC").tz_localize(None)
                    future = when > now - pd.Timedelta(hours=6)
                yield {"year": year, "round": rnd, "event": str(ev["EventName"]), "code": code,
                       "telemetry": year >= FIRST_TELEMETRY_YEAR and code in TELEMETRY_CODES,
                       "future": future}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--years", default="2026", help="2026 or 2022-2026")
    ap.add_argument("--rounds", default="", help="5 or 5-9")
    ap.add_argument("--codes", default="", help="only these sessions, e.g. R,Q,S")
    ap.add_argument("--limit", type=int, default=0, help="stop after N sessions attempted")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--cooldown", type=float, default=15.0,
                    help="minutes to wait after a rate limit")
    ap.add_argument("--max-waits", type=int, default=8,
                    help="give up after this many waits in a row")
    args = ap.parse_args()

    rounds = set(parse_range(args.rounds)) if args.rounds else set()
    codes = {c.strip() for c in args.codes.split(",") if c.strip()}
    status = manifest_status()
    todo, counts = [], Counter()
    for s in plan(parse_range(args.years), rounds, codes):
        state = status.get((s["year"], s["round"], s["code"]))
        if s["future"]:
            label = "future"
        elif state == "ok":
            label = "done"
        elif state in ("failed", "partial") and not args.retry_failed:
            label = f"{state}-before"
        else:
            label = "todo"
        counts[label] += 1
        if args.dry_run:
            kind = "telemetry" if s["telemetry"] else "laps"
            print(f"{s['year']} R{s['round']:02d} {s['event'][:28]:28} {s['code']:3} {kind:9} {label}")
        if label == "todo":
            todo.append(s)
    print("\nplan:", dict(counts), flush=True)
    if args.dry_run:
        return 0

    attempted, tally = 0, Counter()
    for s in todo:
        if args.limit and attempted >= args.limit:
            break
        waits = 0
        while True:
            row = ingest.ingest(s["year"], s["round"], s["code"], telemetry=s["telemetry"])
            if row["status"] != "ratelimited":
                break
            waits += 1
            if waits > args.max_waits:
                print("\nstill rate limited after waiting; stopping.")
                print("this run:", dict(tally))
                return 2
            print(f"\nrate limited; waiting {args.cooldown:.0f} min "
                  f"({waits}/{args.max_waits}), started {time.strftime('%H:%M')}", flush=True)
            time.sleep(args.cooldown * 60)
        attempted += 1
        tally[row["status"]] += 1
        print(f"progress: {attempted}/{len(todo)} attempted {dict(tally)}", flush=True)
        time.sleep(args.pause)
    print("\nthis run:", dict(tally))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

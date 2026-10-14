"""Run the race-state engine test on every race and sprint that has GPS data, and summarise.

usage (from the repository root):
    ~/.venvs/f1-app/bin/python experiments/engine_sweep.py [--years 2022-2026] [--codes R,S] [--limit N]

For each session it runs experiments/engine_probe.py, reads the exact-order percentages at the two sector
lines (engine against the official order from timing, and the last-lap-end baseline), and writes
logs/engine_sweep_<time>.csv. Reads local files only. Sessions where the probe prints no result are listed,
not hidden.
"""
import argparse
import csv
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

LAKE = Path("data/lake")
PROBE = Path("experiments/engine_probe.py")
ENGINE = re.compile(r"engine \(GPS progress\)\s+n=\s*(\d+)\s+exact\s+([\d.]+)%\s+within 1\s+([\d.]+)%")
BASE = re.compile(r"baseline: last lap-end position\s+n=\s*(\d+)\s+exact\s+([\d.]+)%")


def parse_range(text):
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def sessions(years, codes):
    for p in sorted(LAKE.glob("telemetry_pos/year=*/round=*/session=*/part.parquet")):
        code = p.parent.name.split("=")[1]
        rnd = int(p.parent.parent.name.split("=")[1])
        year = int(p.parent.parent.parent.name.split("=")[1])
        if code in codes and (years is None or year in years):
            yield year, rnd, code


def pct(values, q):
    values = sorted(values)
    if len(values) < 2:
        return values[0] if values else float("nan")
    return statistics.quantiles(values, n=100, method="inclusive")[q - 1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="")
    ap.add_argument("--codes", default="R,S")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=300, help="seconds per session")
    args = ap.parse_args()
    years = set(parse_range(args.years)) if args.years else None
    codes = {c.strip() for c in args.codes.split(",") if c.strip()}
    todo = list(sessions(years, codes))
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} sessions to run", flush=True)

    Path("logs").mkdir(exist_ok=True)
    out = Path("logs") / f"engine_sweep_{datetime.now():%Y%m%d_%H%M}.csv"
    cols = ["year", "round", "session", "status", "n1", "engine1", "within1_1", "base1",
            "n2", "engine2", "within1_2", "base2", "seconds", "note"]
    rows = []
    for i, (y, r, c) in enumerate(todo, 1):
        t0 = time.monotonic()
        row = dict.fromkeys(cols, "")
        row.update(year=y, round=r, session=c)
        try:
            p = subprocess.run([sys.executable, str(PROBE), str(y), str(r), c],
                               capture_output=True, text=True, timeout=args.timeout)
            text = p.stdout + "\n" + p.stderr
            eng, base = ENGINE.findall(text), BASE.findall(text)
            if len(eng) >= 2 and len(base) >= 2:
                row.update(status="ok",
                           n1=eng[0][0], engine1=eng[0][1], within1_1=eng[0][2], base1=base[0][1],
                           n2=eng[1][0], engine2=eng[1][1], within1_2=eng[1][2], base2=base[1][1])
            else:
                row.update(status="no result", note=" | ".join(text.strip().splitlines()[-2:])[:200])
        except subprocess.TimeoutExpired:
            row.update(status="timeout")
        row["seconds"] = round(time.monotonic() - t0, 1)
        rows.append(row)
        print(f"[{i}/{len(todo)}] {y} R{r:02d} {c}: {row['status']}"
              + (f" sector1 {row['engine1']}% sector2 {row['engine2']}%" if row["status"] == "ok" else ""), flush=True)

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if r["status"] == "ok"]
    print(f"\nwrote {out}")
    print(f"sessions with a result: {len(ok)} of {len(rows)}")
    if ok:
        for k, label in (("engine1", "sector 1 line"), ("engine2", "sector 2 line")):
            v = [float(r[k]) for r in ok]
            b = [float(r["base" + k[-1]]) for r in ok]
            beat = sum(1 for e, x in zip(v, b) if e > x)
            print(f"{label}: engine exact % median {statistics.median(v):.1f}, 10th percentile {pct(v, 10):.1f}, "
                  f"worst {min(v):.1f}; baseline median {statistics.median(b):.1f}; "
                  f"engine beats baseline in {beat} of {len(ok)}")
        worst = sorted(ok, key=lambda r: min(float(r["engine1"]), float(r["engine2"])))[:10]
        print("ten weakest sessions (lower of the two lines):")
        for r in worst:
            print(f"  {r['year']} R{int(r['round']):02d} {r['session']}: sector1 {r['engine1']}%  sector2 {r['engine2']}%"
                  f"  (baseline {r['base1']}% / {r['base2']}%)")
    bad = [r for r in rows if r["status"] != "ok"]
    if bad:
        print("sessions without a result:")
        for r in bad:
            print(f"  {r['year']} R{int(r['round']):02d} {r['session']}: {r['status']} {r['note']}")


if __name__ == "__main__":
    main()

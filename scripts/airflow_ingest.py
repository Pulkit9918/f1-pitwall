"""Airflow entry points for the ingest. Run from the repo root in the ingest venv.

  airflow_ingest.py plan --years 2026 [--rounds 5-9] [--codes R,Q] [--limit N] [--retry-failed]
      prints one line:  PLAN_JSON:[...]   (sessions still to ingest, same rules as batch.py)
  airflow_ingest.py run YEAR ROUND CODE [--no-telemetry]
      ingests one session and exits with a code the DAG understands.

exit codes: 0 ok (or partial, with a warning), 1 failed, 75 rate limited (retry later),
            99 already ingested (task is marked skipped)
"""

import argparse
import json
import sys
from pathlib import Path

# scripts/ is on sys.path when run as a script; the repo root (batch.py, ingest.py) is not
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXIT_OK, EXIT_FAILED, EXIT_RATELIMIT, EXIT_SKIP = 0, 1, 75, 99


def cmd_plan(a: argparse.Namespace) -> int:
    import batch  # noqa: PLC0415

    rounds = set(batch.parse_range(a.rounds)) if a.rounds else set()
    codes = {c.strip() for c in a.codes.split(",") if c.strip()}
    status = batch.manifest_status()
    todo = []
    for s in batch.plan(batch.parse_range(a.years), rounds, codes):
        if s["future"]:
            continue
        state = status.get((s["year"], s["round"], s["code"]))
        if state == "ok":
            continue
        if state in ("failed", "partial") and not a.retry_failed:
            continue
        todo.append(s)
    if a.limit:
        todo = todo[: a.limit]
    print("PLAN_JSON:" + json.dumps(todo), flush=True)
    return EXIT_OK


def cmd_run(a: argparse.Namespace) -> int:
    import ingest  # noqa: PLC0415

    telemetry = not a.no_telemetry
    if ingest.already_done(a.year, a.round, a.code, telemetry):
        print(f"{a.year} R{a.round} {a.code}: already ingested", flush=True)
        return EXIT_SKIP
    row = ingest.ingest(a.year, a.round, a.code, telemetry=telemetry)
    status = row.get("status")
    print(f"STATUS: {status}", flush=True)
    if status == "ok":
        return EXIT_OK
    if status == "partial":
        print("WARNING: partial ingest, see the manifest row for what is missing", flush=True)
        return EXIT_OK
    if status == "ratelimited":
        return EXIT_RATELIMIT
    return EXIT_FAILED


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--years", required=True)
    p.add_argument("--rounds", default="")
    p.add_argument("--codes", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--retry-failed", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("year", type=int)
    r.add_argument("round", type=int)
    r.add_argument("code")
    r.add_argument("--no-telemetry", action="store_true")
    a = ap.parse_args()
    return cmd_plan(a) if a.cmd == "plan" else cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())

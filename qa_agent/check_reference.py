"""Run every reference query and show what it returns, so a wrong reference answer is caught before any model is scored.

    python -m qa_agent.check_reference
Look for ERROR (the SQL is wrong), EMPTY (nothing matched, so a literal is probably wrong), and ties in 'limit 1' answers.
"""
import argparse
import re
import sys
from pathlib import Path

from . import db
from .questions import QUESTIONS
from .questions_fresh import FRESH

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(ROOT / "data" / "f1_dbt.duckdb"))
    p.add_argument("--set", choices=["main", "fresh"], default="main")
    a = p.parse_args(argv)
    con = db.connect(a.db)
    bad = 0
    for q in (FRESH if a.set == "fresh" else QUESTIONS):
        if not q.answerable:
            continue
        try:
            cols, rows, _ = db.run(con, q.sql, timeout_s=60, max_rows=10_000)
        except Exception as e:
            print(f"ERROR  {q.id}: {e}")
            bad += 1
            continue
        flag = "EMPTY " if not rows else ("NULL  " if all(v is None for r in rows for v in r) else "ok    ")
        bad += flag != "ok    "
        shown = "; ".join(str(r) for r in rows[:4]) + (f" ... ({len(rows)} rows)" if len(rows) > 4 else "")
        print(f"{flag} {q.id}: {shown}")
        if "limit 1" in q.sql.lower() and "order by" in q.sql.lower():
            top = re.sub(r"limit 1\b", "limit 3", q.sql, flags=re.I)
            try:
                print("         top 3:", "; ".join(str(r) for r in db.run(con, top)[1]))
            except Exception:
                pass
    print(f"\n{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

"""Validate every session already in the lake against contracts.py (read-only). Run from the repo root:
   ~/.venvs/f1-pitwall/bin/python scripts/check_contracts.py [table ...] 2>&1 | tee logs/contract_check.txt
Prints, per table, the files that fail a hard rule and, per soft rule, in how many sessions it is broken and
the worst share of rows. Writes logs/contract_check_<time>.csv with every finding."""
import csv, glob, os, sys, time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import contracts  # noqa: E402

LAKE = Path("data/lake")
PARTITION_COLS = ["year", "round", "session"]
tables = sys.argv[1:] or sorted(contracts.HARD)
Path("logs").mkdir(exist_ok=True)
out = Path(f"logs/contract_check_{time.strftime('%Y%m%d_%H%M%S')}.csv")
rows = []
for t in tables:
    files = sorted(glob.glob(str(LAKE / t / "year=*/round=*/session=*/part.parquet")))
    hard, t0 = [], time.monotonic()
    for i, f in enumerate(files, 1):
        df = pd.read_parquet(f).drop(columns=PARTITION_COLS, errors="ignore")
        try:
            for fnd in contracts.validate(t, df):
                rows.append({"table": t, "file": f, **fnd, "rows": len(df)})
        except contracts.ContractError as e:
            hard.append((f, str(e)))
        if i % 100 == 0:
            print(f"  {t}: {i}/{len(files)} files, {time.monotonic() - t0:.0f}s", flush=True)
    print(f"\n== {t}: {len(files)} files, {len(hard)} hard failures, {time.monotonic() - t0:.0f}s")
    for f, msg in hard[:8]:
        print("   HARD", f.split(str(LAKE) + "/")[-1], msg[:200])
    soft = pd.DataFrame([r for r in rows if r["table"] == t])
    if len(soft):
        g = soft.groupby("rule").agg(sessions=("file", "nunique"), worst_share=("share", "max"),
                                     median_share=("share", "median")).sort_values("sessions", ascending=False)
        print(g.to_string())
    else:
        print("   no soft findings")
with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["table", "file", "rule", "bad_rows", "share", "rows"])
    w.writeheader(); w.writerows(rows)
print("\nwrote", out)

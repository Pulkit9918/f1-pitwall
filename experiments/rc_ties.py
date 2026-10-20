"""How much does the order of same-second race control messages change the safety car / VSC / red flag
periods? Read-only. Runs app/racecontrol.build_periods on every session in four tie orders:
  FILE    file order, stable sort by time
  APP     file order, then pandas default sort by time (what the Race scrubber page does)
  ALPHA   ties broken by message text (what silver_race_control's event_key does today)
  REVERSE file order reversed within ties
Time is seconds since the session's first message, so no telemetry is needed and every session is covered."""
import sys

import duckdb
import numpy as np

sys.path.insert(0, "app")
import racecontrol as rcc  # noqa: E402

LAKE = "data/lake" if len(sys.argv) < 2 else sys.argv[1]
SQL = f"""
    select year, round, session, Time, Category, Message, Flag, Scope, Sector, Lap,
           file_row_number as frn
    from read_parquet('{LAKE}/race_control/*/*/*/part.parquet', hive_partitioning = true,
                      union_by_name = true, file_row_number = true)
    where Message is not null and Time is not null
"""
d = duckdb.connect().sql(SQL).df()


def periods(g):
    tmax = float(g["t"].max()) + 1e5
    out = rcc.build_periods(g.reset_index(drop=True), np.array([0.0, tmax]), np.array([0.0, 1.0]), tmax)
    return [(p["kind"], round(p["t0"], 3), round(p["t1"], 3)) for p in out]


n = ties = with_periods = 0
diff = {"APP": [], "ALPHA": [], "REVERSE": []}
for key, g in d.groupby(["year", "round", "session"]):
    g = g.copy()
    g["t"] = (g["Time"] - g["Time"].min()).dt.total_seconds()
    n += 1
    ties += int(g["t"].duplicated().any())
    file = g.sort_values("frn", kind="stable")
    ref = periods(file.sort_values("t", kind="stable"))
    with_periods += bool(ref)
    for name, frame in [("APP", file.sort_values("t")),
                        ("ALPHA", g.sort_values(["t", "Message"], kind="stable")),
                        ("REVERSE", file.iloc[::-1].sort_values("t", kind="stable"))]:
        got = periods(frame)
        if got != ref:
            diff[name].append((key, sorted(set(ref) - set(got)), sorted(set(got) - set(ref))))

print(f"{n} sessions; {ties} with same-second messages; {with_periods} with at least one period (file order)")
for name, rows in diff.items():
    print(f"\n{name}: periods differ from FILE order in {len(rows)} sessions")
    for key, only_file, only_other in rows[:8]:
        print(f"  {key}\n    only in FILE:  {only_file}\n    only in {name}: {only_other}")

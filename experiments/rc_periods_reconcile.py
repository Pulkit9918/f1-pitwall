"""Reconcile gold.fct_race_control_period with app/racecontrol.build_periods. Read-only.
Python side: the Race scrubber's own recipe (session second zero from the first position sample, messages in
file order). SQL side: the dbt table, session-second columns. Periods still open at the end are compared on
their start only (the app closes them at the end of the replay, which SQL does not know).
Then an informational check of message-based periods against the separate track status feed."""
import sys

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, "app")
import racecontrol as rcc  # noqa: E402

LAKE = "data/lake" if len(sys.argv) < 2 else sys.argv[1]
DB = "data/f1_dbt.duckdb" if len(sys.argv) < 3 else sys.argv[2]
TOL = 1e-3
con = duckdb.connect(DB, read_only=True)
zero = con.sql(f"""
    select cast(year as integer) as year, cast(round as integer) as round, session,
           epoch(arg_min(date_utc, session_time_s)) - cast(min(session_time_s) as double) as zero
    from read_parquet('{LAKE}/telemetry_pos/*/*/*/part.parquet', hive_partitioning = true, union_by_name = true)
    group by 1, 2, 3""").df().set_index(["year", "round", "session"])["zero"]
rc = con.sql(f"""
    select cast(year as integer) as year, cast(round as integer) as round, session,
           Time, Message, Flag, file_row_number as frn
    from read_parquet('{LAKE}/race_control/*/*/*/part.parquet', hive_partitioning = true,
                      union_by_name = true, file_row_number = true)
    where Message is not null and Time is not null""").df()
sql = con.sql("""select year, round, session_code as session, period_no, kind, start_s, end_s, is_open
                 from gold.fct_race_control_period where has_session_clock order by 1, 2, 3, 4""").df()
sql_by = {k: g for k, g in sql.groupby(["year", "round", "session"])}

BIG = 1e7
compared = with_periods = py_total = sql_total = 0
bad = []
for key, g in rc.groupby(["year", "round", "session"]):
    if key not in zero.index:
        continue
    compared += 1
    g = g.sort_values("frn", kind="stable").copy()
    g["t"] = (g["Time"] - pd.Timestamp(0)).dt.total_seconds() - zero[key]
    g = g.sort_values("t", kind="stable").reset_index(drop=True)
    py = [(p["kind"], p["t0"], None if p["t1"] == BIG else p["t1"])
          for p in rcc.build_periods(g, np.array([0.0, BIG]), np.array([0.0, 1.0]), BIG)]
    s = sql_by.get(key)
    got = [] if s is None else [(r.kind, r.start_s, None if r.is_open else r.end_s) for r in s.itertuples()]
    py_total += len(py)
    sql_total += len(got)
    with_periods += bool(py)
    ok = len(py) == len(got) and all(
        a[0] == b[0] and abs(a[1] - b[1]) < TOL and (a[2] is None) == (b[2] is None)
        and (a[2] is None or abs(a[2] - b[2]) < TOL)
        for a, b in zip(py, got))
    if not ok:
        bad.append((key, py, got))

print(f"sessions compared (with a clock and race control messages): {compared}; with at least one period: {with_periods}")
print(f"periods: python {py_total}, sql {sql_total}; sessions that differ: {len(bad)}")
for key, py, got in bad[:10]:
    print(f"  {key}\n    python: {py}\n    sql:    {got}")
extra = set(sql_by) - set(zero.index)
print(f"sql sessions with a clock but no position-sample clock (should be none): {len(extra)}")

print("\nMessage-based periods against the track status feed (start, session seconds; informational):")
print(con.sql("""
with d as (
    select p.session_key, p.period_no, p.kind, min(abs(t.start_s - p.start_s)) as diff
    from gold.fct_race_control_period p
    left join gold.fct_track_status_period t
      on t.session_key = p.session_key
     and t.meaning = case p.kind when 'SC' then 'SAFETY_CAR' when 'VSC' then 'VSC' else 'RED' end
    where p.has_session_clock
    group by 1, 2, 3)
select kind, count(*) as periods,
       sum(case when diff is null then 1 else 0 end) as no_status_change,
       sum(case when diff <= 5 then 1 else 0 end) as within_5s,
       sum(case when diff > 30 then 1 else 0 end) as over_30s,
       median(diff) as median_diff_s
from d group by 1 order by 1""").df().to_string(index=False))

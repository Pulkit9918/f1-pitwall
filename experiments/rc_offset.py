"""Can session second zero be taken from the laps table (LapStartDate - LapStartTime_s) instead of from the
first position sample (what the Race scrubber does)? Read-only. Compares the two over every session that has both."""
import sys

import duckdb

LAKE = "data/lake" if len(sys.argv) < 2 else sys.argv[1]
con = duckdb.connect()
con.sql(f"""
create view lapoff as
select cast(year as integer) as year, cast(round as integer) as round, session,
       median(epoch(cast(LapStartDate as timestamp)) - LapStartTime_s) as off_laps,
       quantile_cont(epoch(cast(LapStartDate as timestamp)) - LapStartTime_s, 0.9)
         - quantile_cont(epoch(cast(LapStartDate as timestamp)) - LapStartTime_s, 0.1) as lap_spread,
       count(*) as n_laps
from read_parquet('{LAKE}/laps/*/*/*/part.parquet', hive_partitioning = true, union_by_name = true)
where LapStartDate is not null and LapStartTime_s is not null
group by 1, 2, 3
""")
con.sql(f"""
create view telo as
select cast(year as integer) as year, cast(round as integer) as round, session,
       epoch(arg_min(date_utc, session_time_s)) - cast(min(session_time_s) as double) as off_tel
from read_parquet('{LAKE}/telemetry_pos/*/*/*/part.parquet', hive_partitioning = true, union_by_name = true)
group by 1, 2, 3
""")
con.sql(f"""
create view rcs as
select distinct cast(year as integer) as year, cast(round as integer) as round, session
from read_parquet('{LAKE}/race_control/*/*/*/part.parquet', hive_partitioning = true, union_by_name = true)
""")
print("Race control sessions by whether each offset source exists:")
print(con.sql("""
select (l.year is not null) as has_laps_offset, (t.year is not null) as has_telemetry_offset, count(*) as sessions
from rcs r left join lapoff l using (year, round, session) left join telo t using (year, round, session)
group by 1, 2 order by 1, 2
""").df().to_string(index=False))
print("\nLaps offset against telemetry offset, sessions with both (seconds):")
print(con.sql("""
with j as (select l.year, l.round, l.session, l.off_laps, t.off_tel, abs(l.off_laps - t.off_tel) as d, l.lap_spread
           from lapoff l join telo t using (year, round, session))
select count(*) as sessions, round(median(d), 3) as median_abs_diff, round(quantile_cont(d, 0.9), 3) as p90,
       round(quantile_cont(d, 0.99), 3) as p99, round(max(d), 3) as max_diff,
       sum(case when d > 1 then 1 else 0 end) as over_1s, sum(case when d > 5 then 1 else 0 end) as over_5s,
       round(median(lap_spread), 3) as median_within_session_spread
from j
""").df().to_string(index=False))
print("\nLargest differences:")
print(con.sql("""
select l.year, l.round, l.session, round(l.off_laps - t.off_tel, 3) as laps_minus_tel_s, round(l.lap_spread, 3) as lap_spread, l.n_laps
from lapoff l join telo t using (year, round, session)
order by abs(l.off_laps - t.off_tel) desc limit 10
""").df().to_string(index=False))
print("\nLaps offset spread within a session (p90 - p10 of the per-lap offset), all sessions:")
print(con.sql("select count(*) as sessions, round(median(lap_spread), 3) as median, round(quantile_cont(lap_spread, 0.9), 3) as p90, "
              "round(max(lap_spread), 3) as max from lapoff").df().to_string(index=False))

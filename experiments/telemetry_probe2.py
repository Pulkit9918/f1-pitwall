"""Telemetry probe, part 2. Read-only. Names the sessions behind the oddities in telemetry_probe.py:
which sessions have no telemetry, which have extra drivers, which are short or thin."""
import sys

import duckdb

LAKE = "data/lake" if len(sys.argv) < 2 else sys.argv[1]
con = duckdb.connect()


def src(name):
    return f"read_parquet('{LAKE}/{name}/*/*/*/part.parquet', hive_partitioning = true, union_by_name = true)"


def show(title, sql):
    print(f"\n{title}")
    df = con.sql(sql).df()
    print(df.to_string(index=False) if len(df) else "  (none)")


show("A) Sessions by code, with and without telemetry (laps from 2022 on):", f"""
    with l as (select distinct cast(year as integer) as year, cast(round as integer) as round, session from {src('laps')} where year >= 2022),
         t as (select distinct cast(year as integer) as year, cast(round as integer) as round, session from {src('telemetry_car')})
    select l.session, count(*) as sessions, sum(case when t.year is null then 0 else 1 end) as with_telemetry,
           sum(case when t.year is null then 1 else 0 end) as without_telemetry
    from l left join t using (year, round, session) group by 1 order by 2 desc""")

show("B) Telemetry drivers that have no laps in the same session (car table):", f"""
    with c as (select cast(year as integer) as year, cast(round as integer) as round, session, driver_number,
                      count(*) as rows, round(min(session_time_s)) as first_s, round(max(session_time_s)) as last_s
               from {src('telemetry_car')} group by 1, 2, 3, 4),
         l as (select distinct cast(year as integer) as year, cast(round as integer) as round, session,
                      try_cast(DriverNumber as integer) as driver_number from {src('laps')} where year >= 2022)
    select c.year, c.round, c.session, c.driver_number, c.rows, c.first_s, c.last_s
    from c anti join l using (year, round, session, driver_number)
    order by c.year, c.round, c.session, c.driver_number limit 40""")

show("C) Position telemetry: shortest against the last lap, and thinnest:", f"""
    with p as (select cast(year as integer) as year, cast(round as integer) as round, session,
                      count(*) as rows, count(distinct driver_number) as drivers,
                      min(session_time_s) as t_min, max(session_time_s) as t_max
               from {src('telemetry_pos')} group by 1, 2, 3),
         l as (select cast(year as integer) as year, cast(round as integer) as round, session,
                      min(LapStartTime_s) as first_start, max(Time_s) as last_end from {src('laps')} where year >= 2022 group by 1, 2, 3)
    select p.year, p.round, p.session, p.drivers, p.rows,
           round(p.t_max - l.last_end) as end_minus_last_lap_s, round(p.t_min - l.first_start) as start_minus_first_lap_s,
           round(p.rows / (p.drivers * (p.t_max - p.t_min)), 2) as rate_hz
    from p join l using (year, round, session)
    order by least(p.t_max - l.last_end, 1e9) limit 8""")

show("D) Sessions whose telemetry starts after the first lap has begun (car or position):", f"""
    with t as (select cast(year as integer) as year, cast(round as integer) as round, session, min(session_time_s) as t_min
               from {src('telemetry_car')} group by 1, 2, 3),
         p as (select cast(year as integer) as year, cast(round as integer) as round, session, min(session_time_s) as t_min
               from {src('telemetry_pos')} group by 1, 2, 3),
         l as (select cast(year as integer) as year, cast(round as integer) as round, session, min(LapStartTime_s) as first_start
               from {src('laps')} where year >= 2022 group by 1, 2, 3)
    select t.year, t.round, t.session, round(t.t_min - l.first_start, 1) as car_start_minus_first_lap_s,
           round(p.t_min - l.first_start, 1) as pos_start_minus_first_lap_s
    from t join p using (year, round, session) join l using (year, round, session)
    where t.t_min > l.first_start or p.t_min > l.first_start order by 4 desc""")

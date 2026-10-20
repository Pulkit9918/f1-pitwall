"""Telemetry probe, part 3. Read-only. For telemetry drivers with no laps in a session (telemetry_probe2.py, B),
what does the results table say about them?"""
import sys

import duckdb

LAKE = "data/lake" if len(sys.argv) < 2 else sys.argv[1]
con = duckdb.connect()


def src(name):
    return f"read_parquet('{LAKE}/{name}/*/*/*/part.parquet', hive_partitioning = true, union_by_name = true)"


cols = {r[0] for r in con.sql(f"describe select * from {src('results')}").fetchall()}
if "DriverNumber" not in cols:
    raise SystemExit(f"results has no DriverNumber column; columns are {sorted(cols)}")
want = [c for c in ["Abbreviation", "Status", "ClassifiedPosition", "GridPosition", "Laps"] if c in cols]
sel = "".join(f", r.{c}" for c in want)
inner = "".join(f", {c}" for c in want)
sql = f"""
    with c as (select cast(year as integer) as year, cast(round as integer) as round, session, driver_number, count(*) as rows
               from {src('telemetry_car')} group by 1, 2, 3, 4),
         l as (select distinct cast(year as integer) as year, cast(round as integer) as round, session,
                      try_cast(DriverNumber as integer) as driver_number from {src('laps')} where year >= 2022),
         x as (select c.* from c anti join l using (year, round, session, driver_number)),
         r as (select cast(year as integer) as year, cast(round as integer) as round, session,
                      try_cast(DriverNumber as integer) as driver_number{inner} from {src('results')})
    select x.year, x.round, x.session, x.driver_number, x.rows{sel}
    from x left join r using (year, round, session, driver_number)
    order by x.year, x.round, x.session, x.driver_number"""
df = con.sql(sql).df()
print(df.to_string(index=False))
if "Status" in df.columns:
    print("\nStatus of the telemetry-only drivers:")
    print(df.groupby("Status", dropna=False).size().rename("drivers").reset_index().to_string(index=False))

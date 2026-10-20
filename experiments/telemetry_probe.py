"""Telemetry coverage probe. Read-only. What the two telemetry tables hold per session, how that lines up with
the laps table (2022 onward), and how long a session-level summary of the 1.6 GB takes."""
import sys
import time

import duckdb
import numpy as np

LAKE = "data/lake" if len(sys.argv) < 2 else sys.argv[1]
con = duckdb.connect()


def timed(label, sql):
    t0 = time.time()
    df = con.sql(sql).df()
    print(f"{label}: {len(df)} rows in {time.time() - t0:.1f}s")
    return df


def src(name):
    return f"read_parquet('{LAKE}/{name}/*/*/*/part.parquet', hive_partitioning = true, union_by_name = true)"


car = timed("telemetry_car per session", f"""
    select cast(year as integer) as year, cast(round as integer) as round, session,
           count(*) as rows, count(distinct driver_number) as drivers,
           min(session_time_s) as t_min, max(session_time_s) as t_max,
           sum(case when speed is null then 1 else 0 end) as null_speed
    from {src('telemetry_car')} group by 1, 2, 3""")
pos = timed("telemetry_pos per session", f"""
    select cast(year as integer) as year, cast(round as integer) as round, session,
           count(*) as rows, count(distinct driver_number) as drivers,
           min(session_time_s) as t_min, max(session_time_s) as t_max,
           sum(case when x is null or y is null then 1 else 0 end) as null_xy
    from {src('telemetry_pos')} group by 1, 2, 3""")
status = timed("telemetry_pos status values", f"select status, count(*) as rows from {src('telemetry_pos')} group by 1 order by 2 desc")
print(status.to_string(index=False))
laps = timed("laps per session (2022 onward)", f"""
    select cast(year as integer) as year, cast(round as integer) as round, session,
           count(distinct Driver) as drivers, min(LapStartTime_s) as first_start, max(Time_s) as last_end
    from {src('laps')} where year >= 2022 group by 1, 2, 3""")

key = ["year", "round", "session"]


def tag(df, suffix):
    return df.rename(columns={c: f"{c}_{suffix}" for c in df.columns if c not in key})


m = tag(laps, "laps").merge(tag(car, "car"), on=key, how="outer").merge(tag(pos, "pos"), on=key, how="outer")
m["has_laps"] = m["drivers_laps"].notna()
m["has_car"] = m["drivers_car"].notna()
m["has_pos"] = m["drivers_pos"].notna()
print("\nSessions by where they exist (laps from 2022 on):")
print(m.groupby(["has_laps", "has_car", "has_pos"]).size().rename("sessions").reset_index().to_string(index=False))
odd = m[(m.has_laps != m.has_car) | (m.has_car != m.has_pos)]
print(odd[key + ["has_laps", "has_car", "has_pos"]].head(12).to_string(index=False) if len(odd) else "  (every session that has one has all three)")

b = m[m.has_laps & m.has_car & m.has_pos].copy()
print(f"\nSessions with laps, car and position telemetry: {len(b)}")
print("Drivers in telemetry minus drivers in laps (car, pos):")
b["d_car"] = b.drivers_car - b.drivers_laps
b["d_pos"] = b.drivers_pos - b.drivers_laps
print(b.groupby(["d_car", "d_pos"]).size().rename("sessions").reset_index().to_string(index=False))
print("\nTelemetry end minus last lap end, seconds (car, pos):")
for c, name in [("t_max_car", "car"), ("t_max_pos", "pos")]:
    d = b[c] - b["last_end_laps"]
    print(f"  {name}: min {d.min():.1f}  p10 {d.quantile(.1):.1f}  median {d.median():.1f}  p90 {d.quantile(.9):.1f}  max {d.max():.1f}")
print("Telemetry start minus first lap start, seconds (car, pos):")
for c, name in [("t_min_car", "car"), ("t_min_pos", "pos")]:
    d = b[c] - b["first_start_laps"]
    print(f"  {name}: min {d.min():.1f}  p10 {d.quantile(.1):.1f}  median {d.median():.1f}  p90 {d.quantile(.9):.1f}  max {d.max():.1f}")
print("\nRows per driver per second over the telemetry span (sample rate, Hz):")
for t, name in [("car", "car"), ("pos", "pos")]:
    r = b[f"rows_{t}"] / (b[f"drivers_{t}"] * (b[f"t_max_{t}"] - b[f"t_min_{t}"]))
    print(f"  {name}: min {r.min():.2f}  p10 {r.quantile(.1):.2f}  median {r.median():.2f}  p90 {r.quantile(.9):.2f}  max {r.max():.2f}")
b["rate_car"] = b.rows_car / (b.drivers_car * (b.t_max_car - b.t_min_car))
print("\nSessions with the lowest car sample rate:")
print(b.sort_values("rate_car")[key + ["drivers_car", "rows_car", "rate_car"]].head(5).round(2).to_string(index=False))
print(f"\nShare of car rows with a null speed: {b.null_speed_car.sum() / b.rows_car.sum():.4%}; "
      f"position rows with a null x or y: {b.null_xy_pos.sum() / b.rows_pos.sum():.4%}")
print(f"Total rows: car {int(b.rows_car.sum()):,}, position {int(b.rows_pos.sum()):,}")

import json
from pathlib import Path

import duckdb

con = duckdb.connect()
SRC = "hive_partitioning = true, union_by_name = true"


def show(title: str, sql: str) -> None:
    print(f"\n{title}")
    print(con.sql(sql).df().to_string(index=False))


print("MANIFEST")
lines = Path("data/lake/_manifest/sessions.jsonl").read_text(encoding="utf-8").splitlines()
for r in (json.loads(x) for x in lines):
    mb = sum(t.get("bytes", 0) for t in r.get("tables", {}).values()) / 1e6
    print(f"  {r['year']} {r.get('event', r['requested_event'])} {r['session']}: "
          f"{r['status']}, {mb:.2f} MB, telemetry={r.get('with_telemetry')}")
    if "car_ranges" in r:
        print(f"      car value ranges: {r['car_ranges']}")

show("LAPS", f"""
    SELECT year, round, event, session, count(*) AS laps, count(DISTINCT Driver) AS drivers,
           round(min(LapTime_s), 3) AS fastest_lap_s
    FROM read_parquet('data/lake/laps/*/*/*/part.parquet', {SRC})
    GROUP BY ALL ORDER BY year, round, session""")
show("CAR TELEMETRY", f"""
    SELECT year, round, session, count(*) AS rows, count(DISTINCT driver_number) AS drivers,
           max(speed) AS max_speed, max(throttle) AS max_throttle
    FROM read_parquet('data/lake/telemetry_car/*/*/*/part.parquet', {SRC})
    GROUP BY ALL ORDER BY year, round, session""")
show("WEATHER", f"""
    SELECT year, round, session, round(avg(AirTemp), 1) AS air_c, round(avg(TrackTemp), 1) AS track_c,
           round(avg(Humidity), 0) AS humidity, bool_or(Rainfall) AS any_rain
    FROM read_parquet('data/lake/weather/*/*/*/part.parquet', {SRC})
    GROUP BY ALL ORDER BY year, round, session""")

show("RAIN SHARE OF WEATHER SAMPLES", f"""
    SELECT year, round, session,
           round(100.0 * avg(CASE WHEN Rainfall THEN 1 ELSE 0 END), 1) AS rain_pct
    FROM read_parquet('data/lake/weather/*/*/*/part.parquet', {SRC})
    GROUP BY ALL ORDER BY year, round, session""")
show("TYRE COMPOUNDS", f"""
    SELECT year, round, session, Compound, count(*) AS laps
    FROM read_parquet('data/lake/laps/*/*/*/part.parquet', {SRC})
    GROUP BY ALL ORDER BY year, round, session, laps DESC""")

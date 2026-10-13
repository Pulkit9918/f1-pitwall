import json
from pathlib import Path

import duckdb

con = duckdb.connect()
SRC = "hive_partitioning = true, union_by_name = true"

print("THROTTLE ABOVE 100: share of samples per session")
print(con.sql(f"""
    SELECT year, round, session,
           round(100.0 * avg(CASE WHEN throttle > 100 THEN 1 ELSE 0 END), 1) AS pct_over_100,
           max(throttle) AS max_throttle
    FROM read_parquet('data/lake/telemetry_car/*/*/*/part.parquet', {SRC})
    GROUP BY ALL ORDER BY year, round, session""").df().to_string(index=False))

print("\nTHROTTLE VALUES 99 and above, 2026 Australia qualifying")
print(con.sql("""
    SELECT throttle, count(*) AS n
    FROM read_parquet('data/lake/telemetry_car/year=2026/round=01/session=Q/part.parquet')
    WHERE throttle >= 99 GROUP BY 1 ORDER BY 1""").df().to_string(index=False))

print("\nSINGAPORE 2025 RACE: position dropout vs the start of lap 1")
rows = [json.loads(x) for x in Path("data/lake/_manifest/sessions.jsonl").read_text().splitlines()]
row = [r for r in rows if r["year"] == 2025 and r.get("round") == 18 and r["session"] == "R"][-1]
over = row["pos_gaps"]["over_limit"]
starts = [v["starts_at_s"] for v in over.values()]
gaps = [v["gap_s"] for v in over.values()]
print(f"drivers with a gap: {len(over)}; gaps start at {min(starts)}-{max(starts)} s; "
      f"lengths {min(gaps)}-{max(gaps)} s")
print(con.sql("""
    SELECT min(LapStartTime_s) AS first_lap_start_s
    FROM read_parquet('data/lake/laps/year=2025/round=18/session=R/part.parquet')""").df().to_string(index=False))

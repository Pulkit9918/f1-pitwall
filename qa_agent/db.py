"""Opening the database for the agent and running one query safely."""
import threading
from pathlib import Path

import duckdb

from . import sqlguard

# Tables the agent may see. The per-sample telemetry tables are views over the whole lake, far too large to query here.
EXCLUDED = {"fct_lap_sample", "fct_lap_sample_total", "fct_lap_position", "fct_lap_trace"}
MAX_ROWS = 200


def connect(db_path: str | Path, catalog_schema: str = "gold"):
    con = duckdb.connect(str(db_path), read_only=True, config={"enable_external_access": False})
    cats = [r[0] for r in con.execute("select database_name from duckdb_databases() where not internal").fetchall()]
    con.execute(f"use {cats[0]}.{catalog_schema}")
    return con


def tables(con) -> list[str]:
    rows = con.execute("select table_name from information_schema.tables where table_schema = 'gold' order by 1").fetchall()
    return [r[0] for r in rows if r[0] not in EXCLUDED]


class QueryFailed(Exception):
    pass


def run(con, sql: str, timeout_s: float = 20.0, max_rows: int = MAX_ROWS):
    """(columns, rows, truncated). Raises sqlguard.Rejected or QueryFailed."""
    safe = sqlguard.check(sql)
    timer = threading.Timer(timeout_s, con.interrupt)
    timer.start()
    try:
        cur = con.execute(safe)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    except duckdb.Error as e:
        raise QueryFailed(str(e).splitlines()[0]) from e
    finally:
        timer.cancel()
    truncated = len(rows) > max_rows
    return cols, [tuple(r) for r in rows[:max_rows]], truncated

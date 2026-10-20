"""Read-only HTTP API over the gold tables.

Run from the repository root:  uvicorn api.main:app --port 8000   (docs at /docs)
The database is data/f1_dbt.duckdb unless F1_API_DB points elsewhere. It is opened read-only on every request, so
a running dbt build (which needs the write lock) makes the API answer 503 until the build ends.
Every value from the URL goes in as a query parameter; column and table names in the SQL are fixed in this file."""
import math
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import duckdb
from fastapi import FastAPI, HTTPException, Query

MAX_LIMIT = 5000
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description=f"Rows to return, 1 to {MAX_LIMIT}.")]

app = FastAPI(
    title="f1-pitwall API",
    version="0.1.0",
    description=(
        "Read-only access to the gold tables of the f1-pitwall dbt project. The figures are measured from timing "
        "data and checked for internal consistency, not against an outside source; the project README lists the "
        "known data gaps. Session keys look like 2025-R07-R (see /sessions)."
    ),
)


def db_path() -> str:
    default = Path(__file__).resolve().parents[1] / "data" / "f1_dbt.duckdb"
    return os.environ.get("F1_API_DB", str(default))


def _clean(v):
    """Make a DuckDB value JSON-safe: NaN and infinity become null, dates become ISO text."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def query(sql: str, params: list | None = None) -> list[dict]:
    path = db_path()
    if not Path(path).exists():
        raise HTTPException(503, "The gold database does not exist yet; build the dbt project first.")
    con = duckdb.connect()
    try:
        # attached under a fixed alias, so the SQL below does not depend on the file's name
        con.execute("attach '" + path.replace("'", "''") + "' as f1 (read_only)")
    except duckdb.Error as e:
        con.close()
        raise HTTPException(503, "The gold database is busy (a dbt build may be running); try again shortly.") from e
    try:
        cur = con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [{c: _clean(v) for c, v in zip(cols, row)} for row in cur.fetchall()]
    finally:
        con.close()


def where(filters: list[tuple[str, object]]) -> tuple[str, list]:
    """A WHERE clause from fixed column names and the values that were given (None means no filter)."""
    clauses = [(f"{col} = ?", val) for col, val in filters if val is not None]
    if not clauses:
        return "", []
    return " where " + " and ".join(c for c, _ in clauses), [v for _, v in clauses]


def require_session(session_key: str) -> dict:
    rows = query("select * from f1.gold.dim_session where session_key = ?", [session_key])
    if not rows:
        raise HTTPException(404, f"No session with key {session_key!r}.")
    return rows[0]


@app.get("/health", tags=["service"])
def health():
    """Whether the gold database can be read, and how many sessions it holds."""
    return {"status": "ok", "sessions": query("select count(*) as n from f1.gold.dim_session")[0]["n"]}


@app.get("/sessions", tags=["sessions"])
def sessions(
    year: int | None = None,
    round_: Annotated[int | None, Query(alias="round")] = None,
    session_code: str | None = Query(None, description="R race, Q qualifying, S sprint, SQ sprint qualifying, FP1-FP3 practice."),
    limit: Limit = 500,
):
    """Sessions in the lake, newest last."""
    w, p = where([("year", year), ("round", round_), ("session_code", session_code)])
    return query(f"select * from f1.gold.dim_session{w} order by year, round, session_code limit ?", p + [limit])


@app.get("/sessions/{session_key}", tags=["sessions"])
def session(session_key: str):
    """One session."""
    return require_session(session_key)


@app.get("/sessions/{session_key}/laps", tags=["sessions"])
def laps(session_key: str, driver_code: str | None = None, clean_only: bool = False, limit: Limit = 2000):
    """Laps of a session (fct_lap), optionally for one driver or only clean laps."""
    require_session(session_key)
    w, p = where([("session_key", session_key), ("driver_code", driver_code)])
    if clean_only:
        w += " and is_clean_lap"
    return query(f"select * from f1.gold.fct_lap{w} order by driver_code, lap_number limit ?", p + [limit])


@app.get("/sessions/{session_key}/stints", tags=["sessions"])
def stints(session_key: str, driver_code: str | None = None, limit: Limit = 2000):
    """Tyre stints of a session (fct_stint)."""
    require_session(session_key)
    w, p = where([("session_key", session_key), ("driver_code", driver_code)])
    return query(f"select * from f1.gold.fct_stint{w} order by driver_code, stint limit ?", p + [limit])


@app.get("/sessions/{session_key}/stint-degradation", tags=["sessions"])
def stint_degradation(session_key: str, driver_code: str | None = None, limit: Limit = 2000):
    """Tyre degradation per stint (fct_stint_degradation); a single stint is noisy, about 0.02 s per lap."""
    require_session(session_key)
    w, p = where([("session_key", session_key), ("driver_code", driver_code)])
    return query(f"select * from f1.gold.fct_stint_degradation{w} order by driver_code, stint limit ?", p + [limit])


@app.get("/sessions/{session_key}/pit-stops", tags=["sessions"])
def pit_stops(session_key: str, driver_code: str | None = None, limit: Limit = 2000):
    """Pit stops of a session (fct_pit_stop)."""
    require_session(session_key)
    w, p = where([("session_key", session_key), ("driver_code", driver_code)])
    return query(f"select * from f1.gold.fct_pit_stop{w} order by in_lap, driver_code limit ?", p + [limit])


@app.get("/sessions/{session_key}/race-control-periods", tags=["sessions"])
def race_control_periods(session_key: str, limit: Limit = 500):
    """Safety car, VSC and red flag periods of a session, read from the race control messages."""
    require_session(session_key)
    w, p = where([("session_key", session_key)])
    return query(f"select * from f1.gold.fct_race_control_period{w} order by period_no limit ?", p + [limit])


@app.get("/circuits/pit-loss", tags=["circuits"])
def circuit_pit_loss(reliable_only: bool = True, limit: Limit = 500):
    """Green-flag pit loss per circuit (fct_circuit_pit_loss). Unreliable circuits have too few stops or sessions."""
    w = " where is_reliable" if reliable_only else ""
    return query(f"select * from f1.gold.fct_circuit_pit_loss{w} order by median_pit_loss_s desc limit ?", [limit])


@app.get("/circuits/degradation", tags=["circuits"])
def circuit_degradation(compound: str | None = None, reliable_only: bool = True, limit: Limit = 500):
    """Tyre degradation per circuit layout and compound (fct_circuit_degradation)."""
    w, p = where([("compound", compound)])
    if reliable_only:
        w += (" and " if w else " where ") + "is_reliable"
    return query(f"select * from f1.gold.fct_circuit_degradation{w} order by circuit_name, compound limit ?", p + [limit])

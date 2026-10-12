"""Ingest one F1 session into compact, partitioned Parquet files.

usage: python ingest.py YEAR "Event name or round number" CODE [--force] [--keep-cache] [--no-telemetry]
CODE is a FastF1 session identifier: R, Q, S, SQ, SS, FP1, FP2, FP3
status: ok (everything written), partial (something missing), failed (no laps)
"""

import json
import logging
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd
import pyarrow as pa

CACHE = Path("data/cache")
LAKE = Path("data/lake")
MANIFEST = LAKE / "_manifest" / "sessions.jsonl"
GAP_LIMIT_S = 10.0  # my heuristic: a telemetry gap longer than this counts as incomplete

CACHE.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE))
if hasattr(fastf1, "set_log_level"):
    fastf1.set_log_level("WARNING")


class Collect(logging.Handler):
    """Collect FastF1 warnings so data-quality problems end up in the manifest."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def part_path(table: str, year: int, rnd: int, code: str) -> Path:
    d = LAKE / table / f"year={year}" / f"round={rnd:02d}" / f"session={code}"
    d.mkdir(parents=True, exist_ok=True)
    return d / "part.parquet"


def write(df: pd.DataFrame, path: Path) -> int:
    try:
        df.to_parquet(path, compression="zstd", compression_level=9, index=False)
    except (pa.ArrowInvalid, pa.ArrowTypeError):
        objs = df.select_dtypes(include="object").columns
        df = df.assign(**{c: df[c].astype("string") for c in objs})
        df.to_parquet(path, compression="zstd", compression_level=9, index=False)
    return path.stat().st_size


def seconds(df: pd.DataFrame) -> pd.DataFrame:
    """Plain copy with timedelta columns replaced by float seconds (<name>_s)."""
    out = pd.DataFrame(df).copy()
    for col in list(out.select_dtypes(include="timedelta").columns):
        out[f"{col}_s"] = out[col].dt.total_seconds()
        out = out.drop(columns=col)
    return out


def to_int(series: pd.Series) -> pd.Series:
    """Round to integers: Int16 unless the data needs more room. Never fails, never clips."""
    s = pd.to_numeric(series, errors="coerce").round()
    lo, hi = s.min(), s.max()
    if pd.notna(lo) and (lo < -32768 or hi > 32767):
        return s.astype("Int32")
    return s.astype("Int16")


def rng(s: pd.Series):
    lo, hi = s.min(), s.max()
    return None if pd.isna(lo) else [int(lo), int(hi)]


def tidy_stream(streams: dict, kind: str) -> pd.DataFrame:
    frames = []
    for num, df in streams.items():
        f = pd.DataFrame(df)
        out = pd.DataFrame({
            "driver_number": np.full(len(f), int(num), dtype="int16"),
            "date_utc": f["Date"].astype("datetime64[ms]"),
            "session_time_s": f["SessionTime"].dt.total_seconds().astype("float32"),
        })
        if kind == "car":
            for col in ("Speed", "RPM", "nGear", "Throttle", "DRS"):
                out[col.lower()] = to_int(f[col])
            out["brake"] = f["Brake"].fillna(False).astype(bool)
        else:
            for col in ("X", "Y", "Z"):
                out[col.lower()] = pd.to_numeric(f[col], errors="coerce").round().astype("Int32")
            out["status"] = f["Status"].astype("string")
        frames.append(out)
    return pd.concat(frames, ignore_index=True)


def gap_report(streams: dict) -> dict:
    """Largest gap per driver in session time; keeps only drivers above GAP_LIMIT_S."""
    over, worst = {}, 0.0
    for num, df in streams.items():
        t = pd.DataFrame(df)["SessionTime"].dt.total_seconds().to_numpy()
        if len(t) < 2:
            continue
        d = np.diff(t)
        k = int(np.argmax(d))
        worst = max(worst, float(d[k]))
        if d[k] > GAP_LIMIT_S:
            over[str(num)] = {"gap_s": round(float(d[k]), 1), "starts_at_s": round(float(t[k]), 1)}
    return {"max_gap_s": round(worst, 1), "over_limit": over}


def car_quality(car_df: pd.DataFrame) -> dict:
    return {
        "ngear_over_8": int((car_df["ngear"] > 8).sum()),
        "throttle_over_100": int((car_df["throttle"] > 100).sum()),
        "drs_values": sorted(int(v) for v in car_df["drs"].dropna().unique()),
    }


def already_done(year: int, event, code: str, want_telemetry: bool) -> bool:
    if not MANIFEST.exists():
        return False
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        # rows ingested by name also carry a "round"; match on it when asked by round number
        ident = r.get("round", r["requested_event"]) if isinstance(event, int) else r["requested_event"]
        if ((r["year"], ident, r["session"]) == (year, event, code)
                and r["status"] == "ok"
                and (r.get("with_telemetry") or not want_telemetry)):
            return True
    return False


def log_manifest(row: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def report(row: dict) -> None:
    print(f"\n{row['year']} {row.get('event', row['requested_event'])} {row['session']}: "
          f"{row['status'].upper()} in {row['seconds']}s")
    if "error" in row:
        print("  ERROR:", row["error"])
    total = 0
    for table, info in row.get("tables", {}).items():
        if "bytes" in info:
            total += info["bytes"]
            print(f"  {table:24} {info['rows']:9d} rows {info['bytes'] / 1e6:7.2f} MB")
        else:
            print(f"  {table:24} FAILED {info['error']}")
    print(f"  {'total':24} {'':>14} {total / 1e6:7.2f} MB")
    for key in ("telemetry", "circuit", "car_quality"):
        if key in row:
            print(f"  {key}: {row[key]}")
    for key in ("car_gaps", "pos_gaps"):
        if key in row:
            g = row[key]
            starts = sorted(v["starts_at_s"] for v in g["over_limit"].values())
            print(f"  {key}: worst gap {g['max_gap_s']}s; {len(g['over_limit'])} drivers over "
                  f"limit; gaps start at {starts[:3]}{'...' if len(starts) > 3 else ''}")
    if row.get("warnings"):
        print(f"  fastf1 warnings: {len(row['warnings'])}")


def ingest(year: int, event, code: str, force: bool = False, keep_cache: bool = False,
           telemetry: bool = True) -> dict:
    if not force and already_done(year, event, code, telemetry):
        print(f"{year} {event} {code}: already ingested, skipping (use --force to redo)")
        return {"status": "skipped"}
    t0 = time.monotonic()
    row = {"year": year, "requested_event": event, "session": code,
           "fastf1_version": fastf1.__version__,
           "ingested_at": datetime.now(UTC).isoformat(), "with_telemetry": False}
    collector = Collect()
    logging.getLogger("fastf1").addHandler(collector)
    try:
        session = fastf1.get_session(year, event, code)
        session.load(laps=True, telemetry=telemetry, weather=True, messages=True)
        rnd = int(session.event["RoundNumber"])
        name = str(session.event["EventName"])
        row.update(round=rnd, event=name, location=str(session.event["Location"]),
                   country=str(session.event["Country"]))

        builders = {
            "laps": lambda: seconds(session.laps),
            "weather": lambda: seconds(session.weather_data),
            "race_control": lambda: pd.DataFrame(session.race_control_messages).copy(),
            "results": lambda: seconds(session.results),
            "track_status": lambda: seconds(session.track_status),
            "session_status": lambda: seconds(session.session_status),
        }
        if telemetry:
            try:
                car, pos = session.car_data, session.pos_data
                if not car or not pos:
                    raise ValueError("empty telemetry")
                car_df = tidy_stream(car, "car")
                pos_df = tidy_stream(pos, "pos")
                row["car_quality"] = car_quality(car_df)
                row["car_gaps"], row["pos_gaps"] = gap_report(car), gap_report(pos)
                builders["telemetry_car"] = lambda: car_df
                builders["telemetry_pos"] = lambda: pos_df
                row["with_telemetry"] = True
            except Exception as e:
                row["telemetry"] = f"unavailable: {type(e).__name__}: {e}"
        else:
            row["telemetry"] = "skipped"
        try:
            info = session.get_circuit_info()
            builders["circuit_corners"] = lambda: pd.DataFrame(info.corners).copy()
            builders["circuit_marshal_sectors"] = lambda: pd.DataFrame(info.marshal_sectors).copy()
            row["circuit_rotation"] = float(info.rotation)
        except Exception as e:
            row["circuit"] = f"unavailable: {type(e).__name__}: {e}"

        tables = {}
        for table, build in builders.items():
            try:
                df = build()
                df.insert(0, "event", name)
                tables[table] = {"rows": len(df),
                                 "bytes": write(df, part_path(table, year, rnd, code))}
            except Exception as e:
                tables[table] = {"error": f"{type(e).__name__}: {e}"}
        row["tables"] = tables
        optional = {"track_status", "session_status"}  # nice to have: never downgrade a session
        failed = [t for t, i in tables.items() if "error" in i and t not in optional]
        if "bytes" not in tables.get("laps", {}):
            row["status"] = "failed"
        elif failed or (telemetry and not row["with_telemetry"]):
            row["status"] = "partial"
        else:
            row["status"] = "ok"
    except Exception as e:
        row.update(status="failed", error=f"{type(e).__name__}: {e}")
    finally:
        logging.getLogger("fastf1").removeHandler(collector)

    row["warnings"] = sorted(set(collector.messages))[:25]
    row["seconds"] = round(time.monotonic() - t0, 1)
    if "RateLimit" in str(row.get("error", "")):
        row["status"] = "ratelimited"  # not recorded: the batch retries it after waiting
        print(f"{year} {event} {code}: rate limited (not recorded)")
        return row
    log_manifest(row)
    report(row)
    if row["status"] != "failed" and not keep_cache:
        shutil.rmtree(CACHE)
        CACHE.mkdir(parents=True, exist_ok=True)
    return row


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    ev = int(args[1]) if args[1].isdigit() else args[1]
    ingest(int(args[0]), ev, args[2], force="--force" in flags,
           keep_cache="--keep-cache" in flags, telemetry="--no-telemetry" not in flags)
